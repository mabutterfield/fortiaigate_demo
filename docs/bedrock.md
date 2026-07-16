# AWS Bedrock

This workflow creates temporary-use AWS IAM credentials for FortiAIGate Bedrock testing without running Ollama.

FortiAIGate currently asks for standard AWS SigV4 fields in the GUI:

- Access Key ID
- Secret Access Key
- Region Name
- Bedrock model ID

`terraform/aws-prep` can create two Bedrock access paths:

- temporary IAM user credentials for FortiAIGate GUI provider setup when
  `enable_bedrock_iam = true`
- scoped Bedrock invoke permissions on the k3s EC2 instance role when
  `enable_ec2_bedrock_iam = true`, which is the default path used by in-cluster
  LiteLLM/direct clients

It does not write Bedrock secrets into Ansible vars.

Model access must already be enabled in the AWS account and region.

## Create Credentials

```bash
cd terraform/aws-prep
cp 99-local.auto.tfvars.example 99-local.auto.tfvars
aws sso login --profile <profile-name>
terraform init
terraform fmt
terraform validate
terraform apply
```

Set these values in ignored `99-local.auto.tfvars`. Use the exact Bedrock model ID, including provider suffixes such as `-1:0`; the short display name `openai.gpt-oss-20b` is not enough for the FortiAIGate provider.

```hcl
enable_bedrock_iam = true
enable_ec2_bedrock_iam = true

bedrock_credential_valid_days = 7
bedrock_credential_generation = "20260610"

bedrock_model_ids = [
  "openai.gpt-oss-20b-1:0",
]

# Allow selected model IDs in major commercial US regions.
# Use ["*"] only when the selected model IDs should be allowed in any region.
bedrock_allowed_regions = ["us-east-1", "us-east-2", "us-west-1", "us-west-2"]

# By default, source IP restrictions use terraform/user.tfvars
# allowed_ingress_cidr, which may be one CIDR or a list of CIDRs, and the
# prep-owned k3s EIP when allocated.
bedrock_no_ip_restriction = false

# Optional additional source CIDRs.
bedrock_allowed_source_cidrs = []
```

Terraform creates:

- IAM user named `<name_prefix>-bedrock`
- IAM access key for that user
- inline IAM policy allowing selected Bedrock model invocation in `bedrock_allowed_regions`
- explicit deny after `now + credential_valid_days`
- explicit deny when requests do not originate from the prep-owned k3s EIP, `allowed_ingress_cidr` CIDR or CIDRs, or `bedrock_allowed_source_cidrs`
- optional EC2 instance-role policy allowing selected Bedrock model invocation
  for in-cluster LiteLLM/direct clients

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
terraform output bedrock_allowed_regions
terraform output bedrock_model_ids
```

Paste these into the FortiAIGate Bedrock provider setup:

```text
Access Key ID:     terraform output bedrock_access_key_id
Secret Access Key: terraform output -raw bedrock_secret_access_key
Region Name:       one value from terraform output bedrock_allowed_regions
Model ID:          one value from terraform output bedrock_model_ids
```

To test Bedrock directly before configuring FortiAIGate:

```bash
cd ansible
ansible-playbook playbooks/test_model_direct.yml
```

The direct test uses the generic Bedrock Converse API, calls the repo-owned `scripts/bedrock_direct_test.py` signer, asks for a short response plus the model name, and summarizes the response.

To run the same script manually from the repo root:

```bash
export AWS_ACCESS_KEY_ID="$(terraform -chdir=terraform/aws-prep output -raw bedrock_access_key_id)"
export AWS_SECRET_ACCESS_KEY="$(terraform -chdir=terraform/aws-prep output -raw bedrock_secret_access_key)"
python3 scripts/bedrock_direct_test.py \
  --region "$(terraform -chdir=terraform/aws-prep output -raw bedrock_region)"
```

The script reads `terraform/aws-prep` permitted model IDs and prompts for one when run interactively. Set `BEDROCK_MODEL` to skip the prompt. It generates AWS SigV4 headers at runtime. If the access key or secret key is not exported and the script is run interactively, it prompts for the missing value.

After FortiAIGate status is `READY`, log in with the URL from
`status_fortiaigate.yml`, change the default password, and create the
Bedrock-direct guard/provider with the values above when testing FortiAIGate
without LiteLLM in the middle.

Then run the first external chat test:

```bash
cd ansible
ansible-playbook playbooks/test_fortiaigate_chat.yml
```

The playbook calls `scripts/fortiaigate_chat_test.py`, sends a short test prompt that asks the routed model to identify itself and repeat the URI under test to `https://<fortiaigate-public-ip>:443/v1/chat/completions`, and summarizes the response. The default model is the LiteLLM pass-through alias `pass-bedrock`, which matches the recommended FortiAIGate `/v1/*` fallback provider.

To test every configured FortiAIGate demo route instead of only the default
test route:

```bash
ansible-playbook playbooks/test_fortiaigate_chat.yml \
  -e fortiaigate_test_poll_all_endpoints=true
```

The shared extra var `-e poll_all_endpoints=true` is accepted by both the
FortiAIGate and LiteLLM direct test playbooks.

## Refresh Expiration

Change `bedrock_credential_generation` and apply again:

```bash
terraform apply -var="bedrock_credential_generation=$(date +%Y%m%d)"
```

This recalculates the expiration timestamp as current time plus `bedrock_credential_valid_days`. It does not rotate the access key.

## Teardown

Remove the Bedrock credentials entirely when testing is complete by setting:

```hcl
enable_bedrock_iam = false
```

Then apply `terraform/aws-prep` again. Do not use `terraform destroy` unless
you intend to remove all AWS prep resources, including the k3s EC2 role/profile
and preallocated EIPs.

## Bedrock API Keys

Amazon Bedrock API keys are bearer-token credentials, not the same thing as normal AWS Access Key ID and Secret Access Key credentials.

Do not paste Bedrock API keys into the FortiAIGate Access Key ID or Secret Access Key fields unless FortiAIGate documentation later confirms bearer-token API key support.

## Security Notes

The secret access key is stored in Terraform state.

Rules:

- do not commit Terraform state
- do not commit real `99-local.auto.tfvars`
- do not print the secret in logs
- do not paste the secret into chat or tickets
- treat terminal scrollback as sensitive after running `terraform output -raw bedrock_secret_access_key`
- prefer short validity windows, such as 1 to 7 days
- set `enable_bedrock_iam = false` and apply `terraform/aws-prep` when Bedrock testing is complete

The expiration policy denies access after the expiration timestamp. It does not delete the IAM access key.

## Source IP Lockdown

By default, `terraform/aws-prep` allows requests from:

- the prep-owned k3s public IP as `<eip>/32`, when allocated
- `allowed_ingress_cidr` CIDR or CIDRs from `terraform/user.tfvars`
- any additional `bedrock_allowed_source_cidrs`

To disable source IP restrictions:

```hcl
bedrock_no_ip_restriction = true
```

This works when FortiAIGate reaches Bedrock through the public AWS service endpoint and AWS sees the EC2 host's EIP as the request source. If Bedrock traffic later moves through an AWS PrivateLink/VPC endpoint, use a VPC endpoint condition such as `aws:SourceVpce` instead of public `aws:SourceIp`.
