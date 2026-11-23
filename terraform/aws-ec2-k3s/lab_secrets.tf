# Generated lab passwords are intentionally held in local Terraform state. The
# instructor's optional static password is referenced by path only.
variable "lab_generated_secrets_enabled" {
  type        = bool
  default     = false
  description = "Generate per-instance lab credentials; state and backups contain generated values."
}

variable "lab_secrets_root" {
  type        = string
  default     = ""
  description = "Private root for generated lab credentials, outside the repository."
}

variable "faig_admin_static_password_file" {
  type        = string
  default     = ""
  description = "Optional path to instructor-owned admin password; Terraform does not read it."
}

variable "lab_student_password_file" {
  type        = string
  default     = ""
  description = "Optional path to instructor-owned student password file; Terraform does not read it."
}

locals {
  lab_instance_secrets_dir = var.lab_generated_secrets_enabled ? "${abspath(var.lab_secrets_root)}/${terraform.workspace}/${aws_instance.this.id}" : ""
  lab_secret_definitions = var.lab_generated_secrets_enabled ? toset(concat(
    ["litellm_master", "litellm_ui", "litellm_postgres"],
    var.faig_admin_static_password_file == "" ? ["faig_admin"] : []
  )) : toset([])
}

resource "random_password" "lab" {
  for_each         = local.lab_secret_definitions
  length           = 24
  special          = true
  override_special = "_"
  min_upper        = 1
  min_lower        = 1
  min_numeric      = 1
  min_special      = 1
  keepers          = { instance = aws_instance.this.id }
}

resource "local_sensitive_file" "lab_bootstrap" {
  count                = var.lab_generated_secrets_enabled ? 1 : 0
  filename             = "${local.lab_instance_secrets_dir}/bootstrap-secrets.json"
  file_permission      = "0600"
  directory_permission = "0700"
  content = jsonencode({
    instance_id = aws_instance.this.id
    workspace   = terraform.workspace
    faig_admin = {
      password             = try(random_password.lab["faig_admin"].result, null)
      static_password_file = var.faig_admin_static_password_file != "" ? var.faig_admin_static_password_file : null
    }
    litellm = {
      master_key        = "sk-${random_password.lab["litellm_master"].result}"
      ui_password       = random_password.lab["litellm_ui"].result
      postgres_password = random_password.lab["litellm_postgres"].result
    }
  })
  lifecycle {
    precondition {
      condition     = trimspace(var.lab_secrets_root) != ""
      error_message = "lab_secrets_root must be set to a private directory outside the repository."
    }
  }
}

output "lab_instance_secrets_dir" {
  value       = local.lab_instance_secrets_dir
  description = "Path to generated credentials; the Terraform state contains their values."
}
