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
  effective_allowed_ingress_cidrs = distinct([
    for cidr in try(
      local.prep_outputs.allowed_ingress_cidrs,
      local.allowed_ingress_cidrs
    ) : trimspace(cidr)
    if trimspace(cidr) != ""
  ])
  fortigate_eip_allocation_id = try(local.prep_outputs.fortigate_eip_allocation_id, null)
  fortigate_eip_public_ip = coalesce(
    try(local.prep_outputs.fortigate_eip_public_ip, null),
    try(local.prep_outputs.fortigate_public_ip, null)
  )
  vpc_id                       = local.k3s_outputs.vpc_id
  vpc_cidr                     = local.k3s_outputs.network_cidrs.aws_vpc_cidr
  fortigate_public_subnet_id   = local.k3s_outputs.subnet_ids.fortigate_public
  fortigate_internal_subnet_id = local.k3s_outputs.subnet_ids.fortigate_internal
  fortigate_name               = "${var.name_prefix}-fortigate"
  fortigate_license_pay_type   = var.fortigate_license_type == "byol" ? "AWS" : "AWSONDEMAND"
  fortigate_license_path       = var.fortigate_license_file != "" ? var.fortigate_license_file : "${var.fortigate_license_source_dir}/${var.fortigate_license_file_name}"
  fortigate_ami_name_values = var.fortigate_ami_name_override != "" ? [
    var.fortigate_ami_name_override
    ] : [
    "FortiGate-VM64-${local.fortigate_license_pay_type} build*${var.fortigate_version}*",
  ]
  fortigate_public_allowaccess   = var.fortigate_enable_ssh ? "ping https ssh fgfm" : "ping https fgfm"
  fortigate_internal_allowaccess = var.fortigate_enable_ssh ? "ping https ssh fgfm" : "ping https fgfm"
  fortigate_api_admin_trusthosts = [
    for index, cidr in slice(local.effective_allowed_ingress_cidrs, 0, min(length(local.effective_allowed_ingress_cidrs), 10)) : {
      id      = index + 1
      network = cidrhost(cidr, 0)
      netmask = cidrnetmask(cidr)
    }
  ]
  fortigate_management_tcp_ports = {
    for port in distinct(concat(
      [var.fortigate_admin_port, 443],
      var.fortigate_enable_ssh ? [22] : []
      )) : tostring(port) => {
      port = port
      description = port == var.fortigate_admin_port ? "HTTPS management" : (
        port == 443 ? "Default HTTPS during bootstrap" : "SSH"
      )
    }
  }

  tags = merge(
    {
      Project   = "FortiAIGate Demo"
      Managed   = "terraform"
      Component = "FortiGate"
    },
    var.tags
  )
}

data "aws_ami" "fortigate" {
  count       = var.fortigate_enabled ? 1 : 0
  most_recent = true
  owners      = ["679593333241"]

  filter {
    name   = "name"
    values = local.fortigate_ami_name_values
  }

  filter {
    name   = "architecture"
    values = [var.fortigate_architecture]
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

resource "random_string" "fortigate_api_key" {
  count = var.fortigate_enabled && var.fortigate_enable_api ? 1 : 0

  length  = var.fortigate_api_key_length
  special = false
}

data "cloudinit_config" "fortigate" {
  count = var.fortigate_enabled ? 1 : 0

  gzip          = false
  base64_encode = false

  part {
    filename     = "fortigate-config"
    content_type = "text/x-shellscript"
    content = templatefile("${path.module}/templates/fortigate-cloudinit.conf.tftpl", {
      hostname             = local.fortigate_name
      admin_sport          = var.fortigate_admin_port
      admintimeout         = var.fortigate_admin_timeout_minutes
      public_allowaccess   = local.fortigate_public_allowaccess
      internal_allowaccess = local.fortigate_internal_allowaccess
      enable_api           = var.fortigate_enable_api
      api_admin            = var.fortigate_api_admin
      api_key              = try(random_string.fortigate_api_key[0].result, "")
      api_admin_trusthosts = local.fortigate_api_admin_trusthosts
    })
  }

  dynamic "part" {
    for_each = var.fortigate_license_mode == "byol_file" ? [local.fortigate_license_path] : []

    content {
      filename     = "license"
      content_type = "text/plain"
      content      = sensitive(file(part.value))
    }
  }
}

resource "aws_security_group" "fortigate_mgmt" {
  count = var.fortigate_enabled ? 1 : 0

  name        = "${local.fortigate_name}-mgmt-sg"
  description = "FortiGate management access"
  vpc_id      = local.vpc_id

  ingress {
    description = "All VPC internal traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [local.vpc_cidr]
  }

  dynamic "ingress" {
    for_each = local.fortigate_management_tcp_ports

    content {
      description = ingress.value.description
      from_port   = ingress.value.port
      to_port     = ingress.value.port
      protocol    = "tcp"
      cidr_blocks = local.effective_allowed_ingress_cidrs
    }
  }

  dynamic "ingress" {
    for_each = var.fortigate_enable_icmp ? [1] : []

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
    Name = "${local.fortigate_name}-mgmt-sg"
  })
}

resource "aws_security_group" "fortigate_internal" {
  count = var.fortigate_enabled ? 1 : 0

  name        = "${local.fortigate_name}-internal-sg"
  description = "FortiGate internal subnet access"
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
    Name = "${local.fortigate_name}-internal-sg"
  })
}

