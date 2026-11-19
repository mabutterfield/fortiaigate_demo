# Selecting a private FAIG lab environment (8.0.2 preparation)

An environment contains deployment-specific credentials and keys; it is not a
Terraform backend or a copy of Terraform state. Never commit its contents.
The long-term target is an owner-only directory under `FAIG/.secrets/<name>/`.
Existing environments may remain elsewhere until deliberately migrated.

```text
<environment>/                    # directory 0700, outside Git
├── admin-login.json             # owner-only administrator login
├── litellm-shared-key.json      # owner-only non-admin LiteLLM key
└── students/                    # owner-only
    ├── student01.json           # student login
    └── student01-keys/          # one-time FAIG key files
```

The existing 8.0.2 scripts and Ansible roles can select this directory with
`FAIG_ENV_DIR`. The Ansible variable `faig_env_dir` may instead be set in
ignored `ansible/group_vars/user.yml`; explicit Ansible extra variables have
higher precedence. If `user.yml` hardcodes `faig_env_dir`, it overrides the
shell environment variable for Ansible, while Python scripts read the shell
variable directly. Keep the values consistent; the local Ohio operator file
uses a `lookup('env', 'FAIG_ENV_DIR')` with its existing directory as fallback.

```bash
# Example: replace with the intended actual directory; never commit its files.
export FAIG_ENV_DIR=/path/to/FAIG/.secrets/my-lab
```

When selected, LiteLLM writes/reads `<environment>/litellm-shared-key.json`;
the lab chatbot reads `<environment>/students/studentNN-keys/`; experimental
student/scenario clients use `admin-login.json` and `students/` by default;
and `functional_test baseline` finds `students/student*-keys` and defaults to
`admin-login.json`. Explicit CLI or Ansible path arguments still override these
defaults. Without an environment selection, Ansible retains legacy paths for
compatibility and the baseline still requires `--key-dir`. Check paths before
using them, especially after a rebuild. The LiteLLM role does not replace an
existing local key file automatically; a stale file can disagree with a fresh
Kubernetes Secret, so use a new environment directory for each rebuilt database
or explicitly reconcile it.

## Worktrees and the active Ohio lab

Worktrees contain only committed files. The existing `scripts/user_profile.py`
export/import can transfer user-owned profile files and installed scenario
state to a new checkout; it excludes Terraform state, generated inventories,
licenses and private keys. Its archive can contain credentials from user
configuration: store it privately and do not commit it. Import preserves existing
values unless an explicit replace is requested. Review its behavior before use.

Currently each checkout's Terraform module uses local state, with separate local
workspace state under `terraform.tfstate.d/`. The existing Ohio state belongs to
the original `fortiaigate_demo_802` checkout. Keep Terraform operations against
that existing environment in that operational checkout under the shared lab
lease; **do not** initialize an empty worktree state and apply it to the same
AWS resources. `TF_WORKSPACE=ohio-802` selects a workspace name, not the state
from another checkout. Some Ansible roles invoke Terraform output and therefore
also depend on the right module/state. Generated inventory and group vars point
to a specific deployment and can become stale after instance replacement.

For independent worktree development, copy/import an appropriate private
profile without overwriting existing values, use mocks or a separate disposable
state for Terraform tests, and supply verified inventory/generated files or
explicit variables when a lab lease permits live checks. Review the source and
freshness of every copied/generated file. A later shared-backend migration would
need an explicit state migration, locking and updates to cross-module local
state references; this prep does not perform it.
