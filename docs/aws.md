# AWS

AWS infrastructure is split across three user-facing Terraform folders:

- `terraform/aws-ecr`: private ECR repositories and generated Ansible ECR vars
- `terraform/aws-prep`: IAM roles, ECR pull permissions, EIPs, trusted source CIDRs, and optional Bedrock IAM credentials
- `terraform/aws-ec2-k3s`: VPC, subnets, security group, EC2 k3s host, EIP association, and generated Ansible inventory

Shared values live in `terraform/common.tfvars`.

## Trusted Source CIDRs

`allowed_ingress_cidr` in `terraform/common.tfvars` accepts either one CIDR
string or a list of CIDR strings. Use `/32` entries for individual public IPs.

```hcl
allowed_ingress_cidr = [
  "203.0.113.10/32",
  "198.51.100.25/32",
]
```

The AWS prep module exports the normalized list to the EC2 module. The EC2
security group uses that list for SSH, HTTP, HTTPS, and configured demo
NodePorts.

## More Detail

- [Terraform Reference](terraform.md)
- [AWS k3s Foundation](aws-k3s-foundation.md)
- [AWS Instance Sizing](aws_instance.MD)
