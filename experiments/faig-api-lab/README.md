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

## Workspace review and approval workflow (observed)

Observed on the Ohio FAIG 8.0.2 lab on 2026-11-18. The student-side
calls were made directly against the API as a Workspace Admin; the admin side
was recorded from the GUI. Endpoint names were confirmed against the GUI's
own client code. No helper script automates this sequence yet.

Workspace-owned security objects go through organization review. A Workspace
Admin creates them as `draft`, submits them (`pending`), and an organization
administrator approves (`active`) or rejects them. All write calls send the
`X-CSRF-Token` header returned by login.

| Step | Role | Request | Body | Result |
|------|------|---------|------|--------|
| 1 | Workspace Admin | `POST /api/v1/workspaces/{workspace_id}/guardrails` | `name`, `description`, `detectorIds`, `denySuspiciousCharacters` | guardrail `draft` |
| 2 | Workspace Admin | `POST /api/v1/workspaces/{workspace_id}/guardrails/{guardrail_id}/submit` | none | guardrail `pending` |
| 3 | Workspace Admin | `POST /api/v1/workspaces/{workspace_id}/policies` | `name`, `description`, `inputGuardrailIds`, `outputGuardrailIds`, `responseScanMode`, `providerAccess` | policy `draft` |
| 4 | Workspace Admin | `POST /api/v1/workspaces/{workspace_id}/policies/{policy_id}/submit` | none | policy `pending` |
| 5 | Org admin | `GET /api/v1/admin/review-queue` | — | `items[]` with `id`, `type` (`guardrail`/`policy`), `name`, `submittedBy`, `ownerWorkspaceId`, `changeKind` (`create`) |
| 6 | Org admin | `POST /api/v1/admin/guardrails/{guardrail_id}/approve` | none | guardrail `active`, `activatedAt` set |
| 7 | Org admin | `POST /api/v1/admin/policies/{policy_id}/approve` | none | policy `active`, `activatedAt` set |

Rejection uses `POST /api/v1/admin/{guardrails|policies}/{id}/reject`; its
request body (a rejection reason) has not been recorded. Workspace detectors
follow the same pattern (`/api/v1/workspaces/{workspace_id}/detectors`,
`.../{detector_uuid}/submit`, `/api/v1/admin/detectors/{detector_uuid}/approve`),
but have not been exercised.

Ordering rules and notes:

- A policy can reference only a guardrail that is `pending` or `active`.
  Submit the guardrail before creating the policy. The policy may be created
  and submitted while its guardrail still awaits approval.
- Approving the guardrail before the policy matches the dependency order and
  is what was recorded. Approving a policy whose guardrail is still pending,
  or rejecting a guardrail used by a pending policy, has not been tested.
- The GUI notification pane and the policy management page send the same
  approve request with no body; they only refresh different lists afterward.
  Approvals are one object per request; no batch endpoint was observed.
- Approval does not apply a policy. After approval, `assignedWorkspaceIds`
  is empty and projects still have no `policyIds`. Binding the policy to a
  project or workspace and creating a project key are separate steps that
  have not yet been recorded for a Workspace Admin.
- `providerAccess` with `allModels: true` and an empty `models` list is
  expanded by the server to the provider's current models in the response.

Observed errors:

| Call | Status | Response | Cause / fix |
|------|--------|----------|-------------|
| Create policy referencing a draft guardrail | 422 | `{"error": "guardrail \"<id>\" is still a draft — a policy can attach only a guardrail that is approved or awaiting review", "field": "inputGuardrailIds[0]"}` | Submit the guardrail first, then create the policy. The failed request creates no policy. |
| `POST /api/v1/login` with an unrelated or stale credential file | 401 | withheld by the client | The credential file does not match this installation's admin. Stop after one or two attempts to avoid lockout and confirm which file belongs to the installation. |
| `GET /api/v1/admin/review-queue` before initial setup | 403 | — | Expected before the first administrator exists. |

The `student_lab.py` client withholds error bodies. When diagnosing a 4xx,
read the JSON `error` and `field` values, which describe validation failures
and have not contained secrets in these tests; never print request bodies
or headers that may carry passwords, CSRF tokens or keys.

