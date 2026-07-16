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
3. Leave the tracked `fortigate_enabled = true` default in place, or override it
   in ignored `99-local.auto.tfvars`.
4. Apply this module.

```bash
cd terraform/aws-fortigate
terraform init
terraform fmt
terraform validate
terraform apply
```

Copy `99-local.auto.tfvars.example` to `99-local.auto.tfvars` only when
overriding the tracked defaults in `00-system.auto.tfvars`, such as license
file names or instance size.

The FortiGate initial admin password is the EC2 instance ID. The generated API
key and any BYOL license content passed through user-data are stored in local
Terraform state.

The default HTTPS admin port is `443`. Set `fortigate_admin_port = 8443` in
ignored `99-local.auto.tfvars` when you want the alternate management port.
The default admin idle timeout is 60 minutes. Override it with
`fortigate_admin_timeout_minutes` when needed.

For BYOL testing, set `fortigate_license_source_dir` and
`fortigate_license_file_name` in ignored `99-local.auto.tfvars` to a real FortiGate
license under the parent workspace `licenses/` directory. The committed
placeholder file name is `FGVMSLTM00000000.lic`. `fortigate_license_file`
remains available as a full-path compatibility override.

Useful outputs:

```bash
terraform output fortigate_admin_url
terraform output fortigate_instance_id
terraform output -raw fortigate_api_key
```

Do not commit real `99-local.auto.tfvars`, license files, rendered user-data, or
Terraform state.
