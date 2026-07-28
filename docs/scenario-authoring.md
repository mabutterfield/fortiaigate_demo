# Scenario Authoring Guide

Scenario profiles live under `chatbot/scenarios/examples/<scenario-id>/`.
Each scenario has:

- `profile.json`: tracked metadata, prompt examples, expected traces, data
  sources, and the intended MCP tool profile.
- `instructions.txt`: tracked backend instructions installed into `demo-a` or
  `demo-b` for repeatable demos.

The active installed instructions live under `chatbot/instructions/local/`.
Those files are ignored by Git so they can be tuned during recording without
changing the tracked examples.

## Edit And Test Workflow

1. Install the tracked scenario into a local slot:

   ```bash
   python3 scripts/scenario_profiles.py install hr-tool-dlp-vulnerable --slot demo-a --force
   ansible-playbook ansible/playbooks/deploy_litellm.yml
   ```

2. In the chatbot UI, select the matching LLM profile and MCP tool profile:

   | Control | Example |
   |---|---|
   | LLM profile | `demo-a` |
   | Use MCP tools | On |
   | Tool profile | `hr-tool-dlp-vulnerable` |

3. Tune the local prompt if needed:

   ```bash
   python3 scripts/instruction_profiles.py edit demo-a
   ansible-playbook ansible/playbooks/deploy_litellm.yml
   ```

4. When the local slot behaves correctly, copy the wording back into the
   scenario's tracked `instructions.txt` and update `profile.json` prompts or
   expected trace notes.

5. Validate before committing:

   ```bash
   python3 scripts/scenario_profiles.py validate
   python3 scripts/instruction_profiles.py validate
   python3 scripts/smoke_test.py
   ```

## MCP Tool Profiles

The MCP server exposes one shared `/tools` catalog. Scenario isolation happens
in the chatbot agent loop: the selected tool profile filters the fetched tool
schemas before they are sent to the model.

Use one scenario ID per tool profile where practical. Keep profiles narrow so
the model sees only tools that support the current story.

Current tracked scenario tool profiles:

| Tool profile | Tools |
|---|---|
| `fastfood-ordering` | `menu_search`, `nutrition_lookup`, `allergen_check`, `suggest_combo`, `build_order_summary` |
| `menu-poisoning` | `document_search`, `document_read`, `document_injection_check`, `menu_search`, `allergen_check` |
| `hr-policy-risk` | `employee_lookup`, `employee_search`, `hr_policy_lookup`, `policy_search`, `redaction_check` |
| `hr-tool-dlp-vulnerable` | `employee_sensitive_lookup_demo` |
| `hr-policy-rag-risk` | `document_search`, `document_read`, `document_injection_check`, `redaction_check` |
| `resume-screening-clean` | `document_list`, `document_search`, `document_read`, `resume_search`, `resume_summary` |
| `resume-prompt-injection` | `document_upload_simulation`, `resume_search`, `document_read`, `document_injection_check`, `resume_summary` |
| `resume-cloud-tool-pivot-safe` | `document_upload_simulation`, `document_read`, `document_injection_check`, `resume_summary` |
| `resume-cloud-tool-pivot-vulnerable` | `document_upload_simulation`, `document_read`, `resume_summary`, `cloud_bucket_list_demo` |
| `resume-cloud-tool-pivot` | `document_upload_simulation`, `document_read`, `document_injection_check`, `resume_summary`, `cloud_bucket_list_demo` |
| `support-ticket-triage` | `customer_lookup`, `customer_search`, `ticket_lookup`, `ticket_search`, `policy_lookup`, `policy_search`, `customer_ticket_summary`, `redaction_check` |
| `fortigate-operator` | `fortigate_system_status`, `fortigate_interface_status`, `fortigate_route_list`, `fortigate_policy_list`, `fortigate_address_list`, `fortigate_service_list` |

`all-tools` remains available for troubleshooting. `echo` is intentionally left
out of scenario profiles because it is a connectivity test utility.

Headless tests use the same profile filter:

```bash
kubectl -n chatbot exec deploy/chatbot -- python /app/agent_probe.py \
  --provider direct \
  --mcp-path direct \
  --tool-profile support-ticket-triage \
  --prompt "Which enterprise customers have open support tickets?"
```

`scripts/scenario_test_harness.py` defaults `--tool-profile` from
`profile.json` `mcp.tool_profile`.

## Curl Payloads

Each scenario can also carry raw curl replay payloads under
`curl-payloads/`. These files simulate tool-call transcripts without calling
the chatbot or MCP server.

Use them when the test target is FortiAIGate/LiteLLM/model handling of
tool-result-like content. Use the chatbot UI or `agent_probe.py` when the test
target is real MCP tool selection and execution.

Replay instructions are in [curl-payloads.md](curl-payloads.md).

## Deploy Boundary

You do not need to redeploy MCP when switching scenario prompts or tool
profiles. Redeploy MCP only when the shared tool service changes.

| Change | Deploy |
|---|---|
| Install/edit active prompt slot | `ansible-playbook ansible/playbooks/deploy_litellm.yml` |
| Change chatbot code or default tool-profile settings | publish chatbot image if needed, then `ansible-playbook ansible/playbooks/deploy_chatbots.yml` |
| Change MCP tool code, schemas, fixture data, documents, or FortiGate secret wiring | `ansible-playbook ansible/playbooks/deploy_mcp.yml` |
| Select another tool profile in the chatbot UI | No redeploy |
