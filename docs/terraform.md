# Terraform

Terraform is split into user-facing steps that keep AWS setup in Terraform before switching to Ansible:

- `terraform/user.tfvars`: shared local configuration for all Terraform modules
- `terraform/aws-ecr`: private ECR repositories and generated Ansible registry vars
- `terraform/aws-prep`: IAM, ECR pull permissions, trusted source CIDRs, EIPs, and Bedrock IAM credentials
- `terraform/aws-ec2-k3s`: VPC, subnets, GPU EC2 instance, EIP association, generated Ansible inventory, and generated demo port vars
- `terraform/aws-fortigate`: FortiGate appliance deployment, enabled by default for the full AWS demo
- `terraform/aws-fortiweb`: FortiWeb appliance deployment with S3-backed cloud-init, enabled by default for the full AWS demo

All modules use local Terraform state for now. Remote state is a future enhancement.

## AWS Authentication

Use AWS IAM Identity Center / SSO profiles:

```bash
aws sso login --profile <profile-name>
```

Set shared values once:

```bash
cp terraform/user.tfvars.example terraform/user.tfvars
```

Edit `user.tfvars`:

```hcl
aws_profile          = "AdministratorAccess-123456789012"
aws_region           = "us-east-1"
name_prefix          = "fortiaigate-demo"
ssh_key_name         = "my-existing-keypair"
allowed_ingress_cidr = [
  "203.0.113.10/32",
]
tags                 = {}
```

`allowed_ingress_cidr` accepts either a single CIDR string or a list of CIDR
strings. The list form is preferred when multiple operators need direct lab
access.

Each Terraform module has a tracked `50-user.auto.tfvars` symlink to
`../user.tfvars`, so the shared values are loaded automatically:

Run module commands from the repository root with `-chdir`, for example:

```bash
terraform -chdir=terraform/aws-prep plan
terraform -chdir=terraform/aws-prep apply
```

Do not commit `.terraform/`, real `.tfvars`, state, plans, or generated secrets.

Before moving to a fresh clone or reinitializing local user settings, export
the portable user profile:

```bash
python3 scripts/user_profile.py export ../user_profile.tgz
```

The profile includes user-owned tfvars/YAML, module-local overrides, and
registered installed scenario packages and state. It excludes scenario history,
Terraform state, generated inventory, license files, private keys, and
certificates.

## ECR Module

Container build, tag, publish, verification, cleanup, and rollback procedures
are owned by [Container Repository Management](container-repository-management.md).
The Terraform module is limited to repository infrastructure and generated
registry configuration.

```bash
cp terraform/aws-ecr/99-local.auto.tfvars.example terraform/aws-ecr/99-local.auto.tfvars
terraform -chdir=terraform/aws-ecr init
terraform -chdir=terraform/aws-ecr fmt
terraform -chdir=terraform/aws-ecr validate
terraform -chdir=terraform/aws-ecr apply
```

This module creates or imports private ECR repositories and writes non-secret registry values to:

```text
ansible/group_vars/ecr.generated.yml
```

ECR pull permissions are owned by `terraform/aws-prep`, not this module.

### Import Existing ECR Repositories

If repositories were created manually, import them before `terraform apply`:

```bash
terraform -chdir=terraform/aws-ecr import 'aws_ecr_repository.this["api"]' fortiaigate/api
terraform -chdir=terraform/aws-ecr import 'aws_ecr_repository.this["core"]' fortiaigate/core
terraform -chdir=terraform/aws-ecr import 'aws_ecr_repository.this["webui"]' fortiaigate/webui
terraform -chdir=terraform/aws-ecr import 'aws_ecr_repository.this["scanner"]' fortiaigate/scanner
terraform -chdir=terraform/aws-ecr import 'aws_ecr_repository.this["logd"]' fortiaigate/logd
terraform -chdir=terraform/aws-ecr import 'aws_ecr_repository.this["license_manager"]' fortiaigate/license_manager
terraform -chdir=terraform/aws-ecr import 'aws_ecr_repository.this["triton-models"]' fortiaigate/triton-models
terraform -chdir=terraform/aws-ecr import 'aws_ecr_repository.this["custom-triton"]' fortiaigate/custom-triton
terraform -chdir=terraform/aws-ecr import 'aws_ecr_repository.this["chatbot-basic"]' fortiaigate/chatbot-basic
```

