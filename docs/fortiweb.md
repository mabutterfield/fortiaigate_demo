# FortiWeb Appliance

FortiWeb is an optional Phase 4 appliance. The deployment lives in
`terraform/aws-fortiweb` so it does not affect the default public k3s demo.

Phase 1 status:

- `terraform/aws-prep` can allocate the FortiWeb EIP.
- `terraform/aws-prep` can create a private encrypted S3 bucket for FortiWeb
  cloud-init config and license objects when `fortiweb_enabled = true`.
- `terraform/aws-prep` can create an EC2 instance profile that allows FortiWeb
  to read those S3 objects.
- `terraform/aws-ec2-k3s` creates FortiWeb public and internal subnets.
- `terraform/aws-fortiweb` is scaffolded, but EC2/ENI/cloud-init resources are
  intentionally deferred to the FortiWeb deployment phase.

FortiWeb user-data is S3-backed. The Fortinet cloud-init shape is:

```json
{
  "cloud-initd": "enable",
  "bucket": "the-bucket-containing-the-command-file",
  "region": "the-region-of-the-bucket",
  "license": "the-path-of-the-license-file-in-the-bucket",
  "config": "the-path-of-the-command-file-in-the-bucket"
}
```

Planned FortiWeb shape:

- public/management ENI in `subnet_ids.fortiweb_public`
- internal ENI in `subnet_ids.fortiweb_internal`
- prep-owned FortiWeb EIP association
- S3-backed BYOL license and command/config delivery
- admin/API outputs for manual validation

Do not commit license files, rendered user-data, real `terraform.tfvars`, S3
object copies containing license data, or Terraform state.
