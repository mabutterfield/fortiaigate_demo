# Automated Quick Start

The automated quick start is the intended guided setup path for operators who do
not want to run every Terraform and Ansible step manually.

Status: the repo includes a guided setup script that prepares local
configuration, runs Terraform through ECR, AWS prep, EC2 k3s foundation, and
optional FortiGate/FortiWeb appliance modules when enabled, then runs the
Ansible deployment flow when approved.

Run from the repository root:

```bash
python3 scripts/automated_quickstart.py
```

For repeat lab cycles, use the paired teardown script when you want to remove
the EC2/k3s host and AWS prep resources while keeping ECR repositories:

```bash
python3 scripts/automated_teardown.py
```

By default, Terraform still asks for apply approval in each module. To approve
Terraform applies automatically after the script's final confirmation prompt:

```bash
python3 scripts/automated_quickstart.py --auto-approve
```

To resume from an existing Terraform deployment and start from the generated
outputs:

```bash
python3 scripts/automated_quickstart.py --skip-terraform
```

For repeat runs where local variables are already configured and ECR images
already exist, use YOLO mode:

```bash
python3 scripts/automated_quickstart.py --yolo
```

YOLO mode is intended for subsequent lab cycles, not first-time setup. It:

- uses existing local `tfvars` and Ansible YAML values
- runs Terraform with `-auto-approve`
- treats ECR as an existing registry path and imports missing repository state
  when possible
- skips image publishing
- checks FortiAIGate status once after deploy, deploys the remaining app charts,
  then checks FortiAIGate status again at the end
- runs the remaining Ansible bootstrap/deployment flow without the normal
  confirmation prompts

To reconfigure local ignored Terraform and Ansible variables without running
Terraform or Ansible, use the standalone local reconfiguration tool:

```bash
python3 scripts/reconfigure_local_vars.py
```

The tool backs up local tfvars/YAML files, copies missing local files from
examples, syncs missing defaults, walks through the important quickstart
variables, and then prompts for every remaining top-level difference between
local files and their committed examples.

To stop after Terraform and EC2 status, without running Ansible:

```bash
python3 scripts/automated_quickstart.py --skip-ansible
```

Phase 4 appliance tfvars are prepared by default. The committed examples set
`fortigate_enabled=true` and `fortiweb_enabled=true`, so automated quickstart
runs those Terraform modules unless local ignored tfvars set them to false.

Use these flags to force-enable appliances when local tfvars previously set
one or both to false:

```bash
python3 scripts/automated_quickstart.py --include-fortigate
python3 scripts/automated_quickstart.py --include-fortiweb
python3 scripts/automated_quickstart.py --include-appliances
```

When an appliance is enabled, quickstart reuses the shared EC2 key pair from
`terraform/common.tfvars`, enables the required prep EIPs, and for FortiWeb
enables the prep-owned S3/IAM cloud-init resources.

If an enabled FortiGate or FortiWeb module uses BYOL file mode, quickstart
checks the configured local license path before Terraform starts. When the path
is missing, or still points at the committed all-zero placeholder license name,
interactive runs prompt for a real license file under `FAIG/licenses`. In
`--yolo` mode, the same check is non-interactive and fails fast so Terraform
does not fail later on a missing local file.

Before copying or editing local config, the script creates a tar.gz backup of
existing private/local Terraform and Ansible config files in `../backup`
relative to the repository root. To choose another backup directory:

```bash
python3 scripts/automated_quickstart.py --backup-dir /path/to/backup
```

Use `--skip-backup` only when you already have a current backup.

For a full operator backup that includes generated Ansible values, generated
inventory, and local Terraform state, run:

```bash
python3 scripts/backup_config.py
```

Preview the selected files first with:

```bash
python3 scripts/backup_config.py --dry-run
```

Use the full backup before destructive Terraform work, state imports, or larger
refactors. The automated quick start's built-in backup is intentionally lighter
and excludes generated `*.generated.yml` files.

## Current Script Behavior

The current setup script:

- confirm prerequisites on the workstation
- back up existing private/local tfvars and Ansible group var YAML files,
  excluding generated `*.generated.yml` files
- prompt for AWS profile, region, name prefix, trusted source CIDRs, and optional tags
- prompt for the shared EC2 SSH key pair and save it in `terraform/common.tfvars`
- check AWS caller identity and, when login is needed, prompt for
  `aws sso login` versus `aws login`; SSO-style profiles default to
  `aws sso login`
- prompt whether to pass `--use-device-code` to the selected AWS login command
- list EC2 key pairs in the selected region and prompt for the shared EC2 SSH key
- list likely private keys in `~/.ssh` and allow a manual key path
- check the FortiAIGate license source directory and selected license file
  before Terraform starts
- check enabled FortiGate/FortiWeb BYOL license files before Terraform starts
  and prompt when a placeholder or missing file is configured
