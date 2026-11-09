# terraform/user.tfvars supplies aws_profile, aws_region, name_prefix,
# allowed_ingress_cidr, and tags.

repo_prefix = "fortiaigate"

repositories = [
  "api",
  "core",
  "webui",
  "scanner",
  "logd",
  "license_manager",
  "triton-models",
  "custom-triton",
  "chatbot-basic",
  # Additional 8.0.2 images. Keep the older repositories for 8.0.1 rollback.
  "guardrail",
  "guardrail-scanner",
  "llm-gateway",
  "faig-models",
  "vllm-server",
]

image_tag_mutability = "IMMUTABLE"
# Keep FortiAIGate release image tags immutable, but allow the demo chatbot
# development image to be rebuilt and pushed with the same tag.
image_tag_mutability_overrides = {
  "chatbot-basic" = "MUTABLE"
}
scan_on_push                  = true
lifecycle_retain_tagged_count = 10

ansible_ecr_vars_output_path = "../../ansible/group_vars/ecr.generated.yml"
