# Lab management page (FortiAIGate 8.0.2)

Instructor page served by the lab login gateway at
`https://<host>:<chatbot HTTPS port>/manage/` (30444 by default). It shares the
chatbot's sign-in; only FAIG administrators get in, and students get a 403.

**Current scope** (updated 2026-11-19):
- **Scenario preview:** models and lab prices, actions, tools, prompts and
  tests, from the rendered catalog.
- **Saved scenario selection.**
- **Apply models to FAIG:** adds missing catalog models (selected scenarios plus
  `pass-model`) and sets lab prices on their provider, keeping other models and
  stored credentials. It verifies by reading back.
- **Create students:** creates or reconciles `studentNN@<domain>` accounts,
  `studentNN_workspace` workspaces and one `studentNN_<scenario>` project per
  selected scenario. Password modes:
  - generated per student;
  - one shared password;
  - a base plus the student number.

  Each password is checked against FAIG's rules and must differ from the
  instructor's. Re-running the same numbers is safe. Existing accounts without
  a stored password are flagged, never reset.
- **Students list and share page:** optional lab-only display names (never
  sent to FAIG). The share page (`/manage/share.html`) shows number, name,
  email, password and sign-in URL for screen sharing.
- **Prepopulate:** for each student with a stored password, and for the
  selected scenarios, creates as that student:
  - detectors, guardrails and policies;
  - one key per action, plus a `studentNN_passthrough` key with no policy.

  Each layer is approved with the instructor's session. Names follow the
  catalog naming, e.g. `student03_hr-tool-dlp_redact`. Key secrets (shown by
  FAIG only once) are saved in the `lab-keys` Secret in `lab-data`. Existing
  objects and keys are kept. A key that exists without a stored secret is
  reported; restoring it by rotation is not built yet. Run it from "Create
  students" (checkbox) or "Prepopulate existing students".
- **Operation journal:** records each job's status and result lines, never
  passwords or keys.
- **Chatbot keys:** since 2026-11-19 the student chatbot reads and maps keys
  from `lab-keys` through the gateway (see [lab chatbot](lab-chatbot.md)).