- offer to keep or change the current LiteLLM API key, admin username, and
  admin password in `ansible/group_vars/all.yml`
- copy missing `*.example` variable files to local ignored files
- append missing top-level defaults from updated example files into existing
  local tfvars/YAML files without overwriting existing local values
- collect required Terraform values using existing local files as prompt defaults
- sync AWS/common Ansible values into `ansible/group_vars/env.yml`
- run Terraform in the expected order: ECR, AWS prep, EC2 k3s foundation,
  optional FortiGate, optional FortiWeb
- inspect ECR Terraform state before apply and report whether configured
  repositories are tracked, partially missing, or absent from state
- optionally import missing existing ECR repositories before applying the ECR module
- print a compact EC2 READY/NOT READY status and let the operator continue,
  recheck, or quit
- prompt before running ECR image publishing; the default is `none` so operators
  can skip publishing when images already exist in ECR
- support `--yolo` for repeat runs where variables and images are already in
  place
- run Ansible in this order:
  - publish selected image set when approved: `none`, `chatbot`, `fortiaigate`, or `all`
  - bootstrap k3s
  - deploy FortiAIGate
  - check `status_fortiaigate.yml` once after deploy
  - deploy LiteLLM, chatbot UI, MCP demo tools, demo home, and optional Open WebUI when enabled
  - check `status_fortiaigate.yml` again at the end
  - optionally deploy the HTTPS gateway
  - print consolidated demo outputs

## Expected Prompted Values

The script should collect or confirm:

- AWS profile and region
- deployment name prefix
- one or more trusted source CIDRs for management and demo access
- optional Terraform tags as comma-separated `key=value` pairs
- EC2 SSH key pair from `aws ec2 describe-key-pairs`
- local SSH private key path from `~/.ssh` or a manually entered path
- FortiAIGate license file under `FAIG/licenses` by default
- LiteLLM API key and Admin UI credentials; press Enter to keep current values
- instance type, reviewed in `terraform/aws-ec2-k3s/terraform.tfvars`
- Bedrock IAM enablement and model allow list, reviewed in
  `terraform/aws-prep/terraform.tfvars`

For AWS deployments, shared Ansible values such as `aws_profile` and
`aws_region` are synced into `ansible/group_vars/env.yml`. `all.yml` remains
focused on FortiAIGate and demo application settings. Its example file includes
commented AWS/common overrides for special local runs where bypassing `env.yml`
is useful.

Existing `terraform/*.tfvars`, module `terraform.tfvars`, and local
`ansible/group_vars/*.yml` values are read and offered as defaults. The script
does not overwrite unrelated local settings; it updates only the values it
prompts for.

Trusted source values must use CIDR notation, such as `203.0.113.10/32` for a
single public IP or `203.0.113.0/24` for a network. The script validates this
before Terraform runs. If you enter a single bare IP address, the script offers
to convert it to a host CIDR such as `/32` for IPv4 or `/128` for IPv6.

FortiAIGate licenses are expected under `FAIG/licenses` by default, controlled
by `license_source_dir` in `ansible/group_vars/all.yml`. When
`fortiaigate_licenses` is empty, the deployment maps the first
`fortiaigate_license_files` entry to the discovered k3s node. The automated
quickstart checks that selected file before Terraform starts and prompts for a
license file when it is not configured or not found. In `--yolo` mode, the same
check is non-interactive and fails fast if the configured file is missing.

FortiGate and FortiWeb BYOL license files are also expected under `FAIG/licenses`
by default. Their committed example paths use all-zero placeholder license file
names. When `fortigate_license_mode = "byol_file"` or
`fortiweb_license_mode = "byol_file"`, quickstart stats the selected file before
Terraform starts. Use `fortigate_license_mode = "none"` or
`fortiweb_license_mode = "none"` only for an intentional unlicensed boot test.

The script pauses for manual review before Terraform and Ansible so these
values can be checked in local vars:

- FortiAIGate version and image archive location
- license file location
- LiteLLM admin/master key placeholders
- whether to publish images during this run; default is `none`
- whether to publish only the chatbot image, which does not load FortiAIGate
  release archives locally
- whether to start Ansible deployment after Terraform
- whether to deploy optional Open WebUI by setting `openwebui_enabled=true`
- whether to deploy the optional HTTPS gateway

Before applying `terraform/aws-ecr`, the script compares the configured ECR
repository list with Terraform state:

- If all configured repositories are tracked, apply is safe for normal updates.
- If some are missing from state, import missing repositories that already exist;
  apply can create only the intentionally new repositories.
- If none are tracked, import is recommended when reusing an existing registry;
  apply is appropriate only for a brand-new registry.

## Expected Output

At the end of the current Terraform phase, the script prints the generated files
that should now exist:

