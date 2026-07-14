# Terraform

Terraform is split into user-facing steps that keep AWS setup in Terraform before switching to Ansible:

- `terraform/common.tfvars`: shared local configuration for all Terraform modules
- `terraform/aws-ecr`: private ECR repositories and generated Ansible registry vars
- `terraform/aws-prep`: IAM, ECR pull permissions, trusted source CIDRs, EIPs, and Bedrock IAM credentials
- `terraform/aws-ec2-k3s`: VPC, subnets, GPU EC2 instance, EIP association, generated Ansible inventory, and generated demo port vars
- `terraform/aws-fortigate`: optional FortiGate appliance deployment, scaffolded for Phase 4
- `terraform/aws-fortiweb`: optional FortiWeb appliance deployment, scaffolded for Phase 4

All modules use local Terraform state for now. Remote state is a future enhancement.

## AWS Authentication

Use AWS IAM Identity Center / SSO profiles:

```bash
aws sso login --profile <profile-name>
```

Set shared values once:

```bash
cd terraform
cp common.tfvars.example common.tfvars
```

Edit `common.tfvars`:

```hcl
aws_profile          = "AdministratorAccess-123456789012"
aws_region           = "us-east-1"
name_prefix          = "fortiaigate-demo"
allowed_ingress_cidr = [
  "203.0.113.10/32",
]
tags                 = {}
```

`allowed_ingress_cidr` accepts either a single CIDR string or a list of CIDR
strings. The list form is preferred when multiple operators need direct lab
access.

Each Terraform module has a tracked `common.auto.tfvars` symlink to
`../common.tfvars`, so the shared values are loaded automatically:

```bash
terraform plan
terraform apply
```

Do not commit `.terraform/`, real `.tfvars`, state, plans, or generated secrets.

Before Terraform imports, destructive changes, or larger refactors, create a
local backup of operator config, generated values, inventory, and Terraform
state:

```bash
python3 scripts/backup_config.py
```

Use `python3 scripts/backup_config.py --dry-run` to preview the selected files.

## ECR Module

```bash
cd terraform/aws-ecr
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt
terraform validate
terraform apply
```

This module creates or imports private ECR repositories and writes non-secret registry values to:

```text
ansible/group_vars/ecr.generated.yml
```

ECR pull permissions are owned by `terraform/aws-prep`, not this module.

### Import Existing ECR Repositories

If repositories were created manually, import them before `terraform apply`:

```bash
terraform import 'aws_ecr_repository.this["api"]' fortiaigate/api
terraform import 'aws_ecr_repository.this["core"]' fortiaigate/core
terraform import 'aws_ecr_repository.this["webui"]' fortiaigate/webui
terraform import 'aws_ecr_repository.this["scanner"]' fortiaigate/scanner
terraform import 'aws_ecr_repository.this["logd"]' fortiaigate/logd
terraform import 'aws_ecr_repository.this["license_manager"]' fortiaigate/license_manager
terraform import 'aws_ecr_repository.this["triton-models"]' fortiaigate/triton-models
terraform import 'aws_ecr_repository.this["custom-triton"]' fortiaigate/custom-triton
terraform import 'aws_ecr_repository.this["chatbot-basic"]' fortiaigate/chatbot-basic
```

## AWS Prep Module

```bash
cd terraform/aws-prep
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt
terraform validate
terraform apply
```

This module creates:

- EC2 IAM role and instance profile for the k3s host
- scoped ECR pull policy attachment when `registry_backend = "ecr"`
- scoped Bedrock invoke policy attachment when `enable_ec2_bedrock_iam = true`
- preallocated EIPs for selected entry points
- trusted source CIDR outputs
- optional FortiWeb S3 cloud-init bucket and IAM instance profile when `fortiweb_enabled = true`
- optional Bedrock IAM user, access key, and policy

The EC2 module reads this module's local state by default through:

```hcl
aws_prep_state_path = "../aws-prep/terraform.tfstate"
```

When `registry_backend = "ecr"`, this module reads ECR repository ARNs from:

```hcl
aws_ecr_state_path = "../aws-ecr/terraform.tfstate"
```

Retrieve Bedrock GUI values from this module when `enable_bedrock_iam = true`:

```bash
terraform output bedrock_access_key_id
terraform output -raw bedrock_secret_access_key
terraform output bedrock_key_expires_at
terraform output bedrock_allowed_regions
terraform output bedrock_model_ids
```

The secret access key is stored in Terraform state. Do not commit state or real `terraform.tfvars`.

For Phase 4 appliance deployment, enable prep-owned appliance EIPs:

```hcl
allocate_eips = {
  k3s       = true
  fortigate = true
  fortiweb  = true
}
```

FortiWeb cloud-init also needs an S3 bucket and EC2 instance profile. Enable
those only when deploying FortiWeb:

```hcl
fortiweb_enabled = true
```

