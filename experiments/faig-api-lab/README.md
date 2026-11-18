# Experimental FAIG 8.0.2 API tools

These standalone lab tools exercise GUI-observed FAIG 8.0.2 API endpoints.
They are not integrated into the normal deployment or advertised as a supported
vendor API. Use a trusted, disposable lab; review requests and effective policy
scope. They do not configure LiteLLM aliases or instructions.

- `faig_api.py` reads a JSON resource list and supports `apply`, `get`, and
  `validate`. Resources can reference previously read or created fields using
  `{"$ref":"resource.field"}`, a top-level variable using `{"$var":"name"}`,
  or an interactively prompted secret using `{"$secret":"prompt"}`. Apply
  pauses before each request by default; it does not reconcile or roll back.
- `initialize.py` performs the observed initial setup and license upload.
  It selects `FAIG*.lic` alphabetically in the supplied license directory,
  wraps after the last license, and records the uploaded filename in
  `.last-used` only after the upload returns successfully. The marker is local
  state, not a license validity check. If the previous filename is missing,
  it stops for the operator to reconcile it. Review FAIG before retrying an
  ambiguous upload; `--license-only` can authenticate to an already set-up
  installation and retry a known failed upload.
- `build_providers.py` reads the installed scenario matrix and creates a JSON
  input for the runner. `litellm-direct` contains `pass-model` and direct
  scenario aliases; `litellm-faig-chain` contains only `*-faig-chain` re-entry
  aliases. They use the same LiteLLM endpoint but separate FAIG provider
  objects. A provider with zero models was created in the Ohio lab; the
  8.0.2 re-entry route and loop prevention remain untested.
- `onboard_user.py` creates an org-member invitation, then uses a clean session
  to register with a generated or operator-supplied password. The client does not email the link.
  The account must separately be assigned to a workspace. The output must be
  a new owner-only credential file outside Git.
- `prepare_admin.py` prepares owner-only initial setup and login files for a
  fresh database, using `admin@fortiai.lab` by default. It can generate a
  password or read an operator-supplied password from an owner-only file.
- `student_lab.py` expands `student-template.json` for a requested student
  count. By default it previews without network requests; `--apply` creates
  accounts, workspaces and projects using the observed administrative APIs.
- `workspace-create.template.json` and `provider-add-model.template.json`
  require operator-specific values before use. Adding a model reads the live
  provider and sends a full update preserving the observed existing model and
  credential IDs. This operation has not been validated against a live API;
  review the whole request and concurrency implications before submitting it.

For the JSON runner, provide an HTTPS origin and optionally an owner-only JSON
credentials file containing `username` and `password` with `--credentials`.
Optional `--secrets-file` reads a separate owner-only JSON object mapping each
`$secret` prompt name to its value; absent names still prompt interactively.
`--yes` skips all pauses, including write confirmations. `--insecure` disables
TLS certificate verification and is intended only for an isolated lab with a
self-signed certificate. Run each script with `--help` for arguments.

Read-back validation checks only configured fields, not effective policy or
tenant isolation. Test controlled requests and inspect traffic logs. Workspace
security objects may require organization approval, and inherited policies may
change the final action. The onboarding experiment, selected read-back checks,
and user login have been exercised live; a full clean deployment and automated
workspace scenario installation have not.

Never put real credentials, virtual keys, invitation paths, licenses, HARs or
rendered secrets in this directory or Git. Keep experimental code separate
from normal Terraform, Ansible and Helm workflows.

## How the configuration workflow works

These programs are separate entry points, launched explicitly with Python;
the normal deployment does not call them. They use endpoints observed in the
browser capture, rather than controlling the GUI or using a documented vendor
automation interface. A FAIG version change can break the observed contract.

`faig_api.py` logs in with an existing FAIG account, keeps its session cookie,
and sends the returned CSRF token on subsequent requests. A JSON resource list
describes organization-level providers, detectors, guardrails, policies,
virtual keys and workspaces. The runner looks up each object; `apply` can
create objects, `get` reads them, and `validate` compares selected fields.
References in later resources can use IDs returned by earlier ones. New
virtual key values are written once to owner-only files in the key directory.
Requests pause for operator review unless `--yes` is supplied.

The model-add operation reads a provider and reconstructs a full provider
update with the existing model and credential IDs before appending models.
Its update has not been exercised live. LiteLLM aliases and their instructions
must already exist separately; these scripts only configure their FAIG side.

`onboard_user.py` logs in as an organization administrator and creates an
invitation. It then uses a separate anonymous session to identify the invitee,
check a generated password, and accept the invitation. It writes credentials
to a new owner-only file, logs in independently, and reports the number of
workspace memberships. It neither assigns the user to a workspace nor sends
email itself; server-side email behavior has not been established.

