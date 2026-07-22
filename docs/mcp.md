# MCP Demo Tools

The MCP demo tool server runs in the `mcp` namespace and is enabled by default.
It provides the tool-server side for the custom chatbot agent client.

The service is a small Python HTTP application with deterministic demo tools.
It exposes OpenAI-compatible function schemas at `/tools` so the custom chatbot
can let the LLM choose tools instead of forcing the user to select one manually.

Exact lookup tools:

- `customer_lookup`
- `ticket_lookup`
- `policy_lookup`
- `echo`

Search and join tools:

- `customer_search`
- `ticket_search`
- `policy_search`
- `customer_ticket_summary`

Synthetic HR demo tools:

- `employee_lookup`
- `employee_search`
- `hr_policy_lookup`
- `redaction_check`

Document and resume retrieval demo tools:

- `document_list`
- `document_search`
- `document_read`
- `resume_search`
- `resume_summary`
- `document_injection_check`
- `document_upload_simulation`
- `cloud_bucket_list_demo`

Fast food ordering demo tools:

- `menu_search`
- `nutrition_lookup`
- `allergen_check`
- `suggest_combo`
- `build_order_summary`

FortiGate read-only demo tools:

- `fortigate_system_status`
- `fortigate_interface_status`
- `fortigate_route_list`
- `fortigate_policy_list`
- `fortigate_address_list`
- `fortigate_service_list`

The FortiGate tools are advertised even when the appliance connection is not
available. In that case they return a successful `disabled` payload instead of
failing the whole agent loop. On a deployed lab, the MCP Ansible role enables
them only when it can find a FortiGate admin URL and the locally stored
read-only API token created by the FortiGate account playbook.

The service has both an internal Kubernetes endpoint and a generated public
NodePort by default:

```text
http://mcp-demo.mcp.svc.cluster.local:8000
http://<k3s-public-ip>:30084/tools
```

No ECR image publishing is required for the baseline. The Helm chart runs the
public `python:3.12-slim` image and mounts the server code plus demo data from a
ConfigMap.

## Deploy

```bash
cd ansible
ansible-playbook playbooks/deploy_mcp.yml
```

Check status:

```bash
ansible-playbook playbooks/status_mcp.yml
```

Use validation when the playbook should fail on a bad state:

```bash
ansible-playbook playbooks/validate_mcp.yml
```

Run a single sample tool call:

```bash
ansible-playbook playbooks/test_mcp.yml
```

Run deterministic Phase 8 document retrieval checks:

```bash
ansible-playbook playbooks/validate_phase8_documents.yml
```

This calls clean document listing, poisoned resume upload simulation, poisoned
resume read, prompt-injection detection, and the synthetic cloud inventory
tool.

The test playbook runs on the Ansible controller and calls the public HTTP
NodePort by default. It reads the k3s public IP from
`terraform/aws-ec2-k3s output public_ip`.

To run the same sample through SSH on the k3s host and curl the local NodePort:

```bash
ansible-playbook playbooks/test_mcp.yml \
  -e mcp_test_target_mode=remote_localhost
```

To test the HTTPS gateway instead of HTTP:

```bash
ansible-playbook playbooks/test_mcp.yml \
  -e mcp_test_use_https=true
```

The HTTPS test defaults to port `30447` and does not validate the self-signed
certificate. Set `mcp_test_validate_certs=true` when using a trusted
certificate.

Override the tool call when needed:

```bash
ansible-playbook playbooks/test_mcp.yml \
  -e mcp_test_tool=ticket_lookup \
  -e '{"mcp_test_arguments":{"ticket_id":"TCK-2001"}}'
```

Test the FortiGate system-status MCP tool:

```bash
ansible-playbook playbooks/test_mcp.yml \
  -e mcp_test_tool=fortigate_system_status \
  -e '{"mcp_test_arguments":{}}'
```

Test clean document search:

```bash
ansible-playbook playbooks/test_mcp.yml \
  -e mcp_test_tool=document_search \
  -e '{"mcp_test_arguments":{"query":"Python","document_type":"resume"}}'
```

Test that attack fixtures are blocked by default:

