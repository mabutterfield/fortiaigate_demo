# Automated Quick Start

The automated quick start is the intended guided setup path for operators who do
not want to run every Terraform and Ansible step manually.

Status: the repo includes a guided setup script that prepares local
configuration, runs Terraform through ECR, AWS prep, EC2 k3s foundation, and
FortiGate/FortiWeb appliance modules when enabled, then runs the Ansible
deployment flow, including appliance configuration, when approved.

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

## Local Hardware Mode

Cloud deployment remains the default. To target an existing local Ubuntu/k3s
host and local registry instead of AWS Terraform, generate ignored local
inventory and variable files first:

```bash
python3 scripts/local_setup.py
```

The setup script prompts for the Ubuntu SSH target, local registry, optional
existing FortiGate/FortiWeb appliance targets, and GPU assignment when
`nvidia-smi` can enumerate GPUs. It writes ignored files under
`ansible/inventory/` and `ansible/group_vars/`, including local registry
settings and Ollama defaults.

For local FortiGate onboarding, `local_setup.py` can use the prompted current
admin username/password once to create or refresh a managed `apiadmin` API
account, generate its API token, validate token login, and then store only the
managed token in ignored `ansible/group_vars/local.secrets.yml`. The prompted
admin password is written only to a temporary vars file used by the bootstrap
playbook and is deleted when the playbook exits.

For local FortiWeb onboarding, `local_setup.py` can use the prompted current
admin username/password once to create or refresh a managed `apiadmin` local
admin with a generated password. Only the managed `apiadmin` username/password
is stored in ignored `ansible/group_vars/local.secrets.yml`; the prompted
bootstrap password is not stored in inventory or committed files.

The generated local appliance inventories contain host, port, and connection
metadata only. They do not contain appliance passwords or API tokens.

In local appliance mode, the AWS-shaped `*_public_private_ip` variables map to
the appliance port1/operator-side address, while `*_internal_ip` maps to the
port2/backend address on the k3s LAN. `local_setup.py` prompts for both when an
appliance is enabled. FortiGate MCP tooling is generated to target
`mcp_fortigate_base_url` on FortiGate port2 when that backend IP is known,
because the MCP pod runs on the k3s/backend side. FortiWeb generated proxy
objects still publish listener VIPs on port1 by default and proxy to k3s
NodePorts through port2.

Then run:

```bash
python3 scripts/automated_quickstart.py --local
```

Local mode skips Terraform and uses the generated local inventory. It deploys
Ollama as the direct model provider, keeps LiteLLM pointed at the in-cluster
Ollama service, and exposes Ollama on the plain HTTP NodePort range. The
default local Ollama NodePort is `30085`; keep this endpoint restricted to a
trusted lab network because stock Ollama does not provide built-in API auth.
Automated quickstart passes the deployment target to Ansible so AWS generated
vars and local generated vars do not leak into each other. If you run local
playbooks manually, pass the same target explicitly:

```bash
FAIG_DEPLOYMENT_TARGET=local ansible-playbook -i ansible/inventory/local.generated.ini ansible/playbooks/status_demo_home.yml
```

To reset only the local generated vars and inventories in this checkout without
touching the deployed lab, export them. Export creates a backup archive and then
removes the generated local files:

```bash
python3 scripts/local_var_cleanup.py export
```

The default archive is `../local_vars_backup.tgz`. This archive may contain the
managed FortiGate API token and FortiWeb admin password from
`ansible/group_vars/local.secrets.yml`, so treat it as sensitive and keep it out
of Git. To restore those generated local files later:

```bash
python3 scripts/local_var_cleanup.py import
```

Pass an explicit archive path to either action when you want a different backup
location.

When local appliance inventories exist, `automated_quickstart.py --local` uses
the managed credentials created by `local_setup.py` and runs the same
FortiGate/FortiWeb status and configuration playbooks used by the AWS path. It
does not need the original prompted bootstrap passwords.

On a fresh host where NVIDIA drivers are not yet usable, `local_setup.py` may
not be able to capture GPU UUIDs. In that case local quickstart completes the
k3s/GPU bootstrap and stops before FortiAIGate deployment. Rerun
`local_setup.py`, select the FortiAIGate and Ollama GPUs, then rerun
`automated_quickstart.py --local`.