## Workspace virtual key and first governed traffic (observed)

After the guardrail and policy were approved, the Workspace Admin created a
project key that carries the policy. No admin action is needed for this step,
and no separate project-policy binding was required. The request body matches
the GUI's own create-key form:

```text
POST /api/v1/me/virtual-keys
{ "keyName": "...", "keyType": "user", "scope": "workspace",
  "workspaceId": "<workspace id>", "projectId": "<project id>",
  "policyIds": ["<approved policy id>"],
  "providerAccess": [{ "providerId": "litellm-direct", "platform": "custom",
      "name": "litellm-direct", "allModels": true, "models": [],
      "blockedModelUuids": [], "allKeys": true, "keys": [],
      "excludedKeyIds": [] }],
  "modelGroups": [],
  "budgetWindows": { "hourly": null, "daily": null, "weekly": null, "monthly": null },
  "tpm": null, "rpm": null, "expiresAt": null }
```

- `GET /api/v1/workspaces/{workspace_id}/attachable-policies` lists the
  approved workspace policies a Workspace Admin may put on a key.
- Budget is unlimited when every `budgetWindows` period is `null`. Each period
  (`hourly`, `daily`, `weekly`, `monthly`) can carry its own dollar amount, so
  daily and monthly budgets can coexist; the GUI collects them as
  `{period, amount}` rows and sends this object. Non-null amounts have not been
  tested through the API.
- `tpm` and `rpm` are optional token and request per-minute limits; `null`
  means no limit. `expiresAt` is optional; `null` means the key does not expire.
- The response contains `secretKey` exactly once. Write it straight to a new
  owner-only file outside Git; never print or log it. The response also
  echoes `policyIds` as `{id, assignedByOrg: false}` and the resolved project,
  workspace and provider models.
- Rotate, revoke and delete use `/api/v1/me/virtual-keys/{key_id}/rotate`,
  `/revoke`, and `DELETE /api/v1/me/virtual-keys/{key_id}`; not yet exercised.

Inference uses the gateway's dialect namespace, not `/ai/v1`:

```text
POST https://<faig>/ai/openai/v1/chat/completions
Authorization: Bearer <virtual key>
```

`/ai/v1/chat/completions` returns 404 `no_such_namespace` (the gateway serves
`/ai/openai`, `/ai/anthropic` and `/ai/gemini`) and is still logged as
`Passthrough` / `failure` traffic for the key's user.

Observed results with `student02-policy-01` (OWASP Agentic Top 10 and OWASP
LLM Top 10 2025 at their default actions, suspicious characters denied):

| Request | Model | Client result | Traffic Log |
|---------|-------|---------------|-------------|
| Benign product question | `fortistore-injection` | 200, reply carries `FORTISTORE_DEMO_BOT` | `Governed`, verdict `Log` |
| Prompt injection / system prompt request | `fortistore-injection` | 200 with FortiAIGate block message | `Governed`, `Block` / `DENY`, both OWASP detectors in `violation.input[]` |

- A short `max_tokens` can return an empty `content` with
  `finish_reason: length`; this is model token usage, not a FAIG block.
- Admin read: `GET /api/v1/admin/traffic-logs?limit=&offset=` (summary rows
  with `verdictLabel`, `action`, `user`, `workspace`, `model`, `requestPath`,
  `trafficType`) and `GET /api/v1/admin/traffic-logs/{uuid}` (detail).
- Detail records attribute the request to the user, workspace, key alias and
  key preview, and list each matched detector. In this test the detail's
  `policy`, `guardrail` and `project` fields were `null`, so policy
  attribution is inferred from the key's only attached policy rather than
  read from the log. The GUI Traffic Log detail view matches: it shows user,
  workspace, virtual key, model, detectors (name, ID, version, rules
  violated) and the LLM messages, but no policy, guardrail or project.
- Detail records include the original prompt and response text. Treat traffic
  log exports as sensitive when real data is used.

## Scenario keys: one virtual key per scenario action

`scenario_lab.py` gives each student one virtual key per scenario action, so a
client switches scenario behavior by switching keys while always calling the
same `https://<faig>/ai/openai/v1` endpoint with the scenario's model. Each
key carries exactly one policy, so the key alias in the Traffic Log identifies
the scenario and action even though log records do not name the policy.

