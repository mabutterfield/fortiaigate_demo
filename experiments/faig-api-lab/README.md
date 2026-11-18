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
- `onboard_user.py` creates an org-member invitation, then uses a clean session
  to register with a generated password. The client does not email the link.
  The account must separately be assigned to a workspace. The output must be
  a new owner-only credential file outside Git.
- `workspace-create.template.json` and `provider-add-model.template.json`
  require operator-specific values before use. Adding a model reads the live
  provider and sends a full update preserving the observed existing model and
  credential IDs. This operation has not been validated against a live API;
  review the whole request and concurrency implications before submitting it.

For the JSON runner, provide an HTTPS origin and optionally an owner-only JSON
credentials file containing `username` and `password` with `--credentials`.
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
