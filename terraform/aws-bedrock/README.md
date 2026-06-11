# AWS Bedrock Terraform Module

This module creates temporary-use AWS IAM credentials for manual FortiAIGate Bedrock provider configuration.

It creates:

- dedicated IAM user
- dedicated IAM access key
- inline policy allowing selected Bedrock model invocation
- explicit deny after the configured expiration timestamp
- source IP deny derived from the k3s host EIP and `allowed_ingress_cidr`

It does not attach policies to the EC2 instance role and does not write Ansible vars.

Canonical documentation:

- [../../docs/Bedrock.md](../../docs/Bedrock.md)
- [../../docs/terraform.md](../../docs/terraform.md)
- [../../docs/deployment-runbook.md](../../docs/deployment-runbook.md)

Quick usage:

```bash
cp terraform.tfvars.example terraform.tfvars
aws sso login --profile <profile-name>
terraform init
terraform fmt
terraform validate
terraform apply
```

Retrieve GUI values:

```bash
terraform output bedrock_access_key_id
terraform output -raw bedrock_secret_access_key
terraform output bedrock_key_expires_at
terraform output bedrock_region
terraform output bedrock_model_ids
```

The secret access key is stored in Terraform state. Do not commit state or real `terraform.tfvars`.
