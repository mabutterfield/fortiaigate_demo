# terraform/user.tfvars supplies aws_profile, aws_region, name_prefix,
# ssh_key_name, ssh_private_key_file, ec2_pull_github_keys,
# allowed_ingress_cidr, and tags.

aws_prep_state_path = "../aws-prep/terraform.tfstate"

# g4dn.4xlarge is the default lab size used by this module.
# Use g6.8xlarge for a stronger production-like L4 validation target.
instance_type = "g4dn.4xlarge"

# Optional AWS Price List location override. Leave empty unless a new AWS region
# is not in the module's built-in region-to-location map.
aws_pricing_location_override = ""

# Leave empty to auto-select the first AZ that offers instance_type.
# Set explicitly when AWS recommends a specific AZ, for example us-east-1a.
availability_zone = ""

# Keep AWS VPC, k3s pod, and k3s service networks non-overlapping.
# Defaults intentionally use 10.x networks with second octets between 20 and 90.
vpc_cidr                       = "10.20.0.0/16"
public_subnet_cidr             = "10.20.1.0/24"
k3s_private_subnet_cidr        = "10.20.2.0/24"
fortigate_public_subnet_cidr   = "10.20.10.0/24"
fortiweb_public_subnet_cidr    = "10.20.11.0/24"
fortigate_internal_subnet_cidr = "10.20.20.0/24"
fortiweb_internal_subnet_cidr  = "10.20.21.0/24"
k3s_cluster_cidr               = "10.60.0.0/16"
k3s_service_cidr               = "10.70.0.0/16"
k3s_cluster_dns                = "10.70.0.10"

# Public preserves the current direct-access lab behavior. Private places the
# k3s host in the private subnet without a public IP; use that only when an
# appliance or other private access path is ready.
k3s_subnet_mode = "public"

# Optional private subnet default route target for a future FortiGate traffic
# interface. Leave empty until that interface exists.
k3s_private_default_route_network_interface_id = ""

# Terraform generates the standard demo port assignments once and writes them
# to ansible/group_vars/ports.generated.yml:
# - OpenWebUI: 30080 HTTP, 30443 HTTPS
# - Chatbot: 30081 HTTP, 30444 HTTPS
# - Demo home: 30082 HTTP, 30445 HTTPS
# - LiteLLM Admin/API: 30083 HTTP, 30446 HTTPS
# - MCP demo tools: 30084 HTTP, 30447 HTTPS
demo_http_base_port  = 30080
demo_https_base_port = 30443

ansible_ports_vars_output_path     = "../../ansible/group_vars/ports.generated.yml"
ansible_terraform_vars_output_path = "../../ansible/group_vars/terraform.generated.yml"

# Use this only for extra public TCP listeners beyond the generated demo ports.
additional_ingress_tcp_ports = []

# Phase 2 application routing placeholders. The current public demo is
# port_based through generated NodePorts. path_based and host_based are future
# ingress/DNS-backed options.
ingress_routing_strategy = "port_based"
ingress_base_domain      = ""
route53_zone_id          = ""
create_route53_records   = false
magic_dns_zone           = "sslip.io"