Scenario actions come from each profile's `matrix.entry_points` under
`chatbot/scenarios/examples/`. `scenario-catalog.json` maps each entry point's
`guard_template` to FAIG detectors and a guardrail direction:

| Guard template | Detectors | Direction |
|----------------|-----------|-----------|
| `inject_alert` | per-student alert copies of OWASP Agentic Top 10 and OWASP LLM Top 10 2025 | input |
| `inject_deny` | built-in OWASP Agentic Top 10 and OWASP LLM Top 10 2025 (`block`) | input, deny suspicious characters |
| `output_dlp_alert` / `_redact` / `_deny` | per-student DLP detector for Date of birth and SSN with disposition `alert` / `redact` / `block` | output |

Built-in detectors are fixed to `block`, so alert and redact behavior requires
custom detectors. AI detector copies take the built-in rule text from
`GET /api/v1/workspaces/{id}/built-in-detectors`; DLP rule dispositions may be
`block`, `redact`, `alert` or `log`.

Per student and scenario action the names are:

| Object | Name |
|--------|------|
| detector (shared within the student) | `studentNN-owasp-agentic-alert`, `studentNN-hr-dlp-redact`, ... |
| guardrail | `studentNN-<scenario>-<action>-guardrail` |
| policy | `studentNN-<scenario>-<action>-policy` |
| virtual key | `studentNN-<scenario>-<action>` on project `studentNN_<scenario>`, limited to the scenario model |

All objects are owned by the student's workspace and go through review.
Scenario actions whose model is not offered by the provider are skipped with
a message; for example `hr-tool-dlp` needs its LiteLLM alias deployed and
added to `litellm-direct` first.

### Workflow 1: admin pre-populates ready-to-test students

`prepopulate` signs in with each student's saved credentials, creates and
submits that student's objects one layer at a time (detectors, guardrails,
policies), approves each layer as the org admin, then creates the keys. It
approves only the IDs it created or found pending. Reruns skip active objects
and existing keys. Limit scope with repeatable `--scenario` and `--action`.

```sh
python3 experiments/faig-api-lab/scenario_lab.py prepopulate --start 1 --count 2 \
  --scenario fortistore-injection             # preview only
python3 experiments/faig-api-lab/scenario_lab.py prepopulate --start 1 --count 2 \
  --scenario fortistore-injection --apply --url "$FAIG_URL" \
  --admin-credentials "$FAIG_ADMIN_FILE" \
  --credentials-dir "$FAIG_STUDENT_CREDENTIALS_DIR" --insecure
```

`--credentials-dir` is the owner-only directory (`chmod 700`, outside Git)
that `student_lab.py` fills with `studentNN.json`. Keys are written once to
`studentNN-keys/<key name>.json` with `scenario`, `action`, `model`,
`basePath` and `secretKey`; a front end can map scenario and action to a key
from these files. If FAIG lists a key with no local secret file, rotate or
delete it to obtain a new secret.

### Workflow 2: students build, admin auto-approves

Run `student_lab.py` to create the accounts, workspaces and scenario projects
(the template now includes `hr-tool-dlp`). Students then build detectors,
guardrails, policies and keys themselves. `auto-approve` approves pending
detector, guardrail and policy submissions only from workspaces matching the
template's `studentNN_workspace` pattern, detectors first and policies last.
Deletion requests are skipped unless `--include-deletes` is given.

```sh
python3 experiments/faig-api-lab/scenario_lab.py auto-approve \
  --url "$FAIG_URL" --admin-credentials "$FAIG_ADMIN_FILE" --insecure          # preview
python3 experiments/faig-api-lab/scenario_lab.py auto-approve --apply --watch 15 \
  --url "$FAIG_URL" --admin-credentials "$FAIG_ADMIN_FILE" --insecure
```

Auto-approval removes the review safeguard for those workspaces; use it only
for a controlled lab.

### Observed results (2026-11-18, Ohio lab)

`prepopulate` for student02 and `fortistore-injection` created two detectors,
two guardrails, two policies and two keys, approved each layer, and a rerun
made no changes. Using the same endpoint and model:

