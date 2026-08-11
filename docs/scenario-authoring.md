# Scenario Authoring Guide

Phase 10 is transitional. Current candidate scenario profiles live under
`chatbot/scenarios/examples/<scenario-id>/`. Archived scenario profiles live
under `archived_scenarios/<scenario-id>/` and are inactive in the catalog.
Each scenario has:

- `profile.json`: tracked metadata, prompt examples, expected traces, data
  sources, and the intended MCP tool profile.
- `instructions.txt`: tracked backend instructions installed into `demo-a` or
  `demo-b` for repeatable demos.

The active installed instructions live under `chatbot/instructions/local/`.
Those files are ignored by Git so they can be tuned during recording without
changing the tracked examples.

For Phase 10 candidate scenarios, keep operator-facing settings explicit in the
runbook whenever a profile changes. Phase 11 is planned as the v1.0 baseline
and should replace compatibility slots with generated scenario metadata.

- instruction slot
- model/profile or route
- context mode
- MCP enabled/disabled
- MCP path
- MCP tool profile
- max tool rounds
- simplified chatbot demo profiles
- expected tools and expected response marker

## Edit And Test Workflow

1. Install the tracked scenario into a local slot:

   ```bash
   python3 scripts/scenario_profiles.py install fortigate-operator --slot demo-a --force
   ansible-playbook ansible/playbooks/deploy_litellm.yml
   ```

2. In the chatbot UI, select the matching LLM profile and MCP tool profile:

   | Control | Example |
   |---|---|
   | LLM profile | `demo-a` |
   | Use MCP tools | On |
   | MCP path | Direct MCP first, then FortiWeb MCP only when the proxy path is configured |
| Tool profile | `fortigate-operator` |

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

Current active/candidate scenario tool profiles:

| Tool profile | Tools |
|---|---|
| none | `fortistore-injection` disables MCP tools for product-advisor prompt-injection testing |
| `hr-tool-dlp` | `employee_search`, `employee_lookup`, `employee_sensitive_lookup_demo`, `employee_table_with_cc` |
| `fortigate-operator` | read-only FortiGate status/configuration tools |
| `resume-screening-clean` | resume/document retrieval tools |
| `resume-prompt-injection` | resume/document retrieval tools with attack fixture |
| `resume-cloud-tool-pivot` | resume/document retrieval plus synthetic cloud inventory tools |
| `resume-cloud-tool-pivot-safe` | safe comparison profile for resume tool-pivot testing |
| `resume-cloud-tool-pivot-vulnerable` | vulnerable comparison profile for resume tool-pivot testing |

During `deploy_chatbots.yml`, the chatbot role reads installed scenario
metadata from the configured local slots, defaulting to `demo-a` and `demo-b`.
It generates the MCP profile dropdown from those installed scenarios:

- `all-tools` means all tools required by installed MCP-enabled scenarios.
- Scenario-specific profiles expose only that scenario's required tools.
- Archived or inactive profiles are not shown just because their files exist.
- `debug-all-server-tools` exposes every MCP server tool only when
  `chatbot_mcp_show_debug_all_server_tools: true` is set.

Changing which scenario is installed normally needs only the relevant scenario
install command and `deploy_chatbots.yml` to update the dropdown. Changing MCP
tool code or data still requires `deploy_mcp.yml`. Changing chatbot filtering
logic requires rebuilding/publishing the chatbot image.

## Simplified Chatbot Profiles

The chatbot has two UI modes:

- `Detailed`: the default operator/debug view with explicit controls for path,
  route, model/profile, context, frontend instructions, and MCP tools.
- `Simplified`: a presenter view where one `Demo Profile` dropdown applies the
  path, route, model/profile, context, frontend instruction, and MCP settings.

Scenario `profile.json` files can define `chatbot_demo_profiles`. During
`deploy_chatbots.yml`, the chatbot role reads installed scenario metadata from
`chatbot_simplified_profile_slots`, defaulting to `demo-a`, `demo-b`, and
`frontend`, and passes those presets to the app. Existing installed scenarios
can also pick up tracked preset changes from their scenario ID on the next
chatbot deploy.

Example profile:

```json
{
  "id": "fortigate-operator-direct",
  "label": "FortiGate Operator - Direct",
  "provider_path": "faig-static",
  "route": "demo-a",
  "mcp_enabled": true,
  "mcp_path": "direct",
  "mcp_tool_profile": "fortigate-operator",
  "mcp_max_tool_rounds": 3,
  "frontend_system_prompt_enabled": false,
  "context_mode": "recent",
  "context_window": 8
}
```

Use intent-based labels such as `Detect Only`, `Input Protect`, or `Output DLP`
instead of exposing internal route names. Route IDs such as `demo-a` and
`demo-c` are implementation details and can be renamed later without changing
the presenter-facing dropdown labels.

Inactive legacy profiles still declare their historical tool profiles in
`chatbot/scenarios/examples/catalog.json`, but most files now live under
`archived_scenarios/`. They can be reactivated by moving or copying the folder
back under `chatbot/scenarios/examples/`, updating the catalog path, and setting
`"active": true`. They can be inspected with `--include-inactive` options where
supported.

`echo` is intentionally left out of scenario profiles because it is a
connectivity test utility.

Headless tests use the same profile filter:

```bash
kubectl -n chatbot exec deploy/chatbot -- python /app/agent_probe.py \
  --provider direct \
  --mcp-path direct \
  --tool-profile fortigate-operator \
  --prompt "Show me the FortiGate system status."
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

Scenario-specific runbooks assume the MCP server and chatbot tool-profile
inventory are already deployed. You do not need to redeploy MCP or the chatbot
when switching scenario prompts, installing a scenario into a LiteLLM slot, or
selecting another tool profile in the UI. Redeploy MCP or the chatbot only when
developing the scenario implementation itself.

| Change | Deploy |
|---|---|
| Install/edit active prompt slot | `ansible-playbook ansible/playbooks/deploy_litellm.yml` |
| Change chatbot code or default tool-profile settings | publish chatbot image if needed, then `ansible-playbook ansible/playbooks/deploy_chatbots.yml` |
| Change MCP tool code, schemas, fixture data, documents, or FortiGate secret wiring | `ansible-playbook ansible/playbooks/deploy_mcp.yml` |
| Select another tool profile in the chatbot UI | No redeploy |
