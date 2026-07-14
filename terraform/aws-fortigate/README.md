# AWS FortiGate Terraform Module

This Phase 4 module deploys the optional FortiGate appliance. It is separate
from `terraform/aws-ec2-k3s` so appliance deployment does not become required
for the default public k3s demo.

This module creates:

- FortiGate Marketplace AMI lookup
- public and internal ENIs
- prep-owned EIP association
- FortiGate cloud-init bootstrap
- optional BYOL license file injection
- generated API key output marked sensitive

Run order:

1. Apply `terraform/aws-prep` with `allocate_eips.fortigate = true`.
2. Apply `terraform/aws-ec2-k3s` so the FortiGate public/internal subnets exist.
3. Set `fortigate_enabled = true` in this module's ignored `terraform.tfvars`.
4. Apply this module.

```bash
cd terraform/aws-fortigate
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt
terraform validate
terraform apply
```

The FortiGate initial admin password is the EC2 instance ID. The generated API
key and any BYOL license content passed through user-data are stored in local
Terraform state.

The default HTTPS admin port is `443`. Set `fortigate_admin_port = 8443` in
ignored `terraform.tfvars` when you want the alternate management port.
The default admin idle timeout is 60 minutes. Override it with
`fortigate_admin_timeout_minutes` when needed.

Useful outputs:

```bash
terraform output fortigate_admin_url
terraform output fortigate_instance_id
terraform output -raw fortigate_api_key
```

Do not commit real `terraform.tfvars`, license files, rendered user-data, or
Terraform state.
