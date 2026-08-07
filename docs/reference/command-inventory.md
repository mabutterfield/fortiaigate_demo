# Command And Inventory Reference

This page defines the repository-wide command, inventory, shared-variable, and
operator-output conventions.

## Repository-Root Convention

Run commands from `<repo_root>` unless a document explicitly says otherwise.
`<repo_root>` is the `fortiaigate_demo/` directory containing `README.md`,
`terraform/`, `ansible/`, and `scripts/`.

Use root-relative paths for Ansible:

```bash
ansible-playbook -i cloud ansible/playbooks/status_demo_home.yml
ansible-playbook -i local ansible/playbooks/status_demo_home.yml
```

Use Terraform's `-chdir` option rather than changing the shell directory:

```bash
terraform -chdir=terraform/aws-prep plan
terraform -chdir=terraform/aws-ec2-k3s output ssh_command
```

This keeps copy/paste commands consistent and prevents a later relative path
from silently resolving against the wrong module or `ansible/` directory.

## Root Inventory Aliases

Git tracks six root symlinks. Their generated targets are environment-owned
files excluded from version control by `.gitignore`:

| Alias | Generated target | Producer | Use |
|---|---|---|---|
| `cloud` | `ansible/inventory/aws.generated.ini` | `terraform/aws-ec2-k3s` | AWS k3s/FortiAIGate host |
| `cloud-fortigate` | `ansible/inventory/fortigate.generated.ini` | `terraform/aws-fortigate` | AWS FortiGate appliance |
| `cloud-fortiweb` | `ansible/inventory/fortiweb.generated.ini` | `terraform/aws-fortiweb` | AWS FortiWeb appliance |
| `local` | `ansible/inventory/local.generated.ini` | `scripts/local_setup.py` | Local k3s/FortiAIGate host |
| `local-fortigate` | `ansible/inventory/fortigate.local.generated.ini` | `scripts/local_setup.py` | Existing local FortiGate |
| `local-fortiweb` | `ansible/inventory/fortiweb.local.generated.ini` | `scripts/local_setup.py` | Existing local FortiWeb |

A fresh clone intentionally has symlinks whose generated targets do not yet
exist. Generate only the environment being deployed. Do not replace a symlink
with a tracked inventory file.

Inspect the selected alias:

```bash
readlink cloud
ansible-inventory -i cloud --graph
readlink local-fortiweb
ansible-inventory -i local-fortiweb --graph
```

Use the direct generated path when diagnosing generation itself, confirming
which file a third-party command opens, or distinguishing local from cloud
state:

```bash
ansible-inventory \
  -i ansible/inventory/aws.generated.ini \
  --host <host-alias>
```

Normal operator commands should prefer the root alias.

## Deployment Target Resolution

The `local` inventory records `deployment_target=local`, and repository
playbooks—including localhost-only utility playbooks—resolve the target from
the selected inventory. The inventory alias is sufficient for normal commands:

```bash
ansible-playbook -i local ansible/playbooks/validate_ollama.yml
```

`FAIG_DEPLOYMENT_TARGET` remains an advanced compatibility override for unusual
calls that deliberately do not supply a repository inventory. It is not needed
with `-i local` or `-i cloud`, and it must never contradict the selected
inventory.

## Shared Terraform User Values

The operator-owned `terraform/user.tfvars` is the one shared profile file. It
is excluded from version control by `.gitignore`. Git tracks a
`50-user.auto.tfvars` symlink in every user-facing module:

| Module link | Target |
|---|---|
| `terraform/aws-ecr/50-user.auto.tfvars` | `../user.tfvars` |
| `terraform/aws-prep/50-user.auto.tfvars` | `../user.tfvars` |
| `terraform/aws-ec2-k3s/50-user.auto.tfvars` | `../user.tfvars` |
| `terraform/aws-fortigate/50-user.auto.tfvars` | `../user.tfvars` |
| `terraform/aws-fortiweb/50-user.auto.tfvars` | `../user.tfvars` |

