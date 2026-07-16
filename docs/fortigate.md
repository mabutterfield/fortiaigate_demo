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

The default username is `admin`. The initial admin password is the FortiGate
EC2 instance ID.

The default HTTPS admin port is `8443`. Set `fortigate_admin_port = 443` in
ignored `99-local.auto.tfvars` when you want the standard HTTPS management port.
The default admin idle timeout is 60 minutes through
`fortigate_admin_timeout_minutes`.

Do not commit license files, rendered user-data, real `99-local.auto.tfvars`, or
Terraform state.
