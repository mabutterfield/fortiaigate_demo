# Lab Secrets, Terraform State and Static Passwords (8.0.2)

What the 8.0.2 lab stores, where, how sensitive it is, and what teardown
removes. The [Quickstart](quickstart-802.md) owns the setup prompts and
commands; this page is the reference for instructors and reviewers.

> **Status (v1.0 release work).** External Terraform state and
> Terraform-generated per-instance credentials are being integrated into the
> quickstart and teardown. Until that ships, state stays in the repository's
> `terraform/*/terraform.tfstate.d/` folders and generated files stay in
> `FAIG_ENV_DIR`. Everything on this page about sensitivity applies either way.

## Summary

| What | Where (defaults) | Contains secrets | Created by | Removed by |
|---|---|---|---|---|
| Terraform state, backups, saved plans | `FAIG/.state/` (external state, opt-in) or the repository's `terraform/*/terraform.tfstate.d/` | **yes, in plain text** (host module) | Terraform | never automatically, except the host state backup after a confirmed destroy |
| Per-instance generated credentials | `FAIG/.secrets/<workspace>/<instance-id>/` | yes | Terraform and the quickstart | teardown, after AWS confirms the instance terminated |
| Static admin password file | anywhere you choose, outside Git | yes | you | never (yours) |
| Static student password file | anywhere you choose, outside Git | yes | you | never (yours) |
| Storage settings | `FAIG/.faig-storage-settings.json` | no (paths only) | the quickstart | you |
| Student passwords and keys in the lab | Kubernetes Secrets in namespace `lab-data` | yes | Lab Management | host teardown |
| Licenses | `license_source_dir` (default `FAIG/licenses`) | license content | you | never |

`FAIG` is the workspace folder that holds the repository checkout. Both
`.state` and `.secrets` are hidden, owner-only (`0700`) folders. They are
configurable, must be separate (neither inside the other) and must be outside
every Git repository and worktree.

## Terraform state is sensitive

The host module's state (`aws-ec2-k3s`), its `.backup`, and any saved plan
hold the generated FAIG admin password (unless you use a static admin
password file) and the generated LiteLLM master key, UI password and database
password **in plain text**. Marking a value sensitive only hides it in normal
command output; `terraform show -json`, `terraform output -raw`, the state
file and plans still contain it.

- Never commit, share, upload or attach state, backups or plans.
- Keep state files `0600` and their folders `0700`.
- State is local to your machine. Lose it and Terraform can no longer manage
  the resources it created; keep a private backup of `FAIG/.state` (and of the
  matching `.secrets`) if you need to recover from a lost laptop.
- External state is shared by every worktree of the checkout. Run only one
  Terraform operation (quickstart, teardown or manual command) at a time.
- Migration backups made when moving state out of the repository stay private
  until you remove them deliberately.

Static password files are referenced by **path only**. Terraform never reads
them, so their contents never enter state.

## Per-instance generated credentials

Each new EC2 instance gets new values: FAIG admin password (unless static),
LiteLLM master key, UI password and database password, the LiteLLM shared
virtual key, and the FAIG smoke-test key. A rerun or `--skip-terraform`
resume on the same instance reuses them. Replacing the instance generates new
ones, so a rebuild never reuses a destroyed instance's credentials.

The instance folder `FAIG/.secrets/<workspace>/<instance-id>/` holds
`bootstrap-secrets.json` (Terraform-owned), the LiteLLM shared key copy, the
initialization journal and the smoke key. The lab gateway's signing key,
broker tokens and the FAIG chart's master key are generated inside the
cluster and are never written to your machine.

Teardown removes the instance folder only after AWS reports the instance
terminated and the folder's marker matches the workspace and instance. If AWS
says "not found" (possibly the wrong account or region), the files are kept
for you to inspect. Static password files, licenses, tfvars and `user.yml`
are never deleted.

## Static admin password

Leave it unset to get a new FAIG admin password on every rebuild. To keep
one, create an owner-only, one-line file outside Git and set its absolute
path in the ignored host tfvars:

```hcl
faig_admin_static_password_file = "/path/to/FAIG/.secrets/static/faig-admin-password"
```

```bash
chmod 600 /path/to/FAIG/.secrets/static/faig-admin-password
```

The password must meet FAIG's rules. A path under `.secrets/static/` is
outside every instance folder, so teardown never touches it.

## Static student passwords

By default Lab Management generates a password for each student, or you type
a shared password or base. To use the same student passwords on every build,
keep an owner-only file outside Git and point the deploy at it:

```hcl
# ignored host tfvars (passed to Ansible through terraform.generated.yml)
lab_student_password_file = "/path/to/FAIG/.secrets/static/student-passwords"
```

Until the quickstart passes it through, set the same variable in ignored
`ansible/group_vars/user.yml`. Format: one entry per line, lines starting
with `#` are comments, exactly one form per file:

```text
shared: Lab_Pass_2026
```

```text
# student07 gets Lab_2026_07
base: Lab_2026_
```

```text
# students without a line get a generated password
student01: First_Pass_2026
student02: Second_Pass_2026
```

On each gateway deploy the file is checked (regular file, not a link, mode
`0600` or `0400`, outside any Git checkout, valid format, no student password
equal to a static admin password) and copied into Secret
`lab-data/lab-student-passwords`, which only the lab gateway can read. No
values are printed. `/manage/` then offers **From the instructor password
file** when creating students and **Reset to the instructor password file**
when resetting one. Remove the variable to delete that Secret on the next
deploy. See the [Instructor Guide](instructor-guide-802.md) and
[Lab Management](lab-management.md).

## What never goes in Git

State, backups, plans, `.secrets`, static password files, the storage
settings file, tfvars, `user.yml`, kubeconfigs, licenses and any rendered
user-data. Commit only the `*.example` templates.