## AWS Prep Module

```bash
cp terraform/aws-prep/99-local.auto.tfvars.example terraform/aws-prep/99-local.auto.tfvars
terraform -chdir=terraform/aws-prep init
terraform -chdir=terraform/aws-prep fmt
terraform -chdir=terraform/aws-prep validate
terraform -chdir=terraform/aws-prep apply
```

This module creates:

- EC2 IAM role and instance profile for the k3s host
- scoped ECR pull policy attachment when `registry_backend = "ecr"`
- scoped Bedrock invoke policy attachment when `enable_ec2_bedrock_iam = true`
- preallocated EIPs for selected entry points
- trusted source CIDR outputs
- optional FortiWeb S3 cloud-init bucket and IAM instance profile when `fortiweb_enabled = true`
- optional Bedrock IAM user, access key, and policy

### IAM identities, scope, and lifetime

The default full AWS deployment creates two IAM roles. Optional capabilities
reuse these roles by attaching scoped policies; they do not create a new role
for every feature.

| Identity | Created when | Purpose | Time limit | Removal |
|---|---|---|---|---|
| `<name_prefix>-ec2-role` and its instance profile | Always in `aws-prep` | Lets the k3s EC2 host pull the configured ECR images and invoke the selected Bedrock models; optional scenario-document and syslog policies attach to this same role | The role and policies have no date-based expiration. EC2 supplies rotating temporary role credentials while the profile is attached | Normal guided teardown destroys `aws-prep` after destroying the EC2 foundation |
| `<name_prefix>-fortiweb-cloudinit-role` and its instance profile | `fortiweb_enabled = true`, which is the tracked full-demo default | Lets the FortiWeb EC2 instance list its dedicated cloud-init bucket and read only the configured command and license objects | No date-based expiration | Normal guided teardown destroys FortiWeb first and then destroys `aws-prep`; disabling FortiWeb prep and applying also removes it |
| `<name_prefix>-bedrock` IAM user and access key | Only when `enable_bedrock_iam = true`; the tracked default is disabled | Supplies static AWS credentials only for optional direct FortiAIGate-to-Bedrock provider testing | Its inline policy explicitly denies all actions after the configured expiration, seven days by default. Expiration does not delete or deactivate the access key | Set `enable_bedrock_iam = false` and apply, or run normal guided teardown |

FortiGate does not receive an IAM role. The ECR pull, EC2 Bedrock invocation,
optional scenario-document read, and optional syslog write permissions are
separate least-purpose policies on the shared k3s EC2 role. The tracked
`ec2_iam_role_managed_policy_arns` list is empty, so no additional managed
policies are attached unless the operator explicitly supplies them.

The Bedrock IAM user is disabled by default because it is not required for the
normal chatbot -> FortiAIGate -> LiteLLM -> Bedrock path. That path uses the
k3s EC2 instance role. Enable `enable_bedrock_iam` only when direct
FortiAIGate-to-Bedrock testing is needed. See [AWS Bedrock](bedrock.md) for
expiration, source-IP restrictions, and key handling.

The roles themselves are intentionally lifecycle-bound to Terraform rather
than date-gated. A date condition could unexpectedly stop a running demo;
normal teardown is the control that removes the roles and their policies. If
`automated_teardown.py --skip-prep` is used, these identities remain until the
prep module is applied or destroyed later.

### Existing IAM roles and Terraform import

`ec2_iam_role_name` and `ec2_instance_profile_name` select names for resources
that this module creates and manages. They do not discover or reference
existing IAM objects. If an object with either name already exists but is not
in this Terraform state, `terraform apply` reports an already-exists conflict.

Terraform can adopt a compatible existing k3s role and instance profile. Set
their exact names in ignored `terraform/aws-prep/99-local.auto.tfvars`, then
import both before applying:

