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

# Allow selected model IDs in major commercial US regions.
# Use ["*"] only when the selected model IDs should be allowed in any region.
bedrock_allowed_regions = ["us-east-1", "us-east-2", "us-west-1", "us-west-2"]

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
- inline IAM policy allowing selected Bedrock model invocation in `bedrock_allowed_regions`
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

To test Bedrock directly before configuring FortiAIGate:

```bash
cd ansible
ansible-playbook playbooks/test_model_direct.yml
```

The direct test uses the generic Bedrock Converse API, calls the repo-owned `tests/bedrock_direct_test.py` signer, asks for a short response plus the model name, and summarizes the response.

To run the same script manually from the repo root:

```bash
export AWS_ACCESS_KEY_ID="$(terraform -chdir=terraform/aws-bedrock output -raw bedrock_access_key_id)"
export AWS_SECRET_ACCESS_KEY="$(terraform -chdir=terraform/aws-bedrock output -raw bedrock_secret_access_key)"
python3 tests/bedrock_direct_test.py \
  --region "$(terraform -chdir=terraform/aws-bedrock output -raw bedrock_region)"
```

The script reads `terraform/aws-bedrock` permitted model IDs and prompts for one when run interactively. Set `BEDROCK_MODEL` to skip the prompt. It generates AWS SigV4 headers at runtime. If the access key or secret key is not exported and the script is run interactively, it prompts for the missing value.

After FortiAIGate status is `READY`, log in with the URL from `status_fortiaigate.yml`, change the default password, and create the first Bedrock guard/provider with the values above.

Then run the first external chat test:

```bash
cd ansible
ansible-playbook playbooks/test_fortiaigate_chat.yml
```

The playbook reads the first permitted model ID from `terraform/aws-bedrock` when available, calls `tests/fortiaigate_chat_test.py`, sends a short test prompt that asks the routed model to identify itself to `https://<fortiaigate-public-ip>:443/v1/chat/completions`, and summarizes the response.

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