For numbered students, use `--student-number 1` for `student01@fortiai.lab`;
numbers above 99 are not truncated. `--student-domain` and explicit `--email`
allow other naming conventions. For either administrator preparation or
student onboarding, `--password-file` reads a single line from a private file
instead of generating a random password. Avoid passwords on command lines.
Keep the generated JSON credentials outside the repository and restrict file
and parent-directory access. Share a student's credentials only through a
channel appropriate for that student. None of these files are overwritten.

The initialization and provider-generation steps were exercised on the Ohio
8.0.2 installation. The student loop has local tests but has not yet been
exercised end-to-end against a live FAIG installation. The tools do not
automate workspace-scoped scenario installation or policy approval, or prove
tenant isolation. Prior manual tests created an alert and a block FortiStore
path and checked their traffic-log verdicts. A full fresh-install-to-student
workflow remains to be implemented and tested. A successful field comparison
alone does not establish that traffic is inspected or policies take effect.

The generator currently uses the existing scenario installer and matrix to
identify aliases that the normal LiteLLM deployment creates. That installer
is retained for compatibility, but is not presumed to be the eventual API
scenario configuration interface. FAIG API scenario definitions and LiteLLM
instruction/alias provisioning still need a coherent modular workflow.

For an isolated lab, the separate entry points can be run from the repository
root after FAIG is ready. Provide private paths and the current HTTPS origin:

```sh
python3 experiments/faig-api-lab/initialize.py --url "$FAIG_URL" \
  --setup-file "$FAIG_SETUP_FILE" --licenses "$FAIG_LICENSE_DIR" --insecure
python3 experiments/faig-api-lab/build_providers.py --output "$FAIG_PROVIDER_JSON"
python3 experiments/faig-api-lab/faig_api.py apply "$FAIG_PROVIDER_JSON" \
  --url "$FAIG_URL" --credentials "$FAIG_ADMIN_FILE" \
  --secrets-file "$FAIG_SECRETS_FILE" --insecure
```

The setup file contains `email`, `username`, `password`, and
`organization_name`. Login credentials use the setup email as `username` in
the observed 8.0.2 build. The provider secrets file maps `LiteLLM master key`
to the existing LiteLLM key. These files must be owner-only and outside Git.
The generator writes placeholders only; it never reads the secrets file.
Inspect the generated model list and confirm those aliases actually exist in
LiteLLM before applying it. For chain aliases, configure a valid re-entry key
and route to a direct model rather than another chain alias; 8.0.2 chain
behavior and loop prevention still need live validation.

To prepare fresh administrator credentials and onboard one student after the
administrator exists:

```sh
python3 experiments/faig-api-lab/prepare_admin.py \
  --setup-output "$FAIG_SETUP_FILE" --login-output "$FAIG_ADMIN_FILE"
python3 experiments/faig-api-lab/onboard_user.py \
  --url "$FAIG_URL" --admin-credentials "$FAIG_ADMIN_FILE" \
  --student-number 1 --output "$FAIG_STUDENT_CREDENTIALS" --insecure
```

These commands do not replace the administrator of an already initialized
database and do not assign a new student to a workspace. The administrator
setup file is an input to `initialize.py` on a fresh installation.

## Repeatable student structure

The default template names accounts `student01@fortiai.lab`, workspaces
`student01_workspace`, and projects `student01_fortistore-injection` and
`student01_resume-tool-injection`. Edit the project suffixes in the JSON template
to add or remove scenarios. The student prefix
ensures that project names remain distinctive in organization-wide views.

Preview any number of students without touching FAIG:

```sh
python3 experiments/faig-api-lab/student_lab.py --count 2
```

Apply after reviewing the template and creating a private credentials
directory outside the repository (`chmod 700`):

```sh
python3 experiments/faig-api-lab/student_lab.py --count 2 --apply \
  --url "$FAIG_URL" --admin-credentials "$FAIG_ADMIN_FILE" \
  --credentials-dir "$FAIG_STUDENT_CREDENTIALS_DIR" --insecure
```

Use `--start` to begin at another student number. Each new account receives a
random password saved in `studentNN.json`; optionally provide an owner-only
`--password-file` to use the same chosen password for new accounts. Existing
accounts require a matching owner-only credential file in that directory.
The runner creates one workspace per student, assigns them workspace admin,
and grants both configured providers and all their current models and keys.
Projects inherit the selected provider access. Budgets and policies are unset;
this does not create scenario guardrails, project keys, or policy approval.

The runner stops before writes if it finds a planned name collision. It is a
one-time lab tool, not reconciliation: API errors can leave partially created
users, workspaces or projects. Inspect and clean up partial results before
retrying. This tool does not rename or remove any existing objects.
