# AWS Prep Terraform Module

This module prepares shared AWS resources used by the FortiAIGate demo:

- EC2 IAM role and instance profile for the k3s host
- scoped ECR pull permissions from the ECR Terraform state when `registry_backend = "ecr"`
- trusted source CIDR outputs
- preallocated public EIPs for selected entry points
- optional temporary Bedrock IAM credentials for FortiAIGate provider setup

Run it after the registry module and before the EC2 k3s foundation module:

```bash
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
```

This module reads `terraform/aws-ecr` local state by default when
`registry_backend = "ecr"`. The EC2 module reads this module's local Terraform
state by default.

Retrieve Bedrock GUI values when `enable_bedrock_iam = true`:

```bash
terraform output bedrock_access_key_id
terraform output -raw bedrock_secret_access_key
terraform output bedrock_key_expires_at
terraform output bedrock_allowed_regions
terraform output bedrock_model_ids
```

The Bedrock secret access key is stored in Terraform state. Do not commit state
or real `terraform.tfvars` files.
