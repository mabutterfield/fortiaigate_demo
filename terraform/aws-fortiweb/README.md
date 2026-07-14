# AWS FortiWeb Terraform Module

This Phase 4 module deploys the optional FortiWeb appliance. It is separate
from `terraform/aws-ec2-k3s` so appliance deployment does not become required
for the default public k3s demo.

It creates:

- FortiWeb Marketplace AMI lookup
- public and internal ENIs
- prep-owned EIP association
- S3-backed FortiWeb cloud-init user-data
- optional BYOL license object upload
- FortiWeb management/API outputs

FortiWeb cloud-init reads its config and license from the S3 bucket created by
`terraform/aws-prep` when `fortiweb_enabled = true` there. The EC2 instance
uses the prep-owned FortiWeb instance profile so it can read those objects.
Set `fortiweb_enabled = true` in this module's ignored `terraform.tfvars` when
you want to deploy the appliance.

For BYOL testing, set `fortiweb_license_file` in ignored `terraform.tfvars` to
a real FortiWeb license under the parent workspace `licenses/` directory. The
committed placeholder path is `../../../licenses/FWBVMSTM00000000.lic`. The license
object is uploaded to S3 by path; Terraform state should not contain the
license file content. Terraform state will contain the generated FortiWeb admin
password.

The AWS account must be subscribed to the selected FortiWeb Marketplace AMI
before EC2 launch. If apply fails with `OptInRequired`, accept the Marketplace
terms for the listed SKU and rerun `terraform apply`.

The default AMI filter is FortiWeb `8.0`, which selects the latest matching
8.0.x BYOL Marketplace image.

The default instance type is `c5.xlarge`. FortiWeb Marketplace images support
the `t3`, `m5`, `m4`, `c5`, and `c4` families; `c6i` is rejected by EC2 for
the current FortiWeb 8.0 BYOL image.

When `fortiweb_config_file = ""`, this module uploads a generated command file
that sets the hostname, HTTPS admin port, and admin console timeout. Provide a
local command file path only when you want to override that generated baseline.

By default, `fortiweb_set_initial_password = false`, so the FortiWeb user-data
does not include `initial_passwd`. In this mode, the initial admin password is
the FortiWeb EC2 instance ID. Set `fortiweb_set_initial_password = true` to
pass an explicit generated or operator-provided initial password.

Run order:

```bash
cd terraform/aws-fortiweb
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt
terraform validate
terraform apply
```

Useful outputs:

```bash
terraform output fortiweb_admin_url
terraform output fortiweb_ssh_command
terraform output fortiweb_instance_id
```

Do not commit real `terraform.tfvars`, license files, rendered user-data, or
Terraform state.
