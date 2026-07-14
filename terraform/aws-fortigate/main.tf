data "terraform_remote_state" "aws_prep" {
  backend = "local"

  config = {
    path = var.aws_prep_state_path
  }
}

data "terraform_remote_state" "aws_ec2_k3s" {
  backend = "local"

  config = {
    path = var.aws_ec2_k3s_state_path
  }
}

locals {
  prep_outputs = data.terraform_remote_state.aws_prep.outputs
  k3s_outputs  = data.terraform_remote_state.aws_ec2_k3s.outputs

  tags = merge(
    {
      Project   = "FortiAIGate Demo"
      Managed   = "terraform"
      Component = "FortiGate"
    },
    var.tags
  )
}
