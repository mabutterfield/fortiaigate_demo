# FortiAIGate 8.0.2 deployment reference

The [quickstart](quickstart-802.md) covers the normal instructor workflow.
This page collects optional settings and recovery details for operators.

## Named workspaces and overrides

A saved storage profile records the Terraform workspace and the overrides
directory. When working with an existing profile that uses separate prep and
host files, select them explicitly if needed:

```bash
export TF_WORKSPACE=ohio-802
export FAIG_TERRAFORM_VARS_DIR=/path/to/FAIG/ohio-802
python3 scripts/automated_quickstart.py --yolo
```

The directory must contain `prep.tfvars` and `host.tfvars` with matching AWS
profile and region. `--terraform-vars-dir` is the equivalent CLI option.
Values that conflict with the saved storage profile stop the run. Use the same
profile and overrides for teardown. `--storage-profile` selects a different
private storage profile. Do not run independent Terraform operations against
the same state concurrently.

Existing trusted CIDRs are not silently replaced. An override in `prep.tfvars`
can take precedence over `terraform/user.tfvars`. Public IP detection can
also differ from the SSH source address when using a VPN or proxy.

## Chart and license settings

The default vendor chart location is
`FAIG/FAIG_helm/8.0.2/fortiaigate/Chart.yaml`; set `fortiaigate_chart_path` in
`ansible/group_vars/user.yml` to use another location. Quickstart checks for
the chart before provisioning. If Ansible is broken after a Python update,
check that `ansible-playbook --version` and `ansible-galaxy --version` work.

The experimental initializer selects FAIG licenses using
`quickstart_faig_license_regex`, which defaults to `FAIG.*\.lic`, from
`license_source_dir`. Set those values in ignored `user.yml` if needed. The
older `fortiaigate_license_files` list does not select the automatic 8.0.2
license. A missing rotation marker target or uncertain upload requires manual
reconciliation before retrying.

To leave setup manual, select that option interactively or use
`--no-experimental-faig-init`. In either case, the instructor portal needs
completed FAIG admin setup before sign-in.

## State, credentials and recovery

[Lab secrets and state](lab-secrets-and-state.md) documents storage locations,
static passwords, private files and their lifecycle. Terraform state, backups
and saved plans can contain credentials in plaintext. Keep them outside shared
or public locations and never commit them. External state is opt-in; migration
of existing state remains unvalidated for this release. See the
[state migration recovery runbook](state-migration-recovery.md) before
recovering an interrupted migration.

## Teardown options

`--keep-eip` retains the lab Elastic IPs; `--skip-ec2` retains the whole lab.
With `--yolo`, choose `--export-syslog DIR` or `--discard-syslog` if the
syslog bucket has objects. Export copies the current objects; historical
versions require separate preservation. Teardown checks plans and stops if
it encounters unexpected resources or dependent network interfaces. Appliance
teardown, populated-bucket cleanup and syslog export have not been validated
live for this release.

After an Elastic IP is released, remove its old SSH host key before reusing
that address: `ssh-keygen -R <old-ip>`.
