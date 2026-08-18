# AWS Prep Terraform Module

This module prepares shared AWS resources used by the FortiAIGate demo:

- EC2 IAM role and instance profile for the k3s host
- scoped ECR pull permissions from the ECR Terraform state when `registry_backend = "ecr"`
- trusted source CIDR outputs
- preallocated public EIPs for selected entry points
- FortiWeb S3 cloud-init bucket and IAM instance profile when enabled
- optional private S3 bucket for pre-staged synthetic document fixtures
- optional private S3 bucket for FortiAIGate syslog preservation
- optional temporary Bedrock IAM credentials for FortiAIGate provider setup

Run it after the registry module and before the EC2 k3s foundation module:

```bash
terraform -chdir=terraform/aws-prep init
terraform -chdir=terraform/aws-prep apply
```

Copy `99-local.auto.tfvars.example` to `99-local.auto.tfvars` only when
overriding the tracked defaults in `00-system.auto.tfvars`.

This module reads `terraform/aws-ecr` local state by default when
`registry_backend = "ecr"`. The EC2 module reads this module's local Terraform
state by default.

The default full AWS deployment creates one shared k3s EC2 role and, when
FortiWeb is enabled, one FortiWeb cloud-init role. Optional ECR, Bedrock,
scenario-document, and syslog permissions do not create additional roles; they
attach scoped policies to the shared k3s role. The roles are removed by normal
Terraform teardown and are not date-gated. The separate optional Bedrock IAM
user has a policy expiration. See [IAM identities, scope, and
lifetime](../../docs/terraform.md#iam-identities-scope-and-lifetime) for the
complete inventory, teardown behavior, and existing-role import limitations.

Appliance prep is enabled by default for the full demo. Override these
values in `99-local.auto.tfvars` only when disabling appliance prep:

```hcl
allocate_eips = {
  k3s       = true
  fortigate = true
  fortiweb  = true
}

fortiweb_enabled = true
```

When `fortiweb_enabled = true`, this module creates a private encrypted S3
bucket and an EC2 instance profile FortiWeb can use to read its cloud-init
command file and license file. The default object keys are:

```text
fortiweb/cloud-init/config.txt
fortiweb/cloud-init/FWB.lic
```

License objects are sensitive. Do not commit license files, rendered user-data,
or Terraform state.

Document fixture S3 prep is disabled by default. Enable it only when
you are ready to test S3-backed document retrieval through MCP:

```hcl
scenario_documents_bucket_enabled = true
scenario_documents_prefix         = "scenario-fixtures"
```

Older local overrides used numbered development variable names. Rename those
entries in ignored `99-local.auto.tfvars` to the `scenario_documents_*` names
above before the next plan. Terraform moved declarations preserve existing
resource addresses; review the plan normally because the IAM policy's display
name is also normalized.

When enabled, this module creates a private encrypted bucket, blocks public
access, and attaches a read/list policy for the configured prefix to the k3s
EC2 IAM role. The chatbot does not receive AWS credentials.

FortiAIGate syslog S3 prep is disabled by default. AWS `python3
scripts/user_profile.py init` asks whether to enable it and creates the ignored
`99-local.auto.tfvars` override either way. To change an existing profile before
deploying the in-cluster syslog collector, set:

```hcl
fortiaigate_syslog_bucket_enabled = true
fortiaigate_syslog_prefix         = "fortiaigate/syslog"
```

When enabled, this module creates a private encrypted bucket, blocks public
access, and attaches a write/list policy for the configured prefix to the k3s
EC2 IAM role. The Fluent Bit collector uses the EC2 instance role through the
normal AWS credential chain; no static AWS keys are stored in Kubernetes.

Retrieve Bedrock GUI values when `enable_bedrock_iam = true`:

```bash
terraform -chdir=terraform/aws-prep output bedrock_access_key_id
terraform -chdir=terraform/aws-prep output -raw bedrock_secret_access_key
terraform -chdir=terraform/aws-prep output bedrock_key_expires_at
terraform -chdir=terraform/aws-prep output bedrock_allowed_regions
terraform -chdir=terraform/aws-prep output bedrock_model_ids
```

The Bedrock secret access key is stored in Terraform state. Do not commit state
or real `99-local.auto.tfvars` files.