| Key | Benign | Injection |
|-----|--------|-----------|
| `student02-fortistore-injection-alert` | 200, Log | 200 (model refused on its own), Traffic Log `Alert` from both student alert detectors |
| `student02-fortistore-injection-deny` | 200, Log | FAIG block message, Traffic Log `Block`/`DENY` from both built-in detectors |

`auto-approve` previewed and then approved a guardrail submitted by student01
and ignored nothing else. Workspace detectors report review state in
`approvalStatus` (not `status`) and use `uuid` as their ID.

## Lab model prices

Model prices are defined in code in `model-pricing.json` as USD per 1M
tokens, FAIG's unit. Values are deliberately about a thousand times
real-world rates so a typical scenario request (~650 input, ~90–400 output
tokens) costs several dollars and cost, budget and attribution views move
visibly without much real token use. `default`
applies to any alias without its own entry (for example future
`*-faig-chain` aliases); a model entry overrides it per field. `cache_read`
and `cache_write` are optional and `null` leaves them unset.

| Alias | Input $/1M | Output $/1M |
|-------|-----------:|------------:|
| default | 3,000 | 6,000 |
| `pass-model` | 3,000 | 8,000 |
| `fortistore-injection` | 4,000 | 9,000 |
| `hr-tool-dlp` | 5,000 | 10,000 |
| `resume-tool-injection` | 6,000 | 12,000 |

- `build_providers.py` writes these prices into newly generated provider
  resources (`customizedCost: true` plus the custom cost fields).
- `model_pricing.py` previews and, with `--apply`, saves prices onto existing
  providers. It sends the GUI's full provider update: endpoint, all models with
  their `uuid`, credentials referenced only by `id`/`name`/`enabled`/`weight`
  (no secret is resent), and `updatedAt` for concurrency. It then checks that
  the saved models and credential IDs match the original and the prices
  applied.

```sh
python3 experiments/faig-api-lab/model_pricing.py --url "$FAIG_URL" \
  --admin-credentials "$FAIG_ADMIN_FILE" --insecure            # preview
python3 experiments/faig-api-lab/model_pricing.py --url "$FAIG_URL" \
  --admin-credentials "$FAIG_ADMIN_FILE" --insecure --apply
```

