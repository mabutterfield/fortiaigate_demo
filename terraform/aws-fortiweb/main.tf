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
  allowed_ingress_cidrs = distinct([
    for cidr in(
      can(tolist(var.allowed_ingress_cidr))
      ? tolist(var.allowed_ingress_cidr)
      : [tostring(var.allowed_ingress_cidr)]
    ) : trimspace(cidr)
    if trimspace(cidr) != ""
  ])
  effective_allowed_ingress_cidrs = try(
    local.prep_outputs.allowed_ingress_cidrs,
    local.allowed_ingress_cidrs
  )
  fortiweb_eip_allocation_id = try(local.prep_outputs.fortiweb_eip_allocation_id, null)
  fortiweb_eip_public_ip = try(coalesce(
    try(local.prep_outputs.fortiweb_eip_public_ip, null),
    try(local.prep_outputs.fortiweb_public_ip, null)
  ), null)
  fortiweb_cloudinit_bucket_name = try(local.prep_outputs.fortiweb_cloudinit_bucket_name, null)
  fortiweb_cloudinit_config_key  = try(local.prep_outputs.fortiweb_cloudinit_config_key, null)
  fortiweb_cloudinit_license_key = try(local.prep_outputs.fortiweb_cloudinit_license_key, null)
  fortiweb_instance_profile_name = try(local.prep_outputs.fortiweb_cloudinit_instance_profile_name, null)
  fortiweb_shared_prep_ready     = local.fortiweb_cloudinit_bucket_name != null && local.fortiweb_cloudinit_config_key != null && local.fortiweb_instance_profile_name != null
  vpc_id                         = local.k3s_outputs.vpc_id
  vpc_cidr                       = local.k3s_outputs.network_cidrs.aws_vpc_cidr
  fortiweb_public_subnet_id      = local.k3s_outputs.subnet_ids.fortiweb_public
  fortiweb_internal_subnet_id    = local.k3s_outputs.subnet_ids.fortiweb_internal
  fortiweb_name                  = "${var.name_prefix}-fortiweb"
  fortiweb_license_pay_type      = var.fortiweb_license_type == "byol" ? "_BYOL" : "_OnDemand"
  fortiweb_ami_name_values = var.fortiweb_ami_name_override != "" ? [
    var.fortiweb_ami_name_override
    ] : [
    "*FortiWeb-AWS-*${var.fortiweb_version}*${local.fortiweb_license_pay_type}*",
  ]
  fortiweb_generated_config = templatefile("${path.module}/templates/fortiweb-config.conf.tftpl", {
    hostname                      = local.fortiweb_name
    admin_https_port              = var.fortiweb_admin_https_port
    admin_console_timeout_seconds = var.fortiweb_admin_console_timeout_seconds
  })
  fortiweb_admin_password = var.fortiweb_set_initial_password ? (var.fortiweb_admin_password != "" ? var.fortiweb_admin_password : random_password.fortiweb_admin[0].result) : ""
  fortiweb_license_key    = var.fortiweb_license_mode == "byol_file" ? local.fortiweb_cloudinit_license_key : ""
  fortiweb_user_data = templatefile("${path.module}/templates/fortiweb-user-data.json.tftpl", {
    bucket                 = coalesce(local.fortiweb_cloudinit_bucket_name, "")
    region                 = var.aws_region
    license_key            = local.fortiweb_license_key
    config_key             = coalesce(local.fortiweb_cloudinit_config_key, "")
    include_initial_passwd = var.fortiweb_set_initial_password
    initial_passwd         = var.fortiweb_set_initial_password ? base64encode(local.fortiweb_admin_password) : ""
  })

  tags = merge(
    {
      Project   = "FortiAIGate Demo"
      Managed   = "terraform"
      Component = "FortiWeb"
    },
    var.tags
  )
}

data "aws_ami" "fortiweb" {
  count       = var.fortiweb_enabled ? 1 : 0
  most_recent = true
  owners      = ["aws-marketplace"]

  filter {
    name   = "owner-alias"
    values = ["aws-marketplace"]
  }

  filter {
    name   = "is-public"
    values = ["true"]
  }

  filter {
    name   = "name"
    values = local.fortiweb_ami_name_values
  }

  filter {
    name   = "architecture"
    values = [var.fortiweb_architecture]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "root-device-type"
    values = ["ebs"]
  }
}

resource "random_password" "fortiweb_admin" {
  count = var.fortiweb_enabled && var.fortiweb_set_initial_password && var.fortiweb_admin_password == "" ? 1 : 0

  length           = 16
  special          = true
  min_lower        = 1
  min_upper        = 1
  min_numeric      = 1
  min_special      = 1
  override_special = "$@!%*#?&"
}

resource "aws_s3_object" "config_generated" {
  count = var.fortiweb_enabled && local.fortiweb_shared_prep_ready && var.fortiweb_config_file == "" ? 1 : 0

  bucket       = local.fortiweb_cloudinit_bucket_name
  key          = local.fortiweb_cloudinit_config_key
  content      = local.fortiweb_generated_config
  content_type = "text/plain"

  tags = merge(local.tags, {
    Name = "${local.fortiweb_name}-cloudinit-config"
  })
}