To initialize, export, or import local user-owned settings without running
Terraform or Ansible, use the standalone user profile tool:

```bash
python3 scripts/user_profile.py init
python3 scripts/user_profile.py export ../user_profile.tgz
python3 scripts/user_profile.py import ../user_profile.tgz
```

The profile contains `terraform/user.tfvars`,
`ansible/group_vars/user.yml`, and any existing module
`99-local.auto.tfvars` files. It does not embed license files, private keys,
certificates, Terraform state, generated inventory, or generated Ansible vars.

To stop after Terraform and EC2 status, without running Ansible:

```bash
python3 scripts/automated_quickstart.py --skip-ansible
```

Appliance defaults are prepared by default. The tracked
`00-system.auto.tfvars` files set `fortigate_enabled=true` and
`fortiweb_enabled=true`, so automated quickstart runs those Terraform modules
unless ignored `99-local.auto.tfvars` files set them to false.

Use these flags to force-enable appliances when local overrides previously set
one or both to false:

```bash
python3 scripts/automated_quickstart.py --include-fortigate
python3 scripts/automated_quickstart.py --include-fortiweb
python3 scripts/automated_quickstart.py --include-appliances
```

When an appliance is enabled, quickstart reuses the shared EC2 key pair from
`terraform/user.tfvars`, enables the required prep EIPs, and for FortiWeb
enables the prep-owned S3/IAM cloud-init resources.

If an enabled FortiGate or FortiWeb module uses BYOL file mode, quickstart
checks the configured local license path before Terraform starts. When the path
is missing, or still points at the committed all-zero placeholder license name,
interactive runs prompt for a real license file under `FAIG/licenses`. In
`--yolo` mode, the same check is non-interactive and fails fast so Terraform
does not fail later on a missing local file.

Quickstart can also run the same profile lifecycle actions directly:

```bash
python3 scripts/automated_quickstart.py --init
python3 scripts/automated_quickstart.py --import ../user_profile.tgz
python3 scripts/automated_quickstart.py --export ../user_profile.tgz
```

If required profile files are missing, interactive quickstart asks whether to
import a profile, initialize one, or exit. In `--yolo` mode, missing profile
files fail fast unless `--import` or `--init` is provided.

## Current Script Behavior

The current setup script:

- confirm prerequisites on the workstation
- ensure required user profile files exist, or guide import/init
- prompt for AWS profile, region, name prefix, trusted source CIDRs, and optional tags
- prompt for the shared EC2 SSH key pair and local private key path, then save
  both in `terraform/user.tfvars`
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
  admin password in `ansible/group_vars/user.yml`
- leave direct provider, Bedrock model override, Ollama, chatbot prompt source,
  and TLS certificate path tuning to manual advanced configuration
- collect required Terraform values using existing local files as prompt defaults
- generate Terraform-owned Ansible values into
  `ansible/group_vars/terraform.generated.yml`
- run Terraform in the expected order: ECR, AWS prep, EC2 k3s foundation,
  FortiGate when enabled, FortiWeb when enabled
- inspect ECR Terraform state before apply and report whether configured
  repositories are tracked, partially missing, or absent from state
- default to auto-discovering configured ECR repositories that exist in AWS but
  are missing from Terraform state, then importing those before ECR apply
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
  - poll and configure FortiGate/FortiWeb appliances when enabled
  - deploy LiteLLM, MCP demo tools, chatbot UI, demo home, and optional Open WebUI when enabled
  - check `status_fortiaigate.yml` again at the end
  - offer to run the HTTPS gateway playbook; the role no-ops if disabled
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
- instance type, reviewed in `terraform/aws-ec2-k3s/99-local.auto.tfvars`

The default direct model path remains Bedrock through the Terraform-created IAM
profile. Direct provider/model overrides, Ollama endpoints, chatbot prompt
source paths, and TLS certificate paths are advanced manual settings and are
not prompted during quickstart.

