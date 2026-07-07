locals {
  supported_instance_availability_zones = sort(
    data.aws_ec2_instance_type_offerings.available.locations
  )
  selected_availability_zone     = var.availability_zone != "" ? var.availability_zone : try(local.supported_instance_availability_zones[0], "")
  k3s_subnet_id                  = var.k3s_subnet_mode == "public" ? aws_subnet.public.id : aws_subnet.k3s_private.id
  prep_outputs                   = data.terraform_remote_state.aws_prep.outputs
  k3s_eip_allocation_id          = try(local.prep_outputs.k3s_eip_allocation_id, null)
  k3s_public_ip                  = var.k3s_subnet_mode == "public" ? try(local.prep_outputs.k3s_public_ip, "") : ""
  k3s_inventory_host             = var.k3s_subnet_mode == "public" ? local.k3s_public_ip : aws_instance.this.private_ip
  k3s_ssh_command_host           = local.k3s_inventory_host
  iam_instance_profile_name      = local.prep_outputs.ec2_instance_profile_name
  effective_allowed_ingress_cidr = local.prep_outputs.allowed_ingress_cidr
  effective_allowed_ingress_cidrs = try(
    local.prep_outputs.allowed_ingress_cidrs,
    [local.prep_outputs.allowed_ingress_cidr]
  )
  appliance_ingress_cidrs = [var.fortigate_public_subnet_cidr, var.fortiweb_public_subnet_cidr]
  demo_port_assignments = {
    openwebui = {
      http  = var.demo_http_base_port
      https = var.demo_https_base_port
    }
    chatbot = {
      http  = var.demo_http_base_port + 1
      https = var.demo_https_base_port + 1
    }
    demo_home = {
      http  = var.demo_http_base_port + 2
      https = var.demo_https_base_port + 2
    }
    litellm = {
      http  = var.demo_http_base_port + 3
      https = var.demo_https_base_port + 3
    }
  }
  generated_demo_ingress_tcp_ports = toset(flatten([
    for assignment in values(local.demo_port_assignments) : [
      assignment.http,
      assignment.https
    ]
  ]))
  generated_demo_ingress_tcp_port_list = [
    local.demo_port_assignments.openwebui.http,
    local.demo_port_assignments.chatbot.http,
    local.demo_port_assignments.demo_home.http,
    local.demo_port_assignments.litellm.http,
    local.demo_port_assignments.openwebui.https,
    local.demo_port_assignments.chatbot.https,
    local.demo_port_assignments.demo_home.https,
    local.demo_port_assignments.litellm.https,
  ]
  effective_additional_ingress_tcp_ports = setunion(
    local.generated_demo_ingress_tcp_ports,
    var.additional_ingress_tcp_ports
  )
  github_keys_user_data = length(var.ec2_pull_github_keys) > 0 ? templatefile("${path.module}/templates/user-data.sh.tftpl", {
    github_usernames = var.ec2_pull_github_keys
  }) : null

  tags = merge(
    {
      Project = "FortiAIGate Demo"
      Managed = "terraform"
    },
    var.tags
  )
}

data "aws_ec2_instance_type_offerings" "available" {
  location_type = "availability-zone"

  filter {
    name   = "instance-type"
    values = [var.instance_type]
  }
}

data "aws_ami" "ubuntu_2404" {
  most_recent = true
  owners      = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

data "terraform_remote_state" "aws_prep" {
  backend = "local"

  config = {
    path = var.aws_prep_state_path
  }
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-vpc"
  })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-igw"
  })
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = local.selected_availability_zone
  map_public_ip_on_launch = false

  lifecycle {
    precondition {
      condition     = length(local.supported_instance_availability_zones) > 0
      error_message = "No Availability Zones in the selected AWS region offer the requested instance_type."
    }

    precondition {
      condition     = var.availability_zone == "" || contains(local.supported_instance_availability_zones, var.availability_zone)
      error_message = "availability_zone must be empty or set to an Availability Zone that offers the requested instance_type."
    }
  }

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-k3s-public"
  })
}

resource "aws_subnet" "k3s_private" {
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.k3s_private_subnet_cidr
  availability_zone       = local.selected_availability_zone
  map_public_ip_on_launch = false

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-k3s-private"
  })
}

resource "aws_subnet" "fortigate_public" {
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.fortigate_public_subnet_cidr
  availability_zone       = local.selected_availability_zone
  map_public_ip_on_launch = false

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-fortigate-public"
  })
}

resource "aws_subnet" "fortiweb_public" {
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.fortiweb_public_subnet_cidr
  availability_zone       = local.selected_availability_zone
  map_public_ip_on_launch = false

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-fortiweb-public"
  })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-public"
  })
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "fortigate_public" {
  subnet_id      = aws_subnet.fortigate_public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "fortiweb_public" {
  subnet_id      = aws_subnet.fortiweb_public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "k3s_private" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-k3s-private"
  })
}

