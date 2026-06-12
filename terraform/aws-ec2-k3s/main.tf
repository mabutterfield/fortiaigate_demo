locals {
  created_iam_role_name               = var.iam_role_name != "" ? var.iam_role_name : "${var.name_prefix}-ec2-role"
  effective_iam_instance_profile_name = var.iam_instance_profile_name != "" ? var.iam_instance_profile_name : "${var.name_prefix}-ec2-profile"
  supported_instance_availability_zones = sort(
    data.aws_ec2_instance_type_offerings.available.locations
  )
  selected_availability_zone = var.availability_zone != "" ? var.availability_zone : try(local.supported_instance_availability_zones[0], "")

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

data "aws_iam_instance_profile" "fortiaigate" {
  count = var.create_iam_instance_profile || var.iam_instance_profile_name == "" ? 0 : 1
  name  = var.iam_instance_profile_name
}

resource "aws_iam_role" "ec2" {
  count = var.create_iam_instance_profile ? 1 : 0

  name = local.created_iam_role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Ec2AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      },
    ]
  })

  tags = merge(local.tags, {
    Name = local.created_iam_role_name
  })
}

resource "aws_iam_role_policy_attachment" "ec2_managed" {
  for_each = var.create_iam_instance_profile ? toset(var.iam_role_managed_policy_arns) : toset([])

  role       = aws_iam_role.ec2[0].name
  policy_arn = each.value
}

resource "aws_iam_instance_profile" "ec2" {
  count = var.create_iam_instance_profile ? 1 : 0

  name = local.effective_iam_instance_profile_name
  role = aws_iam_role.ec2[0].name

  tags = merge(local.tags, {
    Name = local.effective_iam_instance_profile_name
  })
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
  map_public_ip_on_launch = true

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
    Name = "${var.name_prefix}-public"
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

resource "aws_security_group" "this" {
  name        = "${var.name_prefix}-sg"
  description = "FortiAIGate demo access"
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ingress_cidr]
  }

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ingress_cidr]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ingress_cidr]
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
  ami                         = data.aws_ami.ubuntu_2404.id
  instance_type               = var.instance_type
  key_name                    = var.ssh_key_name
  iam_instance_profile        = var.create_iam_instance_profile ? aws_iam_instance_profile.ec2[0].name : try(data.aws_iam_instance_profile.fortiaigate[0].name, "")
  subnet_id                   = aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.this.id]
  associate_public_ip_address = true

  lifecycle {
    precondition {
      condition     = var.create_iam_instance_profile || var.iam_instance_profile_name != ""
      error_message = "Set iam_instance_profile_name to an existing profile, or set create_iam_instance_profile=true to create one."
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

resource "aws_eip" "this" {
  domain   = "vpc"
  instance = aws_instance.this.id

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-eip"
  })
}

resource "local_file" "ansible_inventory" {
  filename = var.inventory_output_path
  content = templatefile("${path.module}/templates/aws.generated.ini.tftpl", {
    public_ip              = aws_eip.this.public_ip
    ssh_private_key_file   = var.ssh_private_key_file
    aws_vpc_cidr           = var.vpc_cidr
    aws_public_subnet_cidr = var.public_subnet_cidr
    k3s_cluster_cidr       = var.k3s_cluster_cidr
    k3s_service_cidr       = var.k3s_service_cidr
    k3s_cluster_dns        = var.k3s_cluster_dns
  })
}
