# Student Lab Chatbot (8.0.2)

One shared Streamlit chatbot for every student, reached through the
[lab login gateway](lab-gateway.md) on the chatbot route (HTTPS 30444, HTTP
30081 redirects to HTTPS for sign-in). Each student chats with their own
FortiAIGate virtual keys: one key per scenario action (one key, one policy,
one model alias), all sent to `/ai/openai/v1`, so the key, not the URL,
selects the FortiAIGate policy.

Source: `chatbot/lab-chatbot/chart` (app code in `files/`), deployed by
`ansible/playbooks/deploy_lab_chatbot.yml` (role `lab_chatbot`). The 8.0.1
chatbot (`chatbot/app`) is unchanged.

## What Students See

- **Sidebar:** their account, then **Scenario** and **Action** from the
  catalog, the key mapped to that pair (masked value), the scenario's MCP
  tools, and **Debug options**:
  - *Send directly to LiteLLM (bypasses FortiAIGate)*: off by default and
    needs a second confirmation tick; uses the shared LiteLLM lab key.
  - *Simulate compromised frontend* (FortiStore): adds the scenario's
    compromised frontend instruction as the system prompt.
  Changing scenario, action or a debug option clears the chat.
- **Chat:** multi-turn chat with MCP tool calls (shown in an expander under each
  reply) and the scenario's sample attack and clean prompts. History lives
  only in the browser session.
- **Tests** (for the sidebar's scenario and action):
  - *Run one test*: the action's catalog test is named; when the action has
    several tests (FortiStore normal and compromised frontend) a choice is
    shown. The result is PASS / FAIL / KNOWN FAIL / INCOMPLETE with the
    FortiAIGate verdict, evidence, reasons and the reply, then for each request:
    the payload sent, the payload returned and the matched Traffic Log entry.
  - *Try a prompt*: any catalog prompt of the scenario, or a typed one, sent
    through the action's key with the same tools and marker as a test. It shows
    the FortiAIGate verdict, evidence and the same three columns, **not
    graded**. When a catalog test sends that prompt in the same frontend mode,
    its expected verdict is shown for comparison.
  - *Run all tests*: every test of the selected scenario (default) or of all
    scenarios, for actions with a mapped key; a table of results and a total.
    A failed test is retried once.
- **Keys:**
  - *Refresh from FortiAIGate*: lists the student's keys with scenario, action,
    model, policy count, whether a value is stored, status and origin
    (prepopulated or student).
  - *Map a key*: assign a key to a scenario and action and paste its value. A
    value whose ID does not belong to that key is rejected.
  - *Hello-world*: sends the platform hello-world through a key and records the
    key status (ok, invalid, denied, unavailable).
  - *Rotate*: rotates a key in FortiAIGate (with confirmation) and stores the
    new value.
- **Admins** (FAIG administrators) pick any student under **Act as student**
  and get an **Admin** tab with student password reset and a link to
  [Lab Management](lab-management.md) (`/manage/`).

## How It Is Built

```
gateway (signed X-Lab-* headers, X-Lab-Session) ─► lab-chatbot Service ─► Streamlit :8501
                                                     │ faig_agent.py (shared agent loop)
     ┌──────────────────────┬────────────────────────┼──────────────────────┐
FortiAIGate /ai/openai/v1   LiteLLM /v1 (debug)   MCP standards endpoint   gateway lab_auth (keys, logs)
```

- **Packaging:** stock `python:3.12-slim`. The app (`lab_chatbot.py`,
  `lab_catalog_chat.py`, `lab_support.py`), the shared
  `chatbot/agent/faig_agent.py` and `result_contract.py` (for sensitive-data
  detection) are mounted from a ConfigMap; dependencies are installed at pod
  start (about a minute). No image build or ECR publish.
- **Catalog:** Ansible renders the catalog student view
  (`python3 -m catalog802 student`) into ConfigMap `lab-catalog`, mounted at
  `/catalog/catalog-student.json`, and copies the evaluator package
  (`catalog802/__init__.py`, `loader.py`, `vocabulary.py`, `result_contract.py`)
  into ConfigMap `lab-chatbot-catalog802`, mounted at `/pylib/catalog802`.
  A missing or invalid view shows "catalog unavailable".
- **Grading:** `catalog802.result_contract.evaluate`, the same evaluator as
  `functional_test catalog-baseline`. Each run appends a unique marker
  `[faig-test-<32 hex>]` to the prompt; only Traffic Log rows whose original
  prompt contains it are used, so other traffic on the key cannot be mistaken
  for the test. Missing log rows make a test INCOMPLETE, never PASS.
- **Identity:** the app verifies the gateway's HMAC-signed headers once per
  browser session (`lab-chatbot-signing`, copied from
  `demo-https-gateway/lab-gateway-signing`) and keeps the gateway's opaque
  session handle (`X-Lab-Session`).
- **Keys:** stored by the gateway in Secret `lab-data/lab-keys`. The chatbot
  calls the gateway key endpoints (`/_lab/internal/keys`, `/keys/refresh`,
  `/keys/map`, `/keys/rotate`, `/keys/status`) with its caller token
  (`lab-chatbot-caller`, copied from `lab-gateway-callers`, scope `student`)
  and the visitor's session handle. The pod has no service-account token
  (`legacyKeySecrets: false`) and reads no Kubernetes Secrets.
- **Direct key:** the shared LiteLLM virtual key (`lab-chatbot-direct`, copied
  from `litellm/litellm-shared-virtual-key`), never the master key.
- **Previous app:** `chatbot/lab-chatbot/legacy/lab_chatbot_v1.py` (scenario
  pack and per-student `lab-keys-*`/`lab-seed-*` Secrets), kept for reference.
  Its Ansible tasks are commented out with change notes; the old Secrets are
  not deleted by deploys.

## Deploy

Prerequisites: the lab login gateway (deployed first so `lab-gateway-callers`
exists), LiteLLM with the shared virtual key, the standards MCP endpoint, and
the catalog Python environment on the controller.

```bash
ansible-playbook -i ansible/inventory/aws.generated.ini ansible/playbooks/deploy_demo_https_gateway.yml
ansible-playbook -i ansible/inventory/aws.generated.ini ansible/playbooks/deploy_lab_chatbot.yml \
  -e lab_chatbot_catalog_python=<python with the repo's catalog dependencies>
```

Students and their keys are created from [Lab Management](lab-management.md)
(Create students, Prepopulate). The gateway's chatbot route follows
`lab_chatbot_enabled` (placeholder page when false). Settings are in
`ansible/roles/lab_chatbot/defaults/main.yml`.

## Validation

Observed on 2026-11-19 (Ohio lab, catalog version):
- The pod loads the catalog (3 scenarios), the evaluator and the caller token,
  and has no service-account token.
- Grading as student03 through the Tests code path: HR DLP Alert, Redact and
  Block PASS; FortiStore Block PASS; Resume Block KNOWN FAIL (blocked before
  `document_read`, see [known issues](known-issues.md)); hello-world on
  `student03_passthrough` PASS (verdict Log).
- In a browser, a single test showed the three columns per request and the
  matched Traffic Log entry. The Try a prompt section loads the catalog
  prompts in-pod; it has not been exercised end to end in a browser.

### Previous version (v1)

Observed on 2026-11-18 with the v1 app (scenario pack and `lab-keys-*` Secrets):
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

- Instructor all-students view and admin Traffic Log views when acting as a
  student (admin sign-ins have no student Traffic Log, so their test runs are
  INCOMPLETE).
- Student password reset moves to Lab Management; the Admin tab then retires.
