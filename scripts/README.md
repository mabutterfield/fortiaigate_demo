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
  k3s foundation, and enabled FortiGate/FortiWeb modules, then runs the Ansible
  deployment flow when approved. It backs up existing local tfvars and
  hand-edited Ansible group var YAML files to `../backup` by default, excluding
  generated `*.generated.yml` files; use `--backup-dir` to choose another
  location. It also runs `upgrade_v0_3_to_v0_4.py` and `sync_all_vars.py` after
  copying missing examples so existing local files pick up versioned migrations
  and new defaults without overwriting unrelated local values. It checks
  FortiAIGate and enabled FortiGate/FortiWeb BYOL license files before
  Terraform starts, prompting for real appliance license files when local tfvars
  still use committed placeholder names. Use `--yolo` for repeat runs where
  local variables are already configured and images already exist in ECR.
- `automated_teardown.py`: guided teardown for repeat lab cycles. It creates a
  full backup after confirming AWS caller identity, removes ECR repository
  resources from Terraform state so repositories are not deleted, runs ECR
  destroy for the remaining tracked lifecycle/local output resources, then
  destroys appliances, EC2 k3s, and AWS prep in dependency order.
- `reconfigure_local_vars.py`: standalone guided local configuration review.
  It backs up ignored local tfvars/YAML files, creates missing local files from
  examples, syncs missing defaults, walks through the important quickstart
  variables, then reviews every remaining top-level local-vs-example difference
  as a keep/reset/edit prompt. It does not run Terraform or Ansible.
- `sync_all_vars.py`: appends missing top-level defaults from known
  `*.example` config files into their local ignored files without overwriting
  existing local values. It covers Terraform `*.tfvars` plus Ansible
  `user.yml`. Use `--check` for CI/preflight,
  `--dry-run` to preview the diff, or `--list` to show managed pairs.
- `upgrade_v0_3_to_v0_4.py`: one-time local config migration for existing
  `v0.3`/`v0.4` labs. It migrates shared Terraform values into
  `terraform/user.tfvars`, imports selected module-local Terraform values into
  `99-local.auto.tfvars`, and migrates legacy Ansible `env.yml`/`all.yml`
  user-owned values into `ansible/group_vars/user.yml`.
- `bedrock_direct_test.py`: sends a direct signed Bedrock Converse request
- `fortiaigate_chat_test.py`: sends an OpenAI-compatible chat request through FortiAIGate

FortiAIGate image publishing is handled by the Ansible playbook `ansible/playbooks/publish_images.yml`.