```bash
ansible-playbook playbooks/test_mcp.yml \
  -e mcp_test_tool=document_read \
  -e '{"mcp_test_arguments":{"document_id":"RESUME-9001"}}'
```

That call should return `ok=false` because `RESUME-9001` is an attack fixture.
Run the explicit attack-fixture read only for a planned demo:

```bash
ansible-playbook playbooks/test_mcp.yml \
  -e mcp_test_tool=document_read \
  -e '{"mcp_test_arguments":{"document_id":"RESUME-9001","include_attack":true}}'
```

Check the same poisoned resume for prompt-injection indicators:

```bash
ansible-playbook playbooks/test_mcp.yml \
  -e mcp_test_tool=document_injection_check \
  -e '{"mcp_test_arguments":{"document_id":"RESUME-9001","include_attack":true}}'
```

If that test fails, the playbook prints the MCP response body. FortiGate API
failures include the target URL and FortiGate HTTP detail without printing the
bearer token.

Override the target URL when testing a different endpoint:

```bash
ansible-playbook playbooks/test_mcp.yml \
  -e mcp_test_base_url_override=http://203.0.113.10:30084
```

## Configuration

Repo defaults live in tracked `ansible/group_vars/system.yml`; local overrides
belong in ignored `ansible/group_vars/user.yml`:

```yaml
mcp_enabled: true
mcp_namespace: mcp
mcp_release_name: mcp-demo
mcp_service_type: NodePort
mcp_service_port: 8000
mcp_node_port: "{{ demo_mcp_http_port | default(30084) }}"
mcp_tools_data_local_path: "{{ mcp_chart_local_path }}/files/tools.json"
mcp_fortigate_tools_enabled: true
mcp_fortigate_api_account_name: faig-readonly-api
mcp_fortigate_base_url: ""
mcp_fortigate_admin_port: 8443
mcp_fortigate_verify_tls: false
mcp_fortigate_validate_token: true
```

The default demo data file is:

```text
fortiaigate_demo/mcp/chart/files/tools.json
```

The Phase 8 document library is mounted from:

```text
fortiaigate_demo/mcp/chart/files/documents/
```

The document index is:

```text
fortiaigate_demo/mcp/chart/files/documents/documents.json
```

Tracked documents are plain text or Markdown fixtures. They include clean
synthetic resumes and policies plus clearly labeled attack fixtures for prompt
injection and document poisoning. The fixture metadata uses S3-shaped
`source_uri` values so the same tool contracts can later support a real
read-only S3 backend.

Attack fixtures are opt-in. Document tools hide them unless
`include_attack=true` is passed. This keeps normal validation on clean data
while allowing explicit attack demos to retrieve the poisoned content.

Set `mcp_tools_data_local_path` to another JSON file when testing alternate
customers, tickets, policies, or menu data. The Ansible role copies that file
into the staged Helm chart before deployment, so data changes do not require
rebuilding an image.

FortiGate MCP secrets are not committed. The role reads the generated API token
from ignored local Ansible secret material and writes a Kubernetes secret named
`fortigate-readonly-api` when both the token and management URL are available.
Automated quickstart runs `configure_fortigate_api_accounts.yml` before
`deploy_mcp.yml`; that API-account play regenerates the read-only token when
the local token file is missing, rotation is requested, or the saved token was
generated for a different FortiGate EC2 instance ID.
By default, `deploy_mcp.yml` targets the FortiGate port1 private IP from
`terraform/aws-fortigate output fortigate_public_private_ip`, using
`mcp_fortigate_admin_port` for the HTTPS admin port. Set
`mcp_fortigate_base_url` only when the MCP server should target a different
management URL. Before publishing the Kubernetes secret, the role validates the
saved token against `/api/v2/monitor/system/status` from the k3s host. If that
probe fails, the play leaves the FortiGate MCP secret unchanged, deploys MCP
with FortiGate tools disabled, and prints the recovery commands. Rotate the
local read-only token and redeploy MCP:

```bash
ansible-playbook -i ansible/inventory/fortigate.generated.ini \
  ansible/playbooks/configure_fortigate_api_accounts.yml \
  -e fortigate_readonly_api_account_rotate_token=true

ansible-playbook ansible/playbooks/deploy_mcp.yml
```

