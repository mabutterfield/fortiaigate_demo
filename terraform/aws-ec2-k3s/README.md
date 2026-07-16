# AWS EC2 k3s Terraform Module

This module creates the phase 1 AWS EC2/k3s lab infrastructure and writes the generated Ansible inventory and demo port vars.

Canonical documentation:

- [../../docs/terraform.md](../../docs/terraform.md)
- [../../docs/aws-k3s-foundation.md](../../docs/aws-k3s-foundation.md)
- [../../docs/deployment-runbook.md](../../docs/deployment-runbook.md)

Quick usage:

```bash
aws sso login --profile <profile-name>
terraform init
terraform fmt
terraform validate
terraform apply
```

Copy `99-local.auto.tfvars.example` to `99-local.auto.tfvars` only when
overriding the tracked defaults in `00-system.auto.tfvars`.

The generated inventory is written to `../../ansible/inventory/aws.generated.ini`.

Set `ssh_private_key_file` in `99-local.auto.tfvars` when the EC2 key pair does not use your default SSH key. Terraform uses that value in both the generated Ansible inventory and the `ssh_command` output.

Set `ec2_pull_github_keys = ["<github-user>"]` only when the instance should
pull public GitHub SSH keys into `/home/ubuntu/.ssh/authorized_keys` during
first boot. Leave it empty to skip.

Leave `availability_zone = ""` to let Terraform select the first sorted AZ that offers `instance_type`. Set it explicitly when AWS recommends a specific AZ.

The default network mode remains direct public k3s access:

```hcl
k3s_subnet_mode = "public"
```

This creates the k3s public subnet, a k3s private subnet, FortiGate and
FortiWeb public management subnets, FortiGate and FortiWeb internal subnets,
and places the k3s instance in the public subnet with the EIP preallocated by
`terraform/aws-prep`. The k3s instance does not request an auto-assigned
ephemeral public IP. Set `k3s_subnet_mode = "private"` only after a private
management or appliance-fronted access path exists. Private mode places k3s in
the private subnet without a public IP.

For future appliance-fronted private mode, set `k3s_private_default_route_network_interface_id` to the FortiGate traffic interface that should receive the private subnet default route.

Phase 2 routing placeholders are defined but do not create DNS records yet:

```hcl
ingress_routing_strategy = "port_based"
ingress_base_domain      = ""
route53_zone_id          = ""
create_route53_records   = false
magic_dns_zone           = "sslip.io"
```

`port_based` matches the current generated NodePort demo. `path_based` is reserved for a future single-host ingress path layout. `host_based` is reserved for future Route53, enterprise DNS, hosts-file, or magic-DNS backed demos.

`terraform/aws-prep` creates the EC2 IAM role/profile, scoped ECR pull permissions, trusted source CIDR, and public EIP. This module reads those values from `aws_prep_state_path`.

This module generates the standard demo port assignments, opens those ports in
the EC2 security group, and writes `../../ansible/group_vars/ports.generated.yml`
and `../../ansible/group_vars/terraform.generated.yml` for Ansible. The default
HTTP ports are `30080` through `30084`; the optional HTTPS gateway uses matching
offsets starting at `30443`.

The default instance type is `g4dn.4xlarge`. Use `g6.8xlarge` for a stronger production-like L4 validation target.

After apply, validate host status and SSH:

```bash
AWS_PROFILE="$(terraform output -raw aws_profile)"
AWS_REGION="$(terraform output -raw aws_region)"
INSTANCE_ID="$(terraform output -raw instance_id)"

aws ec2 describe-instance-status \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --instance-ids "$INSTANCE_ID" \
  --include-all-instances \
  --query 'InstanceStatuses[0].{Instance:InstanceState.Name,System:SystemStatus.Status,InstanceStatus:InstanceStatus.Status}' \
  --output table
```

Get the SSH command:

```bash
terraform output ssh_command
```