The bucket stores the FortiWeb command/config object and BYOL license object.
Those objects and Terraform state are sensitive.

## AWS EC2 k3s Module

```bash
cd terraform/aws-ec2-k3s
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt
terraform validate
terraform apply
```

See [VPC Layout](vpc-layout.md) for a diagram of the public k3s subnet, private
k3s subnet, FortiGate/FortiWeb placeholder subnets, EIPs, and external AWS
service paths.

This module creates:

- dedicated VPC
- k3s public subnet without automatic public-IP assignment
- k3s private subnet
- FortiGate and FortiWeb public management subnets without automatic public-IP assignment
- FortiGate and FortiWeb internal subnets with local-only route tables
- internet gateway and public route table
- security group for SSH, HTTP, and HTTPS from the trusted CIDR in `aws-prep`
- Ubuntu 24.04 GPU EC2 instance
- prep-owned EIP association in public k3s mode
- generated Ansible inventory

Terraform writes the inventory to:

```text
ansible/inventory/aws.generated.ini
```

Set `ssh_private_key_file` in `terraform.tfvars` when the EC2 key pair does not use your default SSH key. Terraform includes that path in both:

- `ansible_ssh_private_key_file` in the generated inventory
- the `ssh_command` output as `ssh -i <keypath> ubuntu@<host-ip>`

Set `ec2_pull_github_keys = ["<github-user>"]` only when the instance should
pull public GitHub SSH keys into `/home/ubuntu/.ssh/authorized_keys` during
first boot. Leave it empty to skip. This requires the instance to reach GitHub
during cloud-init and does not re-run automatically on an existing instance.

The selected Availability Zone controls the k3s and appliance subnets. By default, Terraform queries EC2 instance type offerings, sorts the AZs that offer `instance_type`, and selects the first one.

The module writes these non-secret network values into the generated inventory:

```ini
aws_vpc_cidr=10.20.0.0/16
aws_public_subnet_cidr=10.20.1.0/24
aws_k3s_private_subnet_cidr=10.20.2.0/24
aws_fortigate_public_subnet_cidr=10.20.10.0/24
aws_fortigate_internal_subnet_cidr=10.20.20.0/24
aws_fortiweb_public_subnet_cidr=10.20.11.0/24
aws_fortiweb_internal_subnet_cidr=10.20.21.0/24
aws_k3s_subnet_mode=public
k3s_cluster_cidr=10.60.0.0/16
k3s_service_cidr=10.70.0.0/16
k3s_cluster_dns=10.70.0.10
```

Keep AWS VPC, k3s pod, and k3s service networks non-overlapping. Change these values before cluster creation. Public-mode k3s access uses the prep-owned EIP only; the EC2 instance and public subnets do not request auto-assigned ephemeral public IPv4 addresses.

`terraform/aws-ec2-k3s` generates the standard demo port assignments, opens
those ports from `allowed_ingress_cidr`, and writes
`ansible/group_vars/ports.generated.yml` for Ansible. The default generated
HTTP ports are reserved consistently: Open WebUI uses `30080` when enabled,
custom chatbot `30081`, demo home `30082`, LiteLLM Admin/API `30083`, and MCP
demo tools `30084`. The optional HTTPS gateway uses matching offsets: `30443`,
`30444`, `30445`, `30446`, and `30447`.

`additional_ingress_tcp_ports` is only for extra public TCP listeners beyond
those generated demo ports.

The EC2 module also queries AWS Price List data for the configured
`instance_type` and `aws_region` and outputs an estimated Linux On-Demand
shared-tenancy compute cost:

```bash
terraform output ec2_instance_hourly_cost_usd
terraform output ec2_instance_monthly_cost_usd
terraform output ec2_instance_pricing_location
```

The monthly estimate is `hourly * 30 * 24`. It excludes EBS, EIP idle charges,
data transfer, Bedrock, marketplace, and licensing costs. If AWS adds a region
that is not in the module's built-in pricing-location map, set
`aws_pricing_location_override` in `terraform.tfvars`.

## Optional Appliance Modules

`terraform/aws-fortigate` and `terraform/aws-fortiweb` are independent
user-facing roots. They read local state from `terraform/aws-prep` and
`terraform/aws-ec2-k3s`; they do not own the VPC or make appliances required
for normal k3s demo rebuilds.

FortiGate is implemented in `terraform/aws-fortigate` and uses a prep-owned
EIP, two ENIs, FortiGate cloud-init, and an optional local BYOL license file.
The initial FortiGate password is the EC2 instance ID. The generated API key
and rendered user-data are stored in local Terraform state.

## Instance Sizing

The Terraform default instance type is `g4dn.4xlarge`.

Use `g6.8xlarge` for a stronger production-like L4 validation target. Use `g6.4xlarge` when you want a lower-cost official L4 lab candidate.

See [aws_instance.MD](aws_instance.MD) for the detailed table separating test infrastructure, supported validation infrastructure, and experimental instance families.
