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
- **Operation journal:** records each job's status and result lines, never
  passwords or keys.
- **Not yet available:** prepopulation (keys, policies) and auto-approval.

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
  `lab-roster` (names, workspace IDs) and `lab-credentials` (student
  passwords). Only `lab_auth` can read or patch them. A password is written as
  "pending" before FAIG creates the account, so a lost reply cannot lose it.
- **When jobs stop:**
  - if the instructor's session ends, the job stops as `needs-sign-in`;
  - if Lab Management restarts, running jobs show `interrupted`.

  In both cases the instructor re-runs the job after signing in.

## Not yet implemented

These are tracked in the Milestone 2 interfaces proposal:
- the FAIG executor (models, students, prepopulation);
- student roster, passwords and the share page;
- auto-approval;
- session-handle and service-token authorization;
- the chatbot's switch to the catalog view.
