registry_backend   = "ecr"
aws_ecr_state_path = "../aws-ecr/terraform.tfstate"

ec2_iam_role_name                = ""
ec2_instance_profile_name        = ""
ec2_iam_role_managed_policy_arns = []

allocate_eips = {
  k3s       = true
  fortigate = true
  fortiweb  = true
}

fortiweb_enabled                        = true
fortiweb_cloudinit_bucket_name          = ""
fortiweb_cloudinit_bucket_force_destroy = false
fortiweb_cloudinit_config_key           = "fortiweb/cloud-init/config.txt"
fortiweb_cloudinit_license_key          = "fortiweb/cloud-init/FWB.lic"

enable_bedrock_iam            = true
enable_ec2_bedrock_iam        = true
bedrock_credential_valid_days = 7
bedrock_credential_generation = "20260610"

bedrock_model_ids = [
  "openai.gpt-oss-20b-1:0",
]

bedrock_allowed_regions = ["us-east-1", "us-east-2", "us-west-1", "us-west-2"]

bedrock_no_ip_restriction    = false
bedrock_allowed_source_cidrs = []