resource "aws_network_interface" "public" {
  count = var.fortigate_enabled ? 1 : 0

  description = "${local.fortigate_name}-port1-public"
  subnet_id   = local.fortigate_public_subnet_id
  security_groups = [
    aws_security_group.fortigate_mgmt[0].id,
  ]

  tags = merge(local.tags, {
    Name = "${local.fortigate_name}-port1-public"
  })
}

resource "aws_network_interface" "internal" {
  count = var.fortigate_enabled ? 1 : 0

  description       = "${local.fortigate_name}-port2-internal"
  subnet_id         = local.fortigate_internal_subnet_id
  source_dest_check = false
  security_groups = [
    aws_security_group.fortigate_internal[0].id,
  ]

  tags = merge(local.tags, {
    Name = "${local.fortigate_name}-port2-internal"
  })
}

resource "aws_instance" "this" {
  count = var.fortigate_enabled ? 1 : 0

  ami           = data.aws_ami.fortigate[0].id
  instance_type = var.fortigate_instance_type
  key_name      = var.ssh_key_name
  user_data     = data.cloudinit_config.fortigate[0].rendered

  lifecycle {
    precondition {
      condition     = var.fortigate_license_mode != "fortiflex_future"
      error_message = "fortigate_license_mode=fortiflex_future is a Phase 5 placeholder and is not implemented in Phase 4."
    }

    precondition {
      condition     = local.fortigate_eip_allocation_id != null
      error_message = "terraform/aws-prep must allocate and output fortigate_eip_allocation_id before this module can deploy FortiGate."
    }
  }

  root_block_device {
    volume_size = var.fortigate_root_volume_size_gb
    volume_type = "gp3"
    encrypted   = true
  }

  ebs_block_device {
    device_name = "/dev/sdb"
    volume_size = var.fortigate_log_volume_size_gb
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
    Name = local.fortigate_name
  })
}

resource "aws_eip_association" "public" {
  count = var.fortigate_enabled ? 1 : 0

  allocation_id        = local.fortigate_eip_allocation_id
  network_interface_id = aws_network_interface.public[0].id

  depends_on = [
    aws_instance.this,
  ]
}

resource "local_file" "ansible_inventory" {
  filename = var.ansible_inventory_output_path
  content = templatefile("${path.module}/templates/fortigate.generated.ini.tftpl", {
    ansible_host      = local.fortigate_eip_public_ip
    public_ip         = local.fortigate_eip_public_ip
    public_private_ip = try(aws_network_interface.public[0].private_ip, "")
    internal_ip       = try(aws_network_interface.internal[0].private_ip, "")
    instance_id       = try(aws_instance.this[0].id, "")
    admin_port        = var.fortigate_admin_port
    api_admin         = var.fortigate_enable_api ? var.fortigate_api_admin : ""
    admin_url         = local.fortigate_eip_public_ip != null ? "https://${local.fortigate_eip_public_ip}:${var.fortigate_admin_port}" : ""
    api_url           = local.fortigate_eip_public_ip != null ? "https://${local.fortigate_eip_public_ip}:${var.fortigate_admin_port}/api/v2" : ""
  })
}
