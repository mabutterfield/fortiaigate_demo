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
`fortiweb_enabled = true` is tracked in this module's `00-system.auto.tfvars`
for the full demo. Override it in ignored `99-local.auto.tfvars` only when you
want to disable or customize the appliance.

For BYOL testing, set `fortiweb_license_source_dir` and
`fortiweb_license_file_name` in ignored `99-local.auto.tfvars` to a real FortiWeb
license under the parent workspace `licenses/` directory. The committed
placeholder file name is `FWBVMSTM00000000.lic`. The license object is uploaded
to S3 by path; Terraform state should not contain the license file content.
`fortiweb_license_file` remains available as a full-path compatibility override.

The AWS account must be subscribed to the selected FortiWeb Marketplace AMI
before EC2 launch. If apply fails with `OptInRequired`, accept the Marketplace
terms for the listed SKU and rerun `terraform apply`.

The default AMI filter is FortiWeb `8.0`, which selects the latest matching
8.0.x BYOL Marketplace image.

By default, the module also opens the generated demo NodePorts on the FortiWeb
public ENI from the prep-generated trusted public CIDRs and from the VPC CIDR:
TCP `30080` through `30084` for HTTP and TCP `30443` through `30447` for the
optional HTTPS gateway. Override `fortiweb_data_plane_tcp_ports` in ignored
`99-local.auto.tfvars` when the generated listener ports change.

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
terraform init
terraform fmt
terraform validate
terraform apply
```

Copy `99-local.auto.tfvars.example` to `99-local.auto.tfvars` only when
overriding the tracked defaults in `00-system.auto.tfvars`, such as license
file names or instance size.

Useful outputs:

```bash
terraform output fortiweb_admin_url
terraform output fortiweb_ssh_command
terraform output fortiweb_instance_id
```

This module also writes:

```text
../../ansible/inventory/fortiweb.generated.ini
```

From the repo root, poll FortiWeb with:

```bash
ansible-playbook -i ansible/inventory/fortiweb.generated.ini ansible/playbooks/status_fortiweb.yml
```

Configure the FortiWeb baseline with:

```bash
ansible-playbook -i ansible/inventory/fortiweb.generated.ini ansible/playbooks/configure_fortiweb.yml
```

The FortiWeb Ansible config role can also create an optional no-inspection MCP
reverse-proxy chain. Enable `fortiweb_mcp_proxy_enabled` in ignored
`ansible/group_vars/user.yml` after the desired data-plane listener path is
confirmed.

The generated inventory contains appliance connection facts but not the admin
password. The status playbook reads Terraform outputs at runtime and uses
`fortiweb_admin_password` when `fortiweb_set_initial_password = true`, otherwise
it uses the EC2 instance ID as the default admin password.

Do not commit real `99-local.auto.tfvars`, license files, rendered user-data, or
Terraform state.
