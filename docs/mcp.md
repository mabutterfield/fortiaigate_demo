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
```

The default demo data file is:

```text
fortiaigate_demo/mcp/chart/files/tools.json
```

Set `mcp_tools_data_local_path` to another JSON file when testing alternate
customers, tickets, or policies. The Ansible role copies that file into the
staged Helm chart before deployment, so data changes do not require rebuilding
an image.

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
chatbot_frontend_system_prompt_source_path: "{{ chatbot_instruction_root }}/frontend/instructions.txt"
```

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
```
