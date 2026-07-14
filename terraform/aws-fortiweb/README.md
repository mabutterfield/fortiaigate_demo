# AWS FortiWeb Terraform Module

This Phase 4 module will deploy the optional FortiWeb appliance. It is
scaffolded separately from `terraform/aws-ec2-k3s` so appliance deployment does
not become required for the default public k3s demo.

Phase 4 Step 4 will add:

- FortiWeb Marketplace AMI lookup
- public and internal ENIs
- prep-owned EIP association
- S3-backed FortiWeb cloud-init user-data
- optional BYOL license object upload
- FortiWeb management/API outputs

FortiWeb cloud-init reads its config and license from the S3 bucket created by
`terraform/aws-prep` when `fortiweb_enabled = true` there. The EC2 instance
must use the prep-owned FortiWeb instance profile so it can read those objects.

Run order after Step 4 is implemented:

```bash
cd terraform/aws-fortiweb
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt
terraform validate
terraform apply
```

Do not commit real `terraform.tfvars`, license files, rendered user-data, or
Terraform state.
