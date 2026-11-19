# Student Lab Chatbot (8.0.2)

One shared Streamlit chatbot for every student, reached through the
[lab login gateway](lab-gateway.md) on the chatbot route (HTTPS 30444, HTTP
30081 redirects to HTTPS for sign-in). Each student chats with their own
FortiAIGate virtual keys: one key per scenario action, all sent to
`/ai/openai/v1`, so the key, not the URL, selects the FortiAIGate policy.

Source: `chatbot/lab-chatbot/chart` (app code in `files/`), deployed by
`ansible/playbooks/deploy_lab_chatbot.yml` (role `lab_chatbot`). The 8.0.1
chatbot (`chatbot/app`) is unchanged.

## What Students See

- **Sidebar:** their account, then **Scenario** and **Action** (only the
  actions they hold a key for), and **Send through**:
  - *FortiAIGate (your key)*: the selected key at FortiAIGate `/ai/openai/v1`.
  - *Direct to LiteLLM (no FortiAIGate)*: the same scenario prompt, model and
    MCP tools sent straight to LiteLLM with the shared lab key, to compare
    what FortiAIGate changed.
  The sidebar shows the key name (masked value) and the MCP tools offered.
  Changing scenario, action or path clears the chat.
- **Chat:** multi-turn chat with MCP tool calls through the standards MCP
  endpoint (shown in an expander under each reply), and sample attack and
  clean prompts from the scenario. History lives only in the browser session.
- **Tests:**
  - *Run one test* runs the selected scenario action's validation case (the
    same case and pass/fail rules as `python3 -m functional_test baseline`)
    with the student's key. It shows PASS/FAIL with reasons, then for each
    request in the turn: the payload sent, the payload returned and the
    matching FortiAIGate Traffic Log entry (verdict, action, guard type,
    original and modified prompt and response, tool calls, tokens, cost).
  - *Run all tests* runs every scenario action the student has a key for and
    shows only PASS/FAIL per test and a total; a failed test is retried once.
  - Traffic Log entries are read with the student's own FortiAIGate session
    through the gateway's internal API, matched by key name and start time.
    Another chat on the same key during a test can add rows. Admin sign-ins
    have no Traffic Log view, so their tests are judged on the response only.
- **Keys:** the student's keys (secrets masked), a check of every key against
  FortiAIGate, and a form to replace one key after regenerating it in
  FortiAIGate. A replacement is saved only if FortiAIGate accepts it for the
  scenario's model (`GET /ai/openai/v1/models` with the key; no chat cost).
- **Super admins** sign in with their FortiAIGate account and pick any student
  under **Act as student**; chat, tests and key edits then use that student's
  keys. They also get an **Admin** tab:
  - *Students*: each lab student's account, workspace, active flag, key count
    and spend, read with the admin's FortiAIGate session.
  - *Set a student's password*: type one or generate one. FortiAIGate checks
    its strength, then the password is set in FortiAIGate and the matching
    fallback hash is stored. A generated password is shown once. The portal
    cannot update `.student-credentials/studentNN.json` on the deployment
    machine; update that copy by hand.
  - *Keys compared with the instructor's seed*: each key of the selected
    student shows `matches seed`, `changed` (with who and when), `missing
    (seed only)` or `not in seed`, and changed or missing keys can be restored
    from the seed.

## How It Is Built

```
gateway (signed X-Lab-* headers) ─► lab-chatbot Service (ClusterIP :80) ─► Streamlit :8501
                                         │ faig_agent.py (shared agent loop)
            ┌────────────────────────────┼─────────────────────────────┐
FortiAIGate /ai/openai/v1     LiteLLM /v1 (shared key)     MCP standards endpoint
```

- **Packaging:** stock `python:3.12-slim`; the app, `lab_support.py`,
  `requirements.txt`, the shared `chatbot/agent/faig_agent.py` and the scenario
  pack are mounted from a ConfigMap and dependencies are installed at pod start
  (about a minute). No image build or ECR publish.
