# FortiGate Appliance

FortiGate is an optional Phase 4 appliance. The deployment lives in
`terraform/aws-fortigate` so it does not affect the default public k3s demo.

Phase 4 deployment status:

- `terraform/aws-prep` can allocate the FortiGate EIP.
- `terraform/aws-ec2-k3s` creates FortiGate public and internal subnets.
- `terraform/aws-fortigate` deploys a FortiGate EC2 instance with two ENIs.

FortiGate shape:

- public/management ENI in `subnet_ids.fortigate_public`
- internal ENI in `subnet_ids.fortigate_internal`
- prep-owned FortiGate EIP association
- BYOL license file support from ignored local files
- generated API key marked sensitive in Terraform outputs

Apply order:

```bash
cd terraform/aws-prep
terraform apply

cd ../aws-ec2-k3s
terraform apply

cd ../aws-fortigate
terraform apply
```

Make sure `terraform/aws-prep/99-local.auto.tfvars` enables the FortiGate EIP:

```hcl
allocate_eips = {
  k3s       = true
  fortigate = true
  fortiweb  = true
}
```

The tracked `00-system.auto.tfvars` sets `fortigate_enabled = true`. Set it to
false in ignored `99-local.auto.tfvars` only when you want to keep the module
prepared but skip creating FortiGate resources.

After apply, use:

```bash
terraform output fortigate_admin_url
terraform output fortigate_instance_id
terraform output -raw fortigate_api_key
```

The FortiGate module also writes generated Ansible inventory to:

```text
ansible/inventory/fortigate.generated.ini
```

Install the pinned Fortinet Ansible collections before running appliance
playbooks:

```bash
ansible-galaxy collection install -r ansible/collections/requirements.yml
```

Then poll FortiGate status from the repo root:

```bash
ansible-playbook -i ansible/inventory/fortigate.generated.ini ansible/playbooks/status_fortigate.yml
```

Configure the FortiGate baseline from the repo root:

```bash
ansible-playbook -i ansible/inventory/fortigate.generated.ini ansible/playbooks/configure_fortigate.yml
```

Create/update FortiGate API profiles and application API accounts:

```bash
ansible-playbook -i ansible/inventory/fortigate.generated.ini ansible/playbooks/configure_fortigate_api_accounts.yml
```

The status and config playbooks read `fortigate_api_key` from
`terraform/aws-fortigate` at runtime and do not write the token to generated
Ansible vars.

`configure_fortigate.yml` manages:

- system global settings such as admin timeout, banner/disclaimer cleanup, GUI
  first-run warning cleanup, and disabling the wireless controller
- system feature visibility settings such as ICAP, multiple-interface policies,
  SD-WAN, DoS policy, video filter, threat weight, and traffic shaping
- admin password policy settings
- FortiGuard automatic patch firmware upgrade setting
- static FortiGate address objects generated from repo-owned public/private IPs
- generated custom service objects for the demo k3s NodePort listeners
- optional static address objects, static service objects, VIP objects, and
  firewall policies

System maps are pushed as one map. Address objects, service objects, VIP
objects, and firewall policies are gathered from FortiGate first and only
applied when the desired object differs. Static object variables in ignored
`ansible/group_vars/user.yml` are merged after repo-generated objects by `name`,
so a static object can add a new object or override a generated one. Inbound
NAT policies should define the VIP in `fortigate_vip_objects_static`, then
reference that VIP name in the firewall policy `dstaddr`.

`configure_fortigate_api_accounts.yml` creates a managed read-only profile
named `FAIG_READ_ONLY` and a read-only API admin named `faig-readonly-api` by
default. FortiGate only returns a generated API key once, so the play stores the
generated key in the ignored local file:

```text
ansible/secrets/fortigate_api.generated.yml
```

The file is written with `0600` permissions and `ansible/secrets/` is ignored by
Git. Re-running the play reuses the local copy and does not regenerate the key.
Set `fortigate_readonly_api_account_rotate_token: true` in ignored
`ansible/group_vars/user.yml` only when you intentionally want to rotate and
replace the stored key.

The bootstrap `apiadmin` account is restricted to the user-provided
`allowed_ingress_cidr` CIDRs. The FAIG read-only API account defaults to those
same CIDRs plus the VPC CIDR so internal demo applications can query FortiGate.
The FortiGate cloud-init template also seeds bootstrap `apiadmin` trusted hosts
for future rebuilds; changing the template alone does not replace the current
instance.

The default username is `admin`. The initial admin password is the FortiGate
EC2 instance ID.

The default HTTPS admin port is `8443`. Set `fortigate_admin_port = 443` in
ignored `99-local.auto.tfvars` when you want the standard HTTPS management port.
The default admin idle timeout is 60 minutes through
`fortigate_admin_timeout_minutes`.

Do not commit license files, rendered user-data, real `99-local.auto.tfvars`, or
Terraform state.
