# AWS FortiGate Terraform Module

This Phase 4 module will deploy the optional FortiGate appliance. It is
scaffolded separately from `terraform/aws-ec2-k3s` so appliance deployment does
not become required for the default public k3s demo.

Phase 4 Step 3 will add:

- FortiGate Marketplace AMI lookup
- public and internal ENIs
- prep-owned EIP association
- FortiGate cloud-init bootstrap
- optional BYOL license file injection
- generated API key output marked sensitive

Run order after Step 3 is implemented:

```bash
cd terraform/aws-fortigate
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt
terraform validate
terraform apply
```

Do not commit real `terraform.tfvars`, license files, rendered user-data, or
Terraform state.