- `ansible/group_vars/ecr.generated.yml`
- `ansible/group_vars/ports.generated.yml`
- `ansible/inventory/aws.generated.ini`

At the beginning of the run, it also prints the backup archive path when any
private/local config files existed. Generated Ansible files such as
`ecr.generated.yml` and `ports.generated.yml` are intentionally excluded.

After Terraform finishes, it runs a compact EC2 status check:

```bash
aws ec2 describe-instance-status \
  --profile <profile-name> \
  --region <region> \
  --instance-ids <instance-id> \
  --include-all-instances \
  --query 'InstanceStatuses[0].[InstanceState.Name,SystemStatus.Status,InstanceStatus.Status]' \
  --output text
```

The script prints region, instance ID, READY/NOT READY, instance state, system
status, and instance status.

The script polls until EC2 reports READY, then starts Ansible. The default EC2
wait behavior is:

```bash
python3 scripts/automated_quickstart.py --ec2-status-delay 30 --ec2-status-retries 20
```

During Ansible deployment, the script prints the output of each playbook. After
FortiAIGate deploy, the default behavior is single-check mode. This checks
FortiAIGate status once after Helm deploy, continues deploying LiteLLM,
chatbot, MCP, demo home, and optional Open WebUI when enabled while
FortiAIGate images continue pulling, then checks FortiAIGate status again at
the end:

```bash
python3 scripts/automated_quickstart.py --faig-status-mode once
```

Use wait mode when a run should block until FortiAIGate is READY before
deploying the remaining demo apps:

```bash
python3 scripts/automated_quickstart.py --faig-status-mode wait --faig-status-delay 60 --faig-status-retries 30
```

The final `show_demo_outputs.yml` playbook should print:

- k3s public IP or private access note
- FortiAIGate login URL
- `LiteLLM proxy provider` values: `API endpoint/private`, `API key`, UI
  username, UI password, and model name
- LiteLLM Admin UI URL
- Open WebUI URL only when `openwebui_enabled=true`
- custom chatbot URL
- MCP tools URL
- demo home URL
- FortiGate and FortiWeb admin URLs plus EC2 instance IDs when appliance
  modules are enabled and applied
- SSH command for the k3s host
- commands for status and validation playbooks

## Automated Teardown

The automated teardown script is intended for frequent provision/deprovision
cycles where image repositories should be retained.

Before it starts backup or Terraform work, teardown checks AWS caller identity
with the `aws_profile` from `terraform/common.tfvars`. If the session is not
valid, it prompts for `aws sso login` or `aws login`, then checks caller
identity again before continuing.

Run from the repository root:

```bash
python3 scripts/automated_teardown.py
```

For repeat use where you do not want Terraform to prompt for each destroy:

```bash
python3 scripts/automated_teardown.py --auto-approve
```

To skip the script-level confirmation prompt as well:

```bash
python3 scripts/automated_teardown.py --auto-approve --yes
```

The teardown order is:

1. Create a full backup with `scripts/backup_config.py`.
2. Remove `aws_ecr_repository.this[...]` resources from
   `terraform/aws-ecr` state so repositories are not deleted.
3. Run `terraform/aws-ecr` destroy to remove tracked lifecycle policy resources
   and the generated local ECR vars file while preserving repositories already
   removed from state.
4. Destroy `terraform/aws-fortiweb` when state exists.
5. Destroy `terraform/aws-fortigate` when state exists.
6. Destroy `terraform/aws-ec2-k3s`.
7. Destroy `terraform/aws-prep`.

The backup includes local tfvars, generated Ansible vars, generated inventory,
and Terraform state. Use `--backup-dir /path/to/backup` to choose another
destination, or `--skip-backup` only when you already have a current backup.

Useful partial teardown flags:

```bash
python3 scripts/automated_teardown.py --skip-ecr
python3 scripts/automated_teardown.py --skip-appliances
python3 scripts/automated_teardown.py --skip-fortiweb
python3 scripts/automated_teardown.py --skip-fortigate
python3 scripts/automated_teardown.py --skip-ec2
python3 scripts/automated_teardown.py --skip-prep
```

ECR repositories are intentionally preserved by state removal, not by Terraform
destroy. On the next quickstart run, choose the existing/import ECR path when
you want Terraform to manage lifecycle policies and regenerate
`ansible/group_vars/ecr.generated.yml` again.

## Next Steps

After automated deployment completes, use
[FortiAIGate Initial Config](FortiAIGate-initial-config.MD) to complete the
FortiAIGate GUI setup, create the required AI guards and flows, and run the
route validation tests.

## Troubleshooting

If the automated Terraform phase fails or you need to continue manually, use:

- [Manual Quick Start](quickstart-manual.md) for the exact command sequence
- [Troubleshooting](troubleshooting.md) for common failure points
- [Deployment Runbook](deployment-runbook.md) for the full operator workflow
