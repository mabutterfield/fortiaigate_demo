# Scripts

Operational helper and smoke-test scripts used by the Ansible playbooks and
manual troubleshooting.

Current scripts:

- `user_profile.py`: initializes, imports, exports, and checks the local user
  profile. The profile contains `terraform/user.tfvars`,
  `ansible/group_vars/user.yml`, and any existing module
  `99-local.auto.tfvars` overrides. Use `python3 scripts/user_profile.py init`
  for guided setup, `export ../user_profile.tgz` to save the user profile, and
  `import ../user_profile.tgz` to restore it in a fresh clone.
- `automated_quickstart.py`: guided first-phase setup from repo root; prepares
  or imports the user profile when needed, runs Terraform through ECR, AWS prep,
  EC2 k3s foundation, and enabled FortiGate/FortiWeb modules, then runs the
  Ansible deployment flow when approved. It checks FortiAIGate and enabled
  FortiGate/FortiWeb BYOL license files before Terraform starts, prompting for
  real appliance license files when local tfvars still use committed
  placeholder names. Use `--init`, `--import`, or `--export` for profile
  lifecycle actions, and `--yolo` for repeat runs where local variables are
  already configured and images already exist in ECR.
- `automated_teardown.py`: guided teardown for repeat lab cycles. It creates a
  removes ECR repository resources from Terraform state so repositories are not
  deleted, runs ECR destroy for the remaining tracked lifecycle/local output
  resources, then destroys appliances, EC2 k3s, and AWS prep in dependency
  order.
- `bedrock_direct_test.py`: sends a direct signed Bedrock Converse request
- `fortiaigate_chat_test.py`: sends an OpenAI-compatible chat request through FortiAIGate

FortiAIGate image publishing is handled by the Ansible playbook `ansible/playbooks/publish_images.yml`.