Terraform loads configuration in this intended order:

```text
00-system.auto.tfvars       tracked repository defaults
50-user.auto.tfvars         tracked link to local shared user.tfvars
99-local.auto.tfvars        local module-specific overrides, when present
```

Interactive quickstart offers to import or create the shared operator files
when they are missing. The standalone profile commands are optional and are
useful when pre-staging configuration before quickstart:

```bash
# AWS pre-staging
python3 scripts/user_profile.py init

# Local pre-staging without AWS onboarding
python3 scripts/user_profile.py init --local

python3 scripts/user_profile.py check
```

Create a `99-local.auto.tfvars` only for a deliberate module override. Never
put AWS access keys, license contents, or unrelated module values in these
files.

## Generated Variables And State

Common AWS outputs written for Ansible:

| File | Owner | Contains |
|---|---|---|
| `ansible/group_vars/ecr.generated.yml` | `terraform/aws-ecr` | registry, repository URLs, account, and region |
| `ansible/group_vars/terraform.generated.yml` | `terraform/aws-ec2-k3s` | AWS, host, CIDR, and deployment bridge values |
| `ansible/group_vars/ports.generated.yml` | `terraform/aws-ec2-k3s` | demo HTTP/HTTPS port assignments |
| `ansible/group_vars/fortiweb.generated.yml` | `terraform/aws-fortiweb` | FortiWeb endpoint and proxy facts |

Local equivalents are `local.generated.yml`, `registry.generated.yml`, and
`local.secrets.yml`. These environment-specific files are excluded from Git
and can be sensitive.

Terraform commands always target the owning module:

```bash
terraform -chdir=terraform/aws-ecr output repository_urls
terraform -chdir=terraform/aws-prep output k3s_public_ip
terraform -chdir=terraform/aws-ec2-k3s output ansible_inventory
terraform -chdir=terraform/aws-fortigate output fortigate_admin_url
terraform -chdir=terraform/aws-fortiweb output fortiweb_admin_url
```

Local Terraform state is sensitive and module-specific. Do not copy state
between modules or commit it.

## Common Command Shapes

```bash
# Automated deployment
python3 scripts/automated_quickstart.py
python3 scripts/automated_quickstart.py --local

# Component status
ansible-playbook -i cloud ansible/playbooks/status_litellm.yml
ansible-playbook -i local ansible/playbooks/status_litellm.yml

# Appliance status
ansible-playbook -i cloud-fortigate ansible/playbooks/status_fortigate.yml
ansible-playbook -i local-fortiweb ansible/playbooks/status_fortiweb.yml

# Functional acceptance
python3 -m functional_test

# Terraform module operation
terraform -chdir=terraform/aws-ec2-k3s plan
```

## Output And Recovery-Hint Convention

Scripts, playbooks, Terraform outputs, and documentation should:

1. print copy-safe commands relative to `<repo_root>`;
2. identify the deployment lane and component before suggesting a command;
3. use the root inventory alias for normal Ansible next steps;
4. use `terraform -chdir=<module>` for Terraform next steps;
5. name the user-owned or generated file that must be corrected;
6. distinguish retry, recovery, validation, and destructive commands;
7. never print secrets in a suggested command; and
8. state when a missing generated target is expected before its producer runs.

Preferred next-step output:

```text
Next validation command from <repo_root>:
  ansible-playbook -i cloud ansible/playbooks/status_litellm.yml
```

Avoid output that depends on an unstated `cd ansible` or module directory.

## Maintainer Mechanical Checks

The no-apply smoke test validates all six inventory symlink paths and all five
Terraform shared-user symlinks. It validates the tracked link contract even
when a generated target does not exist yet. This is a developer/release check,
not an operator setup requirement:

```bash
python3 scripts/smoke_test.py
```

For a targeted shell check:

```bash
find . -maxdepth 1 -type l -print -exec readlink {} \;
find terraform -maxdepth 2 -type l -name '50-user.auto.tfvars' \
  -print -exec readlink {} \;
```
