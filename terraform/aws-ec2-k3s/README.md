# AWS EC2 k3s Terraform Module

This module creates the phase 1 AWS EC2/k3s lab infrastructure and writes the generated Ansible inventory.

Canonical documentation:

- [../../docs/terraform.md](../../docs/terraform.md)
- [../../docs/aws-k3s-foundation.md](../../docs/aws-k3s-foundation.md)
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

The generated inventory is written to `../../ansible/inventory/aws.generated.ini`.

Set `ssh_private_key_file` in `terraform.tfvars` when the EC2 key pair does not use your default SSH key. Terraform uses that value in both the generated Ansible inventory and the `ssh_command` output.

Leave `availability_zone = ""` to let Terraform select the first sorted AZ that offers `instance_type`. Set it explicitly when AWS recommends a specific AZ.

Set `create_iam_instance_profile = true` when this module should create the EC2 IAM role and instance profile. Use the `iam_role_name` output as the input for ECR pull permissions.

This module also outputs `public_ip` and `allowed_ingress_cidr`; the Bedrock module reads those values from local Terraform state to build its source IP restriction by default.

The default instance type is `g4dn.4xlarge`. Use `g6.8xlarge` for a stronger production-like L4 validation target.

After apply, validate host status and SSH:

```bash
terraform output ssh_command
aws ec2 describe-instance-status \
  --profile <profile-name> \
  --region <region> \
  --instance-ids "$(terraform output -raw instance_id)" \
  --include-all-instances \
  --query 'InstanceStatuses[0].{Instance:InstanceState.Name,System:SystemStatus.Status,InstanceStatus:InstanceStatus.Status}' \
  --output table
```
