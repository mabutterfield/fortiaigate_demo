# AWS Prep Terraform Module

This module prepares shared AWS resources used by the FortiAIGate demo:

- EC2 IAM role and instance profile for the k3s host
- scoped ECR pull permissions from the ECR Terraform state when `registry_backend = "ecr"`
- trusted source CIDR outputs
- preallocated public EIPs for selected entry points
- FortiWeb S3 cloud-init bucket and IAM instance profile when enabled
- optional private S3 bucket for pre-staged synthetic Phase 8 document fixtures
- optional private S3 bucket for FortiAIGate syslog preservation
- optional temporary Bedrock IAM credentials for FortiAIGate provider setup

Run it after the registry module and before the EC2 k3s foundation module:

```bash
terraform init
terraform apply
```

Copy `99-local.auto.tfvars.example` to `99-local.auto.tfvars` only when
overriding the tracked defaults in `00-system.auto.tfvars`.

This module reads `terraform/aws-ecr` local state by default when
`registry_backend = "ecr"`. The EC2 module reads this module's local Terraform
state by default.

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

Phase 8 document fixture S3 prep is disabled by default. Enable it only when
you are ready to test S3-backed document retrieval through MCP:

```hcl
phase8_documents_bucket_enabled = true
phase8_documents_prefix         = "phase8-fixtures"
```

When enabled, this module creates a private encrypted bucket, blocks public
access, and attaches a read/list policy for the configured prefix to the k3s
EC2 IAM role. The chatbot does not receive AWS credentials.

FortiAIGate syslog S3 prep is disabled by default. Enable it before deploying
the in-cluster syslog collector:

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
terraform output bedrock_access_key_id
terraform output -raw bedrock_secret_access_key
terraform output bedrock_key_expires_at
terraform output bedrock_allowed_regions
terraform output bedrock_model_ids
```

The Bedrock secret access key is stored in Terraform state. Do not commit state
or real `99-local.auto.tfvars` files.
