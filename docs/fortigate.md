# FortiGate Appliance

FortiGate is an optional Phase 4 appliance. The deployment lives in
`terraform/aws-fortigate` so it does not affect the default public k3s demo.

Phase 1 status:

- `terraform/aws-prep` can allocate the FortiGate EIP.
- `terraform/aws-ec2-k3s` creates FortiGate public and internal subnets.
- `terraform/aws-fortigate` is scaffolded, but EC2/ENI/cloud-init resources are
  intentionally deferred to the FortiGate deployment phase.

Planned FortiGate shape:

- public/management ENI in `subnet_ids.fortigate_public`
- internal ENI in `subnet_ids.fortigate_internal`
- prep-owned FortiGate EIP association
- BYOL license file support from ignored local files
- generated API key marked sensitive in Terraform outputs

Do not commit license files, rendered user-data, real `terraform.tfvars`, or
Terraform state.