Observed on 2026-11-18: applying prices to `litellm-direct` kept its credential
ID, and a connectivity test with the stored credential still passed (the
credential's `updatedAt` changes on save). With the current prices a
`fortistore-injection` request of 656 input and 392 output tokens was logged
with `cost` `6.15200000` and `costBasis` `tokens`, matching
656 × $4,000/1M + 392 × $9,000/1M. Budgets of tens of dollars therefore trip
after a handful of requests.

## Ownership of workspace policies

An org admin can create a policy inside a specific student's workspace from
the GUI, but it can only use the organization's global guardrails, not that
workspace's own guardrails. It has not been determined whether this is
intended. To keep ownership consistent, `scenario_lab.py prepopulate` signs in
as each student and creates that student's detectors, guardrails, policies and
keys with the student's own session; the admin session is used only to
approve submissions and to create missing projects.

## Adding a scenario model end to end (HR tool DLP example)

1. Install the scenario so the LiteLLM matrix includes its alias and
   instructions, then redeploy LiteLLM (use the deployment's Terraform
   workspace, for example `TF_WORKSPACE=ohio-802`):

   ```sh
   python3 scripts/scenario_profiles.py add hr-tool-dlp
   ansible-playbook -i cloud ansible/playbooks/deploy_litellm.yml
   ```

2. Add installed-scenario aliases missing from the FAIG providers, priced from
   `model-pricing.json`. Workspaces and projects granted all provider models
   receive the new model automatically.

   ```sh
   python3 experiments/faig-api-lab/model_pricing.py --sync-matrix --url "$FAIG_URL" \
     --admin-credentials "$FAIG_ADMIN_FILE" --insecure            # preview
   python3 experiments/faig-api-lab/model_pricing.py --sync-matrix --apply --url "$FAIG_URL" \
     --admin-credentials "$FAIG_ADMIN_FILE" --insecure
   ```

3. Build the student objects and keys (`scenario_lab.py prepopulate`). It
   creates missing scenario projects (for example `studentNN_hr-tool-dlp`) and
   skips the HR actions until the model is available.

4. Validate every key with `validate_keys.py`. It sends each scenario's
   tracked `functional-tests` `<action>-attack` request with the matching key,
   finds the Traffic Log record by key alias, and checks the verdict
   (`alert` → Alert, `deny` → Block, `redact` → Redact). For HR it also checks
   whether the fixture's synthetic DOB and SSN reached the client.

   ```sh
   python3 experiments/faig-api-lab/validate_keys.py --url "$FAIG_URL" \
     --admin-credentials "$FAIG_ADMIN_FILE" --insecure \
     --key-dir "$FAIG_STUDENT_CREDENTIALS_DIR/student01-keys" \
     --key-dir "$FAIG_STUDENT_CREDENTIALS_DIR/student02-keys"
   ```

Observed on 2026-11-18 (Ohio lab, student01 and student02, 14 keys): all
passed. LiteLLM answered `hr-tool-dlp` with its `FORTI_HR_DLP_DEMO_BOT`
marker. The HR fixture replays an `employee_sensitive_lookup` tool result,
so MCP was not required for this check; the chatbot path through MCP is still
to be validated.

| Scenario / action | Verdict | Detectors | Notes |
|-------------------|---------|-----------|-------|
| FortiStore, resume / alert | Alert | student alert copies (input) | request continues and is billed |
| FortiStore, resume / deny | Block | built-in OWASP (input) | blocked before the model; cost 0 |
| HR / alert | Alert | `studentNN-hr-dlp-alert` (output) | DOB and SSN reach the client |
| HR / redact | Redact | `studentNN-hr-dlp-redact` (output) | values replaced with `[REDACTED_DATE_OF_BIRTH_1]`, `[REDACTED_SSN_1]`; phone and email unchanged |
| HR / deny | Block | `studentNN-hr-dlp-block` (output) | blocked after generation, so the response is still billed |

FAIG appends a counter (`_1`) to the configured replacement text.

## HR DLP: full synthetic table with payment cards

The HR DLP detectors cover `Date of birth`, `SSN` and `Credit/debit card`.
`scenario_lab.py prepopulate` now updates an existing student detector whose
DLP rules (category and disposition), guard lists or AI action differ from
the catalog. Editing an active workspace detector puts it straight back into
the review queue (status `pending`, `hasPendingChange: true`, no separate
submit), and prepopulate then approves it as the admin.

`validate_keys.py --hr-table-with-cards` replays the whole five-row synthetic
employee table from `mcp/chart/files/tools.json`, including the card numbers
that the MCP server normally withholds, as one tool result through each HR
key. It reads the model's original response from the Traffic Log and reports
how many DOB, SSN and card values the model produced and how many reached the
client. If the model refuses to reproduce the data, DLP has nothing to act on;
the run is reported as `INCONCLUSIVE` and resent (`--retries`, default 2), and
the exit code is 2 when any key stays inconclusive.

Observed on 2026-11-18 for student01 and student02:

| Key | Verdict | Model output (DOB / SSN / card) | Reached client |
|-----|---------|---------------------------------|----------------|
| `-hr-tool-dlp-alert` | Alert | 5/5, 5/5, 5/5 | 5/5, 5/5, 5/5 |
| `-hr-tool-dlp-redact` | Redact | 5/5, 5/5, 5/5 | 0/5, 0/5, 0/5 |
| `-hr-tool-dlp-deny` | Block | 5/5, 5/5, 5/5 | 0/5, 0/5, 0/5 |

A first run had one Redact key and one Deny key return verdict `Log` with no
detector; the Traffic Log showed the model had refused to print the table, so
these were not FAIG misses. The 8.0.1 multi-card miss came from a five-tool-loop
chatbot flow, which has not been retested here. See
`docs/known-issues.md`.

## Passthrough baseline key

`scenario_lab.py prepopulate` also creates `studentNN-passthrough`: a key for
`pass-model` with no student policy and no project, replacing the 8.0.1 global
passthrough path for baseline checks. Organization-level policies, if any,
still apply to it. `python3 -m functional_test baseline` uses it alongside the
scenario keys; see `docs/functional-validation.md`.
