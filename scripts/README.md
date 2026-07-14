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
  `--backup-dir` to choose another location. It also runs `sync_all_vars.py`
  after copying missing examples so existing local files pick up new defaults
  without overwriting local values. Use `--yolo` for repeat runs where local
  variables are already configured and images already exist in ECR.
- `automated_teardown.py`: guided teardown for repeat lab cycles. It creates a
  full backup, removes ECR repository resources from Terraform state so
  repositories are not deleted, destroys ECR lifecycle/local output resources,
  then destroys EC2 k3s and AWS prep in dependency order.
- `sync_all_vars.py`: appends missing top-level defaults from known
  `*.example` config files into their local ignored files without overwriting
  existing local values. It covers Terraform `*.tfvars` plus Ansible
  `env.yml`, `all.yml`, and `images.yml`. Use `--check` for CI/preflight,
  `--dry-run` to preview the diff, or `--list` to show managed pairs.
- `bedrock_direct_test.py`: sends a direct signed Bedrock Converse request
- `fortiaigate_chat_test.py`: sends an OpenAI-compatible chat request through FortiAIGate

FortiAIGate image publishing is handled by the Ansible playbook `ansible/playbooks/publish_images.yml`.
