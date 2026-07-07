# Automated Quick Start

The automated quick start is the intended guided setup path for operators who do
not want to run every Terraform and Ansible step manually.

Status: the repo includes a guided setup script that prepares local
configuration, runs Terraform through ECR, AWS prep, and EC2 k3s foundation,
then runs the Ansible deployment flow when approved.

Run from the repository root:

```bash
python3 scripts/automated_quickstart.py
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

To stop after Terraform and EC2 status, without running Ansible:

```bash
python3 scripts/automated_quickstart.py --skip-ansible
```

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

## Planned Script Behavior

The current setup script:

- confirm prerequisites on the workstation
- back up existing private/local tfvars and Ansible group var YAML files,
  excluding generated `*.generated.yml` files
- prompt for AWS profile, region, name prefix, trusted source CIDRs, and optional tags
- list EC2 key pairs in the selected region and prompt for the k3s SSH key
- list likely private keys in `~/.ssh` and allow a manual key path
- copy missing `*.example` variable files to local ignored files
- collect required Terraform values using existing local files as prompt defaults
- sync AWS/common Ansible values into `ansible/group_vars/env.yml`
- run Terraform in the expected order: ECR, AWS prep, EC2 k3s foundation
- optionally import existing ECR repositories before applying the ECR module
- print a compact EC2 READY/NOT READY status and let the operator continue,
  recheck, or quit
- prompt before running ECR image publishing
- run Ansible in this order:
  - publish FortiAIGate and chatbot images when approved
  - bootstrap k3s
  - deploy FortiAIGate
  - rerun `status_fortiaigate.yml` every 60 seconds until READY, or until the
    configured retry limit is reached
  - deploy LiteLLM, Open WebUI, chatbot UI, and demo home
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
before Terraform runs.

Later Ansible phases should collect:

- FortiAIGate version and image archive location
- license file location
- LiteLLM admin/master key placeholders
- whether to publish images during this run
- whether to start Ansible deployment after Terraform
- whether to deploy the optional HTTPS gateway

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
status, and instance status. It then prompts to continue, recheck once more, or
quit. Enter `r` to re-run the same compact EC2 status query.

During Ansible deployment, the script prints the output of each playbook. After
FortiAIGate deploy, it repeats `status_fortiaigate.yml` until the status output
contains `FortiAIGate status: READY`. The default wait behavior is:

```bash
python3 scripts/automated_quickstart.py --faig-status-delay 60 --faig-status-retries 30
```

The final `show_demo_outputs.yml` playbook should print:

- k3s public IP or private access note
- FortiAIGate login URL
- LiteLLM Admin UI URL
- OpenWebUI URL
- custom chatbot URL
- demo home URL
- commands for status and validation playbooks

## Troubleshooting

If the automated Terraform phase fails or you need to continue manually, use:

- [Manual Quick Start](quickstart-manual.md) for the exact command sequence
- [Troubleshooting](troubleshooting.md) for common failure points
- [Deployment Runbook](deployment-runbook.md) for the full operator workflow
