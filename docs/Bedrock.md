# AWS Bedrock

This workflow creates temporary-use AWS IAM credentials for FortiAIGate Bedrock testing without running Ollama.

FortiAIGate currently asks for standard AWS SigV4 fields in the GUI:

- Access Key ID
- Secret Access Key
- Region Name
- Bedrock model ID

The Terraform module therefore creates a dedicated IAM user and access key. It does not attach Bedrock permissions to the EC2 instance profile, and it does not write Ansible vars.

Model access must already be enabled in the AWS account and region.

## Create Credentials

```bash
cd terraform/aws-bedrock
cp terraform.tfvars.example terraform.tfvars
aws sso login --profile <profile-name>
terraform init
terraform fmt
terraform validate
terraform apply
```

Set these values in ignored `terraform.tfvars`. Use the exact Bedrock model ID, including provider suffixes such as `-1:0`; the short display name `openai.gpt-oss-20b` is not enough for the FortiAIGate provider.

```hcl
aws_profile = "AdministratorAccess-123456789012"
aws_region  = "us-west-2"
name_prefix = "faig-lab"

credential_valid_days = 7
credential_generation = "20260610"

bedrock_model_ids = [
  "openai.gpt-oss-20b-1:0",
]

# By default, source IP restrictions are derived from terraform/aws-ec2-k3s:
# - public_ip as <eip>/32
# - allowed_ingress_cidr
ec2_k3s_state_path = "../aws-ec2-k3s/terraform.tfstate"
no_ip_restriction  = false

# Optional additional source CIDRs.
allowed_source_cidrs = []
```

Terraform creates:

- IAM user named `<name_prefix>-bedrock`
- IAM access key for that user
- inline IAM policy allowing selected Bedrock model invocation
- explicit deny after `now + credential_valid_days`
- explicit deny when requests do not originate from the EC2 EIP, `allowed_ingress_cidr`, or `allowed_source_cidrs`

Allowed invoke actions:

- `bedrock:InvokeModel`
- `bedrock:InvokeModelWithResponseStream`
- `bedrock:Converse`
- `bedrock:ConverseStream`

## FortiAIGate GUI Values

Retrieve the values after apply:

```bash
terraform output bedrock_access_key_id
terraform output -raw bedrock_secret_access_key
terraform output bedrock_key_expires_at
terraform output bedrock_region
terraform output bedrock_model_ids
```

Paste these into the FortiAIGate Bedrock provider setup:

```text
Access Key ID:     terraform output bedrock_access_key_id
Secret Access Key: terraform output -raw bedrock_secret_access_key
Region Name:       terraform output bedrock_region
Model ID:          one value from terraform output bedrock_model_ids
```

## Refresh Expiration

Change `credential_generation` and apply again:

```bash
terraform apply -var="credential_generation=$(date +%Y%m%d)"
```

This recalculates the expiration timestamp as current time plus `credential_valid_days`. It does not rotate the access key.

## Teardown

Remove the credentials entirely when testing is complete:

```bash
terraform destroy
```

This deletes the IAM access key, IAM user, and inline policy.

## Bedrock API Keys

Amazon Bedrock API keys are bearer-token credentials, not the same thing as normal AWS Access Key ID and Secret Access Key credentials.

Do not paste Bedrock API keys into the FortiAIGate Access Key ID or Secret Access Key fields unless FortiAIGate documentation later confirms bearer-token API key support.

## Security Notes

The secret access key is stored in Terraform state.

Rules:

- do not commit Terraform state
- do not commit real `terraform.tfvars`
- do not print the secret in logs
- do not paste the secret into chat or tickets
- treat terminal scrollback as sensitive after running `terraform output -raw bedrock_secret_access_key`
- prefer short validity windows, such as 1 to 7 days
- run `terraform destroy` when testing is complete

The expiration policy denies access after the expiration timestamp. It does not delete the IAM access key.

## Source IP Lockdown

By default, the Bedrock module reads local Terraform state from `terraform/aws-ec2-k3s` and allows requests from:

- the k3s host Elastic IP as `<eip>/32`
- the EC2 module `allowed_ingress_cidr`
- any additional `allowed_source_cidrs`

To disable source IP restrictions:

```hcl
no_ip_restriction = true
```

This works when FortiAIGate reaches Bedrock through the public AWS service endpoint and AWS sees the EC2 host's EIP as the request source. If Bedrock traffic later moves through an AWS PrivateLink/VPC endpoint, use a VPC endpoint condition such as `aws:SourceVpce` instead of public `aws:SourceIp`.