The server consumes these environment variables:

```text
MCP_FORTIGATE_ENABLED
MCP_FORTIGATE_BASE_URL
MCP_FORTIGATE_API_TOKEN
MCP_FORTIGATE_VDOM
MCP_FORTIGATE_VERIFY_TLS
MCP_FORTIGATE_TIMEOUT_SECONDS
```

## HTTPS Gateway

When `demo_https_gateway_enabled: true`, the HTTPS gateway also exposes MCP:

```text
https://<k3s-public-ip>:30447/tools
```

Terraform opens the generated MCP HTTP and HTTPS ports in AWS public mode after
`terraform/aws-ec2-k3s apply` regenerates `ansible/group_vars/ports.generated.yml`.

## Test Calls

Validation runs these from inside the MCP deployment and checks the NodePort
health endpoint. The same API is useful for manual tests:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/tools
curl -X POST http://127.0.0.1:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"tool":"customer_lookup","arguments":{"customer_id":"CUST-1001"}}'
```

This baseline is intentionally simple. The Python chatbot agent loop can use
these tools today, and the Phase 6 FortiWeb path can front MCP/tool traffic.
The menu tools are deterministic and meant to show an ordering assistant flow
without placing a real order. The FortiGate tools are read-only and intended to
show the model using a real infrastructure data source. The HR tools use
synthetic data and are intended to demonstrate safe lookup, redaction, and
policy-boundary behavior.

## Chatbot Tool Toggle

The custom chatbot UI can run an LLM-directed MCP tool loop. The browser
sidebar exposes:

- `Model`: LiteLLM model/profile alias, such as `pass-bedrock`, `demo-a`, or `demo-b`
- `Use MCP tools`: simple on/off toggle
- `MCP path`: direct MCP or FortiWeb-fronted MCP
- `Max tool rounds`: limit for model-requested tool calls

Current default path:

```text
Browser
  -> chatbot UI
      -> Direct LiteLLM or FortiAIGate -> LiteLLM -> Bedrock
      -> MCP
      -> Direct LiteLLM or FortiAIGate -> LiteLLM -> Bedrock
```

Expected flow:

```text
1. User asks a question.
2. Chatbot sends the question plus available MCP tool schemas to the selected LLM path.
3. The model requests one or more tool calls when needed.
4. Chatbot calls MCP and sends tool results back through the selected LLM path.
5. The model returns the final answer.
6. Chatbot shows the final answer plus an expandable tool-call trace.
```

Config variables:

```yaml
chatbot_mcp_enabled: false
chatbot_mcp_direct_base_url: "{{ mcp_internal_base_url }}"
chatbot_mcp_fortiweb_base_url: "{{ fortiweb_mcp_http_base_url | default('') }}"
chatbot_mcp_default_path: direct
chatbot_mcp_max_tool_rounds: 3
```

Chatbot frontend instructions are disabled by default because backend demo
instructions normally live in LiteLLM profiles. To intentionally add a
browser/UI-layer system prompt, set one of:

```yaml
chatbot_frontend_system_prompt: "Inline system prompt text"
chatbot_frontend_system_prompt_source_path: "{{ chatbot_instruction_local_root }}/frontend/instructions.txt"
```

Tracked examples live under `chatbot/instructions/examples/`. Active local
instruction files live under ignored `chatbot/instructions/local/` and can be
created or opened with `scripts/instruction_profiles.py`.

When FortiWeb Terraform has generated `fortiweb.generated.yml`,
`chatbot_mcp_fortiweb_base_url` defaults to FortiWeb's port1 private IP on the
MCP HTTP NodePort. Set `chatbot_mcp_default_path: fortiweb` to make that the
default chatbot path.

Useful test prompts:

```text
Show me all customers with open tickets.
Which enterprise customers are in us-east?
Find policies related to tool access.
Lookup ticket TCK-2001 and summarize the customer impact.
Find a chicken menu item under 600 calories.
Build an order with MENU-1001, MENU-2002, and MENU-3001.
Get the FortiGate system status.
```
