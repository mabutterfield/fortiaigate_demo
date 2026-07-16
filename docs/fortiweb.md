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

For BYOL testing, set `fortiweb_license_source_dir` and
`fortiweb_license_file_name` in ignored `terraform/aws-fortiweb/99-local.auto.tfvars`
to a real FortiWeb license under the parent workspace `licenses/` directory.
The committed placeholder file name is `FWBVMSTM00000000.lic`. Terraform uploads
the license by source path, not by embedding the license text in Terraform
configuration. Set `fortiweb_license_mode = "none"` for an unlicensed boot test.
`fortiweb_license_file` remains available as a full-path compatibility override.

The tracked `00-system.auto.tfvars` sets `fortiweb_enabled = true`. Set it to
false in ignored `99-local.auto.tfvars` only when you want to keep the module
prepared but skip creating FortiWeb resources.

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

The FortiWeb module also writes generated Ansible inventory to:

```text
ansible/inventory/fortiweb.generated.ini
```

Install the pinned Fortinet Ansible collections before running appliance
playbooks:

```bash
ansible-galaxy collection install -r ansible/collections/requirements.yml
```

Then poll FortiWeb status from the repo root:

```bash
ansible-playbook -i ansible/inventory/fortiweb.generated.ini ansible/playbooks/status_fortiweb.yml
```

Configure the FortiWeb baseline from the repo root:

```bash
ansible-playbook -i ansible/inventory/fortiweb.generated.ini ansible/playbooks/configure_fortiweb.yml
```

The status playbook reads Terraform outputs at runtime. It uses
`fortiweb_admin_password` when `fortiweb_set_initial_password = true`;
otherwise it uses the FortiWeb EC2 instance ID as the default admin password.
The generated inventory does not contain the admin password.

`configure_fortiweb.yml` currently manages the narrow baseline:

- system admin settings: hostname, HTTP/HTTPS management ports, and admin idle
  timeout
- default `admin` account `force-password-change disable`
- port2 internal interface IP from the Terraform-created FortiWeb internal ENI
- static route ID `1`: default route through port1's gateway
- static route ID `2`: VPC route through port2's internal subnet gateway
- optional generated reverse-proxy framework without MCP inspection: service,
  virtual server, server pool, pool member, and server policy for all demo HTTP
  NodePorts and, when `demo_https_gateway_enabled = true`, all demo HTTPS
  NodePorts

The generated FortiWeb command file sets `force-password-change disable` for
the default `admin` account so future builds can be automated without an
interactive first-login password change. Changing this template does not replace
the current FortiWeb instance unless Terraform is applied in a way that
recreates it.

The generated FortiWeb NodePort proxy chain is disabled by default. Enable it in
ignored `ansible/group_vars/user.yml` when the intended traffic path is ready:

```yaml
fortiweb_mcp_proxy_enabled: true
```

This creates no-inspection reverse proxies using the FortiWeb collection's
existing server-policy resources. HTTP listeners use the generated HTTP
NodePorts. HTTPS listeners use FortiWeb reverse-proxy SSL on the front end and
SSL-enabled server-pool members on the back end. Listener and backend ports
match by default.

FortiWeb 8.0.3+ MCP Security appears to use
`/api/v2.0/cmdb/waf/mcp-security.policy`, but the pinned collection does not
currently expose a module for that object. When the full REST schema is known,
add it as an explicit gather/compare/apply object rather than relying on
collection-side defaults.

Do not commit license files, rendered user-data, real `99-local.auto.tfvars`, S3
object copies containing license data, FortiWeb admin passwords, or Terraform
state.
