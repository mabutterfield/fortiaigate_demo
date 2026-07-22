# terraform/user.tfvars supplies aws_profile, aws_region, name_prefix,
# ssh_key_name, allowed_ingress_cidr, and tags.

aws_prep_state_path    = "../aws-prep/terraform.tfstate"
aws_ec2_k3s_state_path = "../aws-ec2-k3s/terraform.tfstate"

fortigate_enabled = true

fortigate_instance_type         = "c6i.xlarge"
fortigate_architecture          = "x86_64"
fortigate_version               = "8.0"
fortigate_ami_name_override     = ""
fortigate_license_type          = "byol"
fortigate_license_mode          = "byol_file"
fortigate_fortiflex_token       = ""
fortigate_license_file          = ""
fortigate_license_source_dir    = "../../../licenses"
fortigate_license_file_name     = "FGVMSLTM00000000.lic"
fortigate_root_volume_size_gb   = 2
fortigate_log_volume_size_gb    = 30
fortigate_admin_port            = 8443
fortigate_admin_timeout_minutes = 60
fortigate_enable_ssh            = true
fortigate_enable_api            = true
fortigate_enable_icmp           = true
fortigate_api_admin             = "apiadmin"
fortigate_api_key_length        = 30
