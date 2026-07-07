# Scripts

Operational helper and smoke-test scripts used by the Ansible playbooks and
manual troubleshooting.

Current scripts:

- `backup_config.py`: creates a tar.gz backup of local operator config,
  generated Ansible values, generated inventory, and local Terraform state.
  Use this before destructive Terraform work, imports, or larger refactors:
  `python3 scripts/backup_config.py`. Add `--dry-run` to list selected files
  without creating an archive.
- `automated_quickstart.py`: guided first-phase setup from repo root; prepares
  ignored local config files and runs Terraform through ECR, AWS prep, and EC2
  k3s foundation, then runs the Ansible deployment flow when approved. It backs
  up existing local tfvars and hand-edited Ansible group var YAML files to
  `../backup` by default, excluding generated `*.generated.yml` files; use
  `--backup-dir` to choose another location.
- `bedrock_direct_test.py`: sends a direct signed Bedrock Converse request
- `fortiaigate_chat_test.py`: sends an OpenAI-compatible chat request through FortiAIGate

FortiAIGate image publishing is handled by the Ansible playbook `ansible/playbooks/publish_images.yml`.