- **Identity:** the app verifies the gateway's HMAC-signed headers once per
  browser session with its copy of the signing key (`lab-chatbot-signing`,
  copied from `demo-https-gateway/lab-gateway-signing` on each deploy). Requests
  that do not come through the gateway get a "could not be verified" page.
- **Pass/fail rules:** `functional_test/result_contract.py` is shared by
  `functional_test` and the chatbot (Ansible copies it into the chart), so the
  chatbot and the baseline judge results the same way. The Traffic Log check
  requires the strongest verdict to match the action (alert → Alert,
  deny → Block, redact → Redact, passthrough → Log).
- **Scenario pack:** `python3 -m functional_test scenario-pack` builds a
  secret-free JSON from the installed scenarios and the key files: per scenario
  action, the model, system prompt, MCP tools, sample prompts and the
  validation test case used by `baseline`.
- **Keys:** one Secret per student, `lab-keys-studentNN` (data key
  `keys.json`), seeded from `<workspace>/.student-credentials/studentNN-keys`
  (written by `experiments/faig-api-lab/scenario_lab.py prepopulate`).
  Redeploys keep existing Secrets, so student edits survive; set
  `lab_chatbot_reseed_keys: true` to overwrite them from the files (this
  discards edits). Edits are never written back to the instructor's files.
  Every deploy also rewrites a read-only instructor copy per student,
  `lab-seed-studentNN`, which the Admin tab compares and restores from. The
  chatbot's service account may only `get` and `patch` the key Secrets and
  `get` the seed Secrets.
- **Direct key:** the shared LiteLLM virtual key (`lab-chatbot-direct`,
  copied from `litellm/litellm-shared-virtual-key`), never the master key.

## Deploy

Prerequisites: the lab login gateway, LiteLLM with the shared virtual key, the
standards MCP endpoint, and student keys from `scenario_lab.py prepopulate`.

```bash
cd ansible
ansible-playbook -i ../cloud playbooks/deploy_lab_chatbot.yml
ansible-playbook -i ../cloud playbooks/deploy_demo_https_gateway.yml
```

The gateway's chatbot route follows `lab_chatbot_enabled` (placeholder page
when false). Settings are in `ansible/roles/lab_chatbot/defaults/main.yml`;
repo toggles `lab_chatbot_enabled` and `lab_chatbot_reseed_keys` are in
`group_vars/system.yml`.

## Validation

Observed on 2026-11-18 (Ohio lab):
- Deploy seeded `lab-keys-student01` and `lab-keys-student02`, and the pod
  reported healthy.
- Through the gateway, an unsigned request redirects to sign-in. After
  student02 signs in, the gateway serves the Streamlit app and its health
  endpoint.
- In the pod, student02's keys load, and a save round-trip works. Reading any
  other Secret returns 403.
- The `hr-tool-dlp`/`redact` key passes the key check. Its scenario test
  prompt called `employee_sensitive_lookup` over MCP, and FortiAIGate returned
  the record with the SSN and date of birth redacted. The same turn in Direct
  mode returned them unredacted.

Tests (2026-11-19): the "Run all tests" code path for student02 passed 7 of
8. The failure is Resume Deny, a known scenario-tuning issue (see
[known issues](known-issues.md)): FortiAIGate blocks before `document_read`.
The single test for `hr-tool-dlp`/`redact` paired its 2 requests with 2
Traffic Log entries (input Log, output Redact), and no key value appeared in
the result.

Admin tab (2026-11-19):
- The student list showed student01 and student02.
- A student identity got 403 from the admin calls.
- A weak password was refused with the missing requirements listed.
- Resetting student01 (to its current password) succeeded in FortiAIGate and
  wrote the fallback hash; the sidecar accepted it about 30 seconds later and
  rejected a wrong password.
- On student02, an edited key showed as `changed`, and a restore returned it
  to `matches seed`.
- No password appeared in the sidecar log.

## Not Yet Built

- Instructor all-students view (the admin student picker is the groundwork;
  Traffic Log views for admins acting as a student are out of scope).
