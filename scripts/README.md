# Scripts

Operational helper scripts used by the Ansible playbooks and manual
troubleshooting. Release smoke tests are internal development checks and are not
part of the end-user quickstart path.

Current scripts:

- `user_profile.py`: initializes, imports, exports, and checks the local user
  profile. The profile contains `terraform/user.tfvars`,
  `ansible/group_vars/user.yml`, and any existing module
  `99-local.auto.tfvars` overrides. It also includes local instruction profiles
  under `chatbot/instructions/local/` when they exist. Use
  `python3 scripts/user_profile.py init` for guided setup, `export
  ../user_profile.tgz` to save the user profile, and `import
  ../user_profile.tgz` to restore it in a fresh clone.
- `instruction_profiles.py`: initializes, validates, activates examples into,
  and opens local operator-owned instruction slots under
  `chatbot/instructions/local/`. Examples and their metadata remain tracked
  under `chatbot/instructions/examples/`. Run it without a subcommand to open a
  menu-driven wizard for changing one slot at a time.
- `automated_quickstart.py`: guided first-phase setup from repo root; prepares
  or imports the user profile when needed, runs Terraform through ECR, AWS prep,
  EC2 k3s foundation, and enabled FortiGate/FortiWeb modules, then runs the
  Ansible deployment flow when approved. It checks FortiAIGate and enabled
  FortiGate/FortiWeb BYOL license files before Terraform starts, prompting for
  real appliance license files when local tfvars still use committed
  placeholder names. Use `--init`, `--import`, or `--export` for profile
  lifecycle actions, and `--yolo` for repeat runs where local variables are
  already configured and images already exist in ECR.
- `automated_teardown.py`: guided teardown for repeat lab cycles. It removes
  appliances, EC2 k3s, and AWS prep in dependency order, then removes ECR
  repository resources from Terraform state and destroys only the remaining
  tracked ECR lifecycle/local output resources so repositories are not deleted.
- `smoke_test.py`: no-apply release smoke test. It compiles Python scripts,
  checks Terraform formatting and shared tfvars symlinks, guards against
  tracked local/secret files, and runs Ansible syntax checks without applying
  Terraform or running deployment tasks.
- `bedrock_direct_test.py`: sends a direct signed Bedrock Converse request
- `fortiaigate_chat_test.py`: sends an OpenAI-compatible chat request through FortiAIGate

FortiAIGate image publishing is handled by the Ansible playbook `ansible/playbooks/publish_images.yml`.