resource "aws_route" "k3s_private_default" {
  count = var.k3s_private_default_route_network_interface_id != "" ? 1 : 0

  route_table_id         = aws_route_table.k3s_private.id
  destination_cidr_block = "0.0.0.0/0"
  network_interface_id   = var.k3s_private_default_route_network_interface_id
}

resource "aws_route_table_association" "k3s_private" {
  subnet_id      = aws_subnet.k3s_private.id
  route_table_id = aws_route_table.k3s_private.id
}

resource "aws_security_group" "this" {
  name        = "${var.name_prefix}-sg"
  description = "FortiAIGate demo access"
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = local.effective_allowed_ingress_cidrs
  }

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = local.effective_allowed_ingress_cidrs
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = local.effective_allowed_ingress_cidrs
  }

  dynamic "ingress" {
    for_each = local.effective_additional_ingress_tcp_ports

    content {
      description = contains(local.generated_demo_ingress_tcp_ports, ingress.value) ? "Generated demo TCP port ${ingress.value}" : "Additional demo TCP port ${ingress.value}"
      from_port   = ingress.value
      to_port     = ingress.value
      protocol    = "tcp"
      cidr_blocks = local.effective_allowed_ingress_cidrs
    }
  }

  dynamic "ingress" {
    for_each = var.appliance_ingress_to_k3s_enabled ? local.appliance_ingress_cidrs : []

    content {
      description = "HTTP from appliance subnet ${ingress.value}"
      from_port   = 80
      to_port     = 80
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }

  dynamic "ingress" {
    for_each = var.appliance_ingress_to_k3s_enabled ? local.appliance_ingress_cidrs : []

    content {
      description = "HTTPS from appliance subnet ${ingress.value}"
      from_port   = 443
      to_port     = 443
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
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
    Name = "${var.name_prefix}-sg"
  })
}

resource "aws_instance" "this" {
  ami                    = data.aws_ami.ubuntu_2404.id
  instance_type          = var.instance_type
  key_name               = var.ssh_key_name
  iam_instance_profile   = local.iam_instance_profile_name
  subnet_id              = local.k3s_subnet_id
  vpc_security_group_ids = [aws_security_group.this.id]
  user_data              = local.github_keys_user_data

  lifecycle {
    precondition {
      condition     = var.k3s_subnet_mode == "private" || local.k3s_eip_allocation_id != null
      error_message = "k3s_subnet_mode=public requires terraform/aws-prep to allocate a k3s EIP."
    }

    precondition {
      condition     = local.iam_instance_profile_name != ""
      error_message = "terraform/aws-prep must create and output ec2_instance_profile_name before running this module."
    }
  }

  root_block_device {
    volume_size = var.root_volume_size_gb
    volume_type = "gp3"
    encrypted   = true
  }

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-k3s"
  })
}

resource "aws_eip_association" "k3s" {
  count = var.k3s_subnet_mode == "public" ? 1 : 0

  allocation_id = local.k3s_eip_allocation_id
  instance_id   = aws_instance.this.id
}

resource "local_file" "ansible_inventory" {
  filename = var.inventory_output_path
  content = templatefile("${path.module}/templates/aws.generated.ini.tftpl", {
    ansible_host                     = local.k3s_inventory_host
    public_ip                        = local.k3s_public_ip
    private_ip                       = aws_instance.this.private_ip
    ssh_private_key_file             = var.ssh_private_key_file
    aws_vpc_cidr                     = var.vpc_cidr
    aws_public_subnet_cidr           = var.public_subnet_cidr
    aws_k3s_private_subnet_cidr      = var.k3s_private_subnet_cidr
    aws_fortigate_public_subnet_cidr = var.fortigate_public_subnet_cidr
    aws_fortiweb_public_subnet_cidr  = var.fortiweb_public_subnet_cidr
    aws_k3s_subnet_mode              = var.k3s_subnet_mode
    k3s_cluster_cidr                 = var.k3s_cluster_cidr
    k3s_service_cidr                 = var.k3s_service_cidr
    k3s_cluster_dns                  = var.k3s_cluster_dns
  })
}

resource "local_file" "ansible_ports_vars" {
  filename = var.ansible_ports_vars_output_path
  content = templatefile("${path.module}/templates/ports.generated.yml.tftpl", {
    demo_http_base_port     = var.demo_http_base_port
    demo_https_base_port    = var.demo_https_base_port
    demo_port_assignments   = local.demo_port_assignments
    generated_ingress_ports = local.generated_demo_ingress_tcp_port_list
  })
}