resource "aws_s3_object" "config_file" {
  count = var.fortiweb_enabled && local.fortiweb_shared_prep_ready && var.fortiweb_config_file != "" ? 1 : 0

  bucket       = local.fortiweb_cloudinit_bucket_name
  key          = local.fortiweb_cloudinit_config_key
  source       = var.fortiweb_config_file
  etag         = filemd5(var.fortiweb_config_file)
  content_type = "text/plain"

  tags = merge(local.tags, {
    Name = "${local.fortiweb_name}-cloudinit-config"
  })
}

resource "aws_s3_object" "license" {
  count = var.fortiweb_enabled && local.fortiweb_shared_prep_ready && var.fortiweb_license_mode == "byol_file" ? 1 : 0

  bucket       = local.fortiweb_cloudinit_bucket_name
  key          = local.fortiweb_cloudinit_license_key
  source       = var.fortiweb_license_file
  etag         = filemd5(var.fortiweb_license_file)
  content_type = "text/plain"

  tags = merge(local.tags, {
    Name = "${local.fortiweb_name}-license"
  })
}

resource "aws_security_group" "fortiweb_mgmt" {
  count = var.fortiweb_enabled ? 1 : 0

  name        = "${local.fortiweb_name}-mgmt-sg"
  description = "FortiWeb management access"
  vpc_id      = local.vpc_id

  ingress {
    description = "HTTPS management"
    from_port   = var.fortiweb_admin_https_port
    to_port     = var.fortiweb_admin_https_port
    protocol    = "tcp"
    cidr_blocks = local.effective_allowed_ingress_cidrs
  }

  ingress {
    description = "HTTP management"
    from_port   = var.fortiweb_admin_http_port
    to_port     = var.fortiweb_admin_http_port
    protocol    = "tcp"
    cidr_blocks = local.effective_allowed_ingress_cidrs
  }

  dynamic "ingress" {
    for_each = var.fortiweb_enable_ssh ? [1] : []

    content {
      description = "SSH"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = local.effective_allowed_ingress_cidrs
    }
  }

  dynamic "ingress" {
    for_each = var.fortiweb_enable_icmp ? [1] : []

    content {
      description = "ICMP"
      from_port   = -1
      to_port     = -1
      protocol    = "icmp"
      cidr_blocks = local.effective_allowed_ingress_cidrs
    }
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, {
    Name = "${local.fortiweb_name}-mgmt-sg"
  })
}

resource "aws_security_group" "fortiweb_internal" {
  count = var.fortiweb_enabled ? 1 : 0

  name        = "${local.fortiweb_name}-internal-sg"
  description = "FortiWeb internal subnet access"
  vpc_id      = local.vpc_id

  ingress {
    description = "VPC internal traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [local.vpc_cidr]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, {
    Name = "${local.fortiweb_name}-internal-sg"
  })
}

resource "aws_network_interface" "public" {
  count = var.fortiweb_enabled ? 1 : 0

  description = "${local.fortiweb_name}-port1-public"
  subnet_id   = local.fortiweb_public_subnet_id
  security_groups = [
    aws_security_group.fortiweb_mgmt[0].id,
  ]

  tags = merge(local.tags, {
    Name = "${local.fortiweb_name}-port1-public"
  })
}

resource "aws_network_interface" "internal" {
  count = var.fortiweb_enabled ? 1 : 0

  description       = "${local.fortiweb_name}-port2-internal"
  subnet_id         = local.fortiweb_internal_subnet_id
  source_dest_check = false
  security_groups = [
    aws_security_group.fortiweb_internal[0].id,
  ]

  tags = merge(local.tags, {
    Name = "${local.fortiweb_name}-port2-internal"
  })
}

resource "aws_instance" "this" {
  count = var.fortiweb_enabled ? 1 : 0

  ami                  = data.aws_ami.fortiweb[0].id
  instance_type        = var.fortiweb_instance_type
  key_name             = var.ssh_key_name
  iam_instance_profile = local.fortiweb_instance_profile_name
  user_data            = sensitive(local.fortiweb_user_data)

  lifecycle {
    precondition {
      condition     = var.fortiweb_license_mode != "fortiflex_future"
      error_message = "fortiweb_license_mode=fortiflex_future is a Phase 5 placeholder and is not implemented in Phase 4."
    }

    precondition {
      condition     = local.fortiweb_eip_allocation_id != null
      error_message = "terraform/aws-prep must allocate and output fortiweb_eip_allocation_id before this module can deploy FortiWeb."
    }

    precondition {
      condition     = local.fortiweb_shared_prep_ready
      error_message = "terraform/aws-prep must be applied with fortiweb_enabled=true before this module can deploy FortiWeb."
    }
  }

  root_block_device {
    volume_type = "gp3"
    encrypted   = true
  }

  network_interface {
    network_interface_id = aws_network_interface.public[0].id
    device_index         = 0
  }

  network_interface {
    network_interface_id = aws_network_interface.internal[0].id
    device_index         = 1
  }

  tags = merge(local.tags, {
    Name = local.fortiweb_name
  })

  depends_on = [
    aws_s3_object.config_generated,
    aws_s3_object.config_file,
    aws_s3_object.license,
  ]
}

resource "aws_eip_association" "public" {
  count = var.fortiweb_enabled ? 1 : 0

  allocation_id        = local.fortiweb_eip_allocation_id
  network_interface_id = aws_network_interface.public[0].id

  depends_on = [
    aws_instance.this,
  ]
}
