# FortiWeb Appliance

FortiWeb is an optional Phase 4 appliance. The deployment lives in
`terraform/aws-fortiweb` so it does not affect the default public k3s demo.

Phase 4 deployment shape:

- `terraform/aws-prep` can allocate the FortiWeb EIP.
- `terraform/aws-prep` can create a private encrypted S3 bucket for FortiWeb
  cloud-init config and license objects when `fortiweb_enabled = true`.
- `terraform/aws-prep` can create an EC2 instance profile that allows FortiWeb
  to read those S3 objects.
- `terraform/aws-ec2-k3s` creates FortiWeb public and internal subnets.
- `terraform/aws-fortiweb` deploys FortiWeb EC2, public/internal ENIs,
  security groups, the prep-owned EIP association, S3 cloud-init objects, and
  management outputs.

FortiWeb user-data is S3-backed. The Fortinet cloud-init shape is:

```json
{
  "cloud-initd": "enable",
  "bucket": "the-bucket-containing-the-command-file",
  "region": "the-region-of-the-bucket",
  "initial_passwd": "base64-encoded-initial-admin-password",
  "license": "the-path-of-the-license-file-in-the-bucket",
  "config": "the-path-of-the-command-file-in-the-bucket"
}
```

Default command-file behavior:

- `fortiweb_config_file = ""` uploads a generated command file.
- The generated command file sets hostname, `admin-sport`, and
  `admin-console-timeout`.
- `fortiweb_admin_console_timeout_seconds = 3600` is the default 60-minute
  timeout.
- `fortiweb_set_initial_password = false` omits `initial_passwd` from user-data
  and uses the EC2 instance ID as the initial admin password.
- Set `fortiweb_set_initial_password = true` to pass an explicit generated or
  operator-provided initial admin password.

For BYOL testing, set `fortiweb_license_file` in ignored
`terraform/aws-fortiweb/terraform.tfvars` to a real FortiWeb license under the
parent workspace `licenses/` directory. The committed placeholder path is
`../../../licenses/FWBVMSTM00000000.lic`. Terraform uploads the license by source
path, not by embedding the license text in Terraform configuration. Set
`fortiweb_license_mode = "none"` for an unlicensed boot test.

The committed example sets `fortiweb_enabled = true`. Set it to false in
ignored local tfvars only when you want to keep the module prepared but skip
creating FortiWeb resources.

The AWS account must be subscribed to the selected FortiWeb Marketplace AMI
before EC2 launch. If Terraform returns `OptInRequired`, accept the Marketplace
terms for the SKU in the error message and rerun `terraform apply`.

The default AMI filter is FortiWeb `8.0`, which selects the latest matching
8.0.x BYOL Marketplace image.

The default instance type is `c5.xlarge`. FortiWeb Marketplace images support
the `t3`, `m5`, `m4`, `c5`, and `c4` families; `c6i` is rejected by EC2 for
the current FortiWeb 8.0 BYOL image.

Useful validation outputs:

```bash
cd terraform/aws-fortiweb
terraform output fortiweb_admin_url
terraform output fortiweb_ssh_command
terraform output fortiweb_instance_id
```

Do not commit license files, rendered user-data, real `terraform.tfvars`, S3
object copies containing license data, FortiWeb admin passwords, or Terraform
state.