```hcl
ec2_iam_role_name         = "existing-k3s-role"
ec2_instance_profile_name = "existing-k3s-profile"
```

```bash
terraform -chdir=terraform/aws-prep import aws_iam_role.ec2 existing-k3s-role
terraform -chdir=terraform/aws-prep import aws_iam_instance_profile.ec2 existing-k3s-profile
terraform -chdir=terraform/aws-prep plan
```

Import transfers management of the role trust policy, tags, and
instance-profile relationship to this Terraform state. A subsequent apply also
creates and manages the repo-owned scoped policies and attachments. Review the
first plan carefully. Any same-named policies that already exist must be
imported or otherwise reconciled with state rather than recreated.

There is currently no reference-only mode that accepts an organization-owned
role/profile without managing it, and the FortiWeb role/profile names are not
independently configurable. Supporting centrally managed IAM cleanly would
require separate create-versus-existing variables and data-source lookups for
the k3s and FortiWeb profiles.

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
terraform -chdir=terraform/aws-prep output bedrock_access_key_id
terraform -chdir=terraform/aws-prep output -raw bedrock_secret_access_key
terraform -chdir=terraform/aws-prep output bedrock_key_expires_at
terraform -chdir=terraform/aws-prep output bedrock_allowed_regions
terraform -chdir=terraform/aws-prep output bedrock_model_ids
```

The secret access key is stored in Terraform state. Do not commit state or real `99-local.auto.tfvars`.

For appliance deployment, enable prep-owned appliance EIPs:

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
cp terraform/aws-ec2-k3s/99-local.auto.tfvars.example terraform/aws-ec2-k3s/99-local.auto.tfvars
terraform -chdir=terraform/aws-ec2-k3s init
terraform -chdir=terraform/aws-ec2-k3s fmt
terraform -chdir=terraform/aws-ec2-k3s validate
terraform -chdir=terraform/aws-ec2-k3s apply
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

Set `ssh_private_key_file` in `terraform/user.tfvars` when the EC2 key pair
does not use your default SSH key. Terraform includes that path in both:

- `ansible_ssh_private_key_file` in the generated inventory
- the `ssh_command` output as `ssh -i <keypath> ubuntu@<host-ip>`

Set `ec2_pull_github_keys = ["<github-user>"]` in `terraform/user.tfvars` only
when the instance should pull public GitHub SSH keys into
`/home/ubuntu/.ssh/authorized_keys` during first boot. Leave it empty to skip.
This requires the instance to reach GitHub during cloud-init and does not
re-run automatically on an existing instance.

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
`ansible/group_vars/ports.generated.yml` plus
`ansible/group_vars/terraform.generated.yml` for Ansible. The Terraform bridge
file carries AWS profile, region, SSH key details, trusted CIDRs, and k3s host
facts into Ansible. The default generated HTTP ports are reserved consistently:
Open WebUI uses `30080` when enabled, custom chatbot `30081`, demo home
`30082`, LiteLLM Admin/API `30083`, and MCP demo tools `30084`. The optional
HTTPS gateway uses matching offsets: `30443`, `30444`, `30445`, `30446`, and
`30447`.

`additional_ingress_tcp_ports` is only for extra public TCP listeners beyond
those generated demo ports.

The EC2 module also queries AWS Price List data for the configured
`instance_type` and `aws_region` and outputs an estimated Linux On-Demand
shared-tenancy compute cost:

```bash
terraform -chdir=terraform/aws-ec2-k3s output ec2_instance_hourly_cost_usd
terraform -chdir=terraform/aws-ec2-k3s output ec2_instance_monthly_cost_usd
terraform -chdir=terraform/aws-ec2-k3s output ec2_instance_pricing_location
```

The monthly estimate is `hourly * 30 * 24`. It excludes EBS, EIP idle charges,
data transfer, Bedrock, marketplace, and licensing costs. If AWS adds a region
that is not in the module's built-in pricing-location map, set
`aws_pricing_location_override` in `99-local.auto.tfvars`.

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

See [AWS Instance Sizing](aws-instance.md) for the detailed table separating
test infrastructure, supported validation infrastructure, and experimental
instance families.
