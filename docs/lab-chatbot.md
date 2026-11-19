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
- **Keys:** the student's keys (secrets masked), a check of every key against
  FortiAIGate, and a form to replace one key after regenerating it in
  FortiAIGate. A replacement is saved only if FortiAIGate accepts it for the
  scenario's model (`GET /ai/openai/v1/models` with the key; no chat cost).
- **Super admins** sign in with their FortiAIGate account and pick any student
  under **Act as student**; chat and key edits then use that student's keys.

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
  The chatbot's service account may only `get` and `patch` those named
  Secrets.
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

## Not Yet Built

- Step 4: the single-test view (payload sent, payload returned, Traffic Log
  entry) and "Run all tests" (pass/fail).
- Step 5: the admin portal (FortiAIGate and fallback passwords, seeded keys).
- Instructor all-students view (the admin student picker is the groundwork).