For AWS deployments, Terraform writes shared Ansible values such as
`aws_profile`, `aws_region`, SSH key details, CIDRs, and k3s host facts into
`ansible/group_vars/terraform.generated.yml`. Tracked
`ansible/group_vars/system.yml` owns repo defaults. Local operator overrides
belong in ignored `ansible/group_vars/user.yml`.

Existing `terraform/*.tfvars`, module `99-local.auto.tfvars`, and local
`ansible/group_vars/*.yml` values are read and offered as defaults. The script
does not overwrite unrelated local settings; it updates only the values it
prompts for.

Trusted source values must use CIDR notation, such as `203.0.113.10/32` for a
single public IP or `203.0.113.0/24` for a network. The script validates this
before Terraform runs. If you enter a single bare IP address, the script offers
to convert it to a host CIDR such as `/32` for IPv4 or `/128` for IPv6.

FortiAIGate licenses are expected under `FAIG/licenses` by default, controlled
by `license_source_dir` in `ansible/group_vars/user.yml`. When
`fortiaigate_licenses` is empty, the deployment maps the first
`fortiaigate_license_files` entry to the discovered k3s node. The automated
quickstart checks that selected file before Terraform starts and prompts for a
license file when it is not configured or not found. In `--yolo` mode, the same
check is non-interactive and fails fast if the configured file is missing.

FortiGate and FortiWeb BYOL license files are also expected under `FAIG/licenses`
by default. Their tracked `00-system.auto.tfvars` files split the license setting into
`*_license_source_dir` and `*_license_file_name`, with all-zero placeholder
license file names. When `fortigate_license_mode = "byol_file"` or
`fortiweb_license_mode = "byol_file"`, quickstart stats the selected file before
Terraform starts. Use `fortigate_license_mode = "none"` or
`fortiweb_license_mode = "none"` only for an intentional unlicensed boot test.
The legacy `*_license_file` full-path setting remains available as an override.

When `fortigate_license_mode = "fortiflex_token"` or
`fortiweb_license_mode = "fortiflex_token"`, interactive quickstart prompts for
the corresponding FortiFlex token if it is not already set in ignored local
tfvars. `--yolo` mode fails fast when token mode is enabled and the token is
empty. FortiFlex tokens are rendered into instance user-data and therefore into
local Terraform state; do not commit local tfvars or state. Before tainting and
rebuilding a FortiFlex-licensed appliance, clear or replace the token in local
tfvars so the next build consumes a fresh token.

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
- whether to run the HTTPS gateway playbook

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
- `ansible/group_vars/terraform.generated.yml`
- `ansible/inventory/aws.generated.ini`

At the beginning of the run, it verifies that the required user profile files
exist. When they are missing, interactive runs offer profile import,
initialization, or exit.

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
FortiAIGate status once after Helm deploy, continues appliance configuration
and app deployment while FortiAIGate images continue pulling, then checks
FortiAIGate status again at the end:

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

Before it starts Terraform work, teardown checks AWS caller identity
with the `aws_profile` from `terraform/user.tfvars`. If the session is not
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

For repeat teardown runs with no prompts:

```bash
python3 scripts/automated_teardown.py --yolo
```

`--yolo` is equivalent to `--auto-approve --yes`. When the FortiAIGate syslog
S3 bucket exists and contains objects under the configured prefix, it exports a
local backup under `../backups`, then empties the dedicated syslog bucket so
`terraform/aws-prep` can destroy cleanly. If the export fails, teardown stops
instead of deleting unbacked-up logs.

The teardown order is:

1. Destroy `terraform/aws-fortiweb` when state exists.
2. Destroy `terraform/aws-fortigate` when state exists.
3. Destroy `terraform/aws-ec2-k3s`.
4. Export FortiAIGate syslog S3 objects when present, empty the dedicated
   syslog bucket when confirmed or when running non-interactively, then destroy
   `terraform/aws-prep`.
5. Remove `aws_ecr_repository.this[...]` resources from
   `terraform/aws-ecr` state so repositories are not deleted.
6. Run `terraform/aws-ecr` destroy to remove tracked lifecycle policy resources
   and the generated local ECR vars file while preserving repositories already
   removed from state.

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
