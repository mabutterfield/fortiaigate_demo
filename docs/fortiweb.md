# FortiWeb Appliance

FortiWeb is an appliance path enabled by default for the full AWS demo. The
deployment lives in `terraform/aws-fortiweb` so it can still be disabled with
local overrides when the public k3s-only demo is desired.

Deployment shape:

- `terraform/aws-prep` can allocate the FortiWeb EIP.
- `terraform/aws-prep` can create a private encrypted S3 bucket for FortiWeb
  cloud-init config and license objects when `fortiweb_enabled = true`.
- `terraform/aws-prep` can create an EC2 instance profile that allows FortiWeb
  to read those S3 objects.
- `terraform/aws-ec2-k3s` creates FortiWeb public and internal subnets.
- `terraform/aws-fortiweb` deploys FortiWeb EC2, public/internal ENIs,
  security groups, the prep-owned EIP association, S3 cloud-init objects, and
  management outputs.
- Ansible configures management settings, port2, static routes, traffic
  logging, and pass-through reverse-proxy policies for the generated NodePorts.

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
- The generated command file sets hostname, `admin-sport`, `admintimeout`, and
  disables the FortiWeb admin password policy.
- `fortiweb_admin_console_timeout_seconds = 3600` is the default 60-minute
  timeout and renders as `set admintimeout 60`.
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

Set `fortiweb_license_mode = "fortiflex_token"` and
`fortiweb_fortiflex_token` in ignored `terraform/aws-fortiweb/99-local.auto.tfvars`
to inject a FortiFlex token through JSON cloud-init as `Flex_token`. Token
changes replace the FortiWeb EC2 instance. Before tainting/rebuilding a
FortiFlex-licensed instance, clear or replace the token so the next build
consumes a fresh token.

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

If the `admin` password was changed manually or by a previous GUI first-login
flow, set an ignored Ansible override instead of retrying with stale
credentials:

```yaml
fortiweb_admin_password_override: "<current-admin-password>"
```

Put that only in ignored `ansible/group_vars/user.yml` or pass it with
`-e @/path/to/local-secret.yml`. Repeated failed API logins can trigger the
FortiWeb lockout message `Too many bad login attempts or reached max number of
logins`; wait for the lockout window to clear before rerunning Ansible.

`configure_fortiweb.yml` currently manages the narrow baseline:

- system admin settings: hostname, HTTP/HTTPS management ports, and admin idle
  timeout
- port2 internal interface IP from the Terraform-created FortiWeb internal ENI
- static route ID `1`: default route through port1's gateway
- static route ID `2`: VPC route through port2's internal subnet gateway
- generated reverse-proxy framework without MCP inspection: service,
  virtual server, server pool, pool member, and server policy for all demo HTTP
  NodePorts and, when `demo_https_gateway_enabled = true`, all demo HTTPS
  NodePorts

The generated FortiWeb command file disables `system password-policy` and sets
`force-password-change disable` for the default `admin` account so future builds
can be automated without an interactive first-login password change. FortiWeb
cloud images can enable password policy by default; when enabled, admins whose
passwords do not meet policy are prompted to change password on login even if
the per-admin force flag is disabled. Changing this template does not replace
the current FortiWeb instance unless Terraform is applied in a way that
recreates it.

The Ansible `fwebos_admin` task is disabled by default through
`fortiweb_config_enable_admin_user=false`. The FortiWeb collection module reads
the admin object and sends a full-object update back to FortiWeb. On first-boot
default-admin accounts this can disturb the default instance-ID password even
when the playbook does not explicitly set a password.

The generated FortiWeb NodePort proxy chain is enabled in repo system defaults
with `fortiweb_mcp_proxy_enabled: true`. Override it in ignored
`ansible/group_vars/user.yml` only when you want to skip FortiWeb listener and
server-policy creation:

```yaml
fortiweb_mcp_proxy_enabled: false
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

Do not commit FortiFlex tokens, license files, rendered user-data, real
`99-local.auto.tfvars`, S3 object copies containing license data, FortiWeb admin
passwords, or Terraform state.