- **Not yet available:** auto-approval, seeded-key restore by rotation, and
  student password reset (still on the chatbot's Admin tab).

## Deploy

```bash
TF_WORKSPACE=<workspace> ansible-playbook -i ansible/inventory/aws.generated.ini ansible/playbooks/deploy_lab_management.yml
TF_WORKSPACE=<workspace> ansible-playbook -i ansible/inventory/aws.generated.ini ansible/playbooks/deploy_demo_https_gateway.yml
```

The first command:
- renders the catalog views on the controller (`python3 -m catalog802 student|faig`);
- installs chart `chatbot/lab-management/chart` into namespace `lab-management`;
- waits for the rollout.

The second adds the `/manage/` route to the chatbot gateway route.
`lab_management_enabled: false` removes the route on the next gateway deploy.

It starts with zero students, keys or selection. A missing or invalid catalog
shows "catalog unavailable" instead of failing.

## If you set up FAIG yourself

The quickstart's experimental initializer does the FAIG first-time setup for you
(on by default once it is validated). If you turn it off
(`--no-experimental-faig-init` or `quickstart_experimental_faig_init: false`)
or install FAIG another way, Lab Management still deploys and starts empty, but
nobody can sign in to `/manage/` until FAIG is set up. No redeploy is needed
afterwards: the gateway checks FAIG live at every sign-in and request.

Do these in the FAIG GUI (`https://<host>/ui`), in order:

1. **First-time setup.** Create the administrator account and organization.
   This account is a FAIG `super_admin`, which is what `/manage/` accepts
   (`lab_auth.py` maps `super_admin` to the instructor role; anyone else gets a
   403, and students are recognized by their `studentNN_workspace`). To give
   more instructors access, create more `super_admin` users. Use a password
   that no student will get: Create students rejects a student password equal
   to the instructor's.
2. **License.** Upload the FAIG license and confirm it shows Active with
   scanning enabled. Without both, the guardrail tests can't pass.
3. **LiteLLM provider.** Lab Management's Apply models only edits an existing
   provider; it never creates one, and it refuses a provider without a saved
   credential. Create a provider exactly as the catalog expects
   (`catalog802/data/models.json`: every lab model uses provider
   `litellm-direct`):
   - ID and name `litellm-direct`, platform custom, OpenAI API format;
   - endpoint `http://litellm.litellm.svc.cluster.local:4000/v1` (in-cluster
     LiteLLM; it is not reachable from outside);
   - one enabled API key: the LiteLLM shared non-admin virtual key. It is in
     the owner-only file `litellm-shared-key.json` in your `FAIG_ENV_DIR`
     (or `.litellm_shared_virtual_key.json` in the workspace root), and in
     Secret `litellm-shared-virtual-key` in namespace `litellm`. Copy it from
     the file; don't print it in a shared terminal.
   - at least the model `pass-model` (custom model). Apply models adds the
     scenario models and lab prices later; leaving the others out is fine.
4. **Optional check.** Create a global key for `pass-model` only, send one
   request through FAIG and confirm a Traffic Log entry. This is what the
   initializer's governed smoke test does. Delete the key afterwards, or keep
   it outside the lab.

Then sign in at `https://<host>:<chatbot HTTPS port>/manage/` with the
administrator account and continue as usual: select scenarios, **Apply models**
(it reports `litellm-direct: add ...` and verifies by reading back), then
Create students with or without Prepopulate.

Typical errors when a step was missed:
- 403 on `/manage/` after sign-in: the account isn't `super_admin`.
- Sign-in fails at the gateway: first-time setup not done, or FAIG not ready.
- Apply models fails reading `litellm-direct`: step 3 not done, or the
  provider was created with a different ID.
- Create students fails with "provider has no saved credential": the provider
  has no API key.
- Prepopulated tests return no verdicts or fail: license inactive or scanning
  disabled.

This manual path has not yet been run end to end on a fresh host; it mirrors
what the initializer (`scripts/faig_bootstrap_802.py`) creates.

## GUI-only installs (no GPU, no license)

A one-off install mode for GUI testing: FAIG runs without a GPU and is not
licensed, so it passes traffic but does not inspect it. Set `faig_gui_only: true`
(the deployment sets it for this mode); Lab Management and the chatbot read it
as `lab_management_gui_only` and `lab_chatbot_gui_only`.

- `/manage/` shows a banner. Models, students and prepopulation run as usual
  so the GUI objects exist. Whether FAIG accepts every object without a
  license is not yet verified.
- In the chatbot, every test, Run all, Try a prompt and hello-world is shown
  ungraded: the reply, payloads and any Traffic Log entry, never PASS or FAIL.
  A hello-world reply still marks the key OK.
- Guardrail results can't be verified in this mode. Use a licensed GPU install
  for any test that must pass.

## Design notes

- **Image:** stock `python:3.12-slim`, standard library only, code in a
  ConfigMap. No custom image or pip install.
- **Pod permissions:**
  - no service-account token, no FAIG cookies or passwords, no signing key;
  - non-root, with a read-only root filesystem.
- **Authorization:** every request except `/healthz` forwards the gateway's
  signed `X-Lab-*` headers to the gateway auth service
  (`/_lab/internal/admin/students`), which verifies them and makes a live FAIG
  admin call. A positive answer is cached for 20 s per signed header set.
  POSTs also require the browser `Origin` to match the gateway's
  `X-Forwarded-Proto`/`-Host`, plus the `X-Lab-Request: 1` header.
- **Gateway changes:**
  - `/_lab/internal/` returns 404 from outside; in-cluster callers use the
    auth service port directly;
  - routes may define `prefixRoutes`, which are signed-in path prefixes proxied
    with the prefix stripped.
- **State:** SQLite in PVC `lab-management-state`. It survives pod restarts but
  not host termination. Back it up with a consistent copy of the database and
  WAL files while the pod is stopped.

## Where FAIG actions run

- **Who acts:** Lab Management never holds FAIG cookies or passwords. It calls
  the gateway's sign-in service (`lab_auth`) with:
  - its own caller token (Secret `lab-management-caller`, copied from
    `lab-gateway-callers`);
  - the instructor's session handle (`X-Lab-Session`).

  `lab_auth` acts with that instructor's live FAIG session and allows only a
  fixed list of FAIG calls.
- **Where student data lives:** in namespace `lab-data`, in Secrets
  `lab-roster` (names, workspace IDs), `lab-credentials` (student
  passwords) and `lab-keys` (prepopulated key secrets). Only `lab_auth` can read or patch them. A password is written as
  "pending" before FAIG creates the account, so a lost reply cannot lose it.
- **When jobs stop:**
  - if the instructor's session ends, the job stops as `needs-sign-in`;
  - if Lab Management restarts, running jobs show `interrupted`.

  In both cases the instructor re-runs the job after signing in.

## Not yet implemented

Tracked in the Milestone 2 interfaces proposal:
- auto-approval: the instructor turns it on for a chosen number of hours; it
  approves pending review-queue items with the instructor's session every 60
  seconds, with a status indicator;
- restoring a prepopulated key that has no stored secret, by rotating it;
- student password reset on this page (then the chatbot Admin tab can be
  retired);
- handling FAIG's idle session timeout (not yet measured) for long jobs.
