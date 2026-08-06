# FortiGate Traffic Demo

This Phase 10E runbook covers two FortiGate-only demo paths. These are separate
from the FortiAIGate guard demos and do not change the default AWS quickstart or
local quickstart behavior.

## Goals

1. Generate real FortiGate Application Control evidence by touching several AI
   application endpoints from a VM behind FortiGate.
2. Show FortiGate inspection on inbound AI traffic by routing chatbot or curl
   traffic to FortiGate listener ports, then forwarding that traffic to LiteLLM
   or FortiAIGate.

The default quickstarts do not enable these paths. Operators can either build
the FortiGate objects manually or opt in to the Ansible-generated objects after
confirming the lab interface/IP mapping.

## Non-Goals

- Do not insert, forge, or present fabricated FortiGate log records as real
  appliance telemetry.
- Do not make FortiGate traversal required for the default FAIG demo.
- Do not commit FortiGate credentials, API tokens, packet captures, or generated
  local variables.
- Do not use this path as a replacement for FortiAIGate prompt, DLP, or guard
  validation.

## Outbound AI App Detection From A VM

Use this path when a small Ubuntu VM or lab host sits behind FortiGate and uses
FortiGate as its normal default gateway. The script sends direct HTTP or HTTPS
requests by default. It also clears proxy-related environment variables inside
the script process so inherited workstation settings do not change the path.

FortiGate manual setup:

| Area | Requirement |
|---|---|
| Test source | Ubuntu VM or lab host behind FortiGate. |
| Routing | Test source default gateway or selected route points through FortiGate. |
| Policy | Firewall policy permits the test source to reach the internet. |
| Security profiles | Application Control and logging are enabled on the policy. |
| DNS/internet | Test source can resolve DNS and reach HTTP/HTTPS through FortiGate. |
| TLS inspection | Optional for first pass; enable deep inspection when app/category detection needs more than SNI/certificate/destination metadata. |

Preview the built-in targets:

```bash
python3 scripts/fortigate_ai_app_proxy_touch.py --list-targets
```

Built-in target labels use FortiGuard-style application names where practical,
including ChatGPT, Gemini, NotebookLM, Vertex AI, Claude, Copilot, Azure
OpenAI, Hugging Face, DeepSeek, Mistral API, OpenRouter, Groq, Meta AI,
Replicate, and Protocol.A2A.Tasks. Some API targets are expected to return HTTP
401, 403, or 404 without credentials; those responses still prove the session
reached the remote application.

Dry-run the default target plan:

```bash
python3 scripts/fortigate_ai_app_proxy_touch.py
```

Execute the default target plan:

```bash
python3 scripts/fortigate_ai_app_proxy_touch.py \
  --execute \
  --method GET \
  --yes
```

GET mode reads only the first `--read-bytes` bytes from each response and does
not send a `Range` header by default. Use `--range-request` only when testing
partial-content behavior, because range requests can change FortiGate
classification.

Use `--proxy-url` only when explicitly testing a FortiGate explicit proxy from a
workstation that does not route through FortiGate:

```bash
python3 scripts/fortigate_ai_app_proxy_touch.py \
  --proxy-url http://<fgt-ip>:<proxy-port> \
  --execute \
  --method GET \
  --yes
```

Equivalent one-off curl sanity check:

```bash
curl -kv --noproxy "" --proxy http://<fgt-ip>:<proxy-port> https://www.google.com/
```

If FortiGate is performing HTTPS inspection with a certificate that this
workstation does not trust, add `--insecure` for this lab test:

```bash
python3 scripts/fortigate_ai_app_proxy_touch.py \
  --proxy-url http://<fgt-ip>:<proxy-port> \
  --execute \
  --yes \
  --insecure
```

Expected FortiGate evidence:

| Field | What to look for |
|---|---|
| Policy | The firewall policy handling routed VM traffic, or the explicit proxy policy when `--proxy-url` is used. |
| Application | Recognized AI app names or categories for ChatGPT, Claude, Gemini, Copilot, Azure OpenAI, Hugging Face, DeepSeek, Mistral, OpenRouter, Groq, Meta AI, Replicate, or Protocol.A2A.Tasks targets when FortiGuard classification supports them. |
| Host/SNI/URL | Destination hostname or URL matching the script target. |
| Action | Permit, monitor, block, or other action applied by the policy/profile. |
| Timestamp | Matches the script run time. |
| User-Agent | `FAIG-Phase10E-FortiGate-AppTouch/1.0` unless overridden. |

HTTP errors such as 403 or 405 can still be successful test evidence. They mean
the request reached the destination and should have generated FortiGate
session/log data.

The explicit proxy path is useful for connectivity and policy testing, but it
may classify only the browser/proxy transaction. If Application Control still
shows generic `HTTPS.Browser` or browser signatures with deep inspection, prefer
the routed VM path.

### MCP And Bedrock Probe Targets

Use these optional target sets when FortiGate needs evidence for MCP or AWS
Bedrock application signatures. Run them from the routed VM behind FortiGate
when possible so FortiGate sees normal client-to-internet traffic.

Copy the script to the temporary Ubuntu test VM when the repo is on the
workstation:

```bash
scp scripts/fortigate_ai_app_proxy_touch.py \
  mike@192.168.248.10:~/fortigate_ai_app_proxy_touch.py
```

Remote MCP probes send an unauthenticated JSON-RPC `initialize` request. HTTP
401, 403, 404, or protocol errors can still be useful FortiGate evidence
because the request reached the real MCP host.

```bash
python3 ~/fortigate_ai_app_proxy_touch.py \
  --target-set mcp \
  --execute \
  --insecure \
  --yes
```

For GitHub MCP, export a GitHub token on the test VM and run a real MCP
`tools/list` sequence. This sends `initialize`, `notifications/initialized`,
and `tools/list` JSON-RPC requests. The token is read from the named
environment variable and is not printed by the script.

```bash
read -rs GITHUB_MCP_TOKEN; echo
export GITHUB_MCP_TOKEN

python3 ~/fortigate_ai_app_proxy_touch.py \
  --target-set mcp \
  --mcp-target GitHub.MCP \
  --mcp-mode tools-list \
  --mcp-token-env GITHUB_MCP_TOKEN \
  --execute \
  --insecure \
  --yes
```

After `tools/list` works, send read-only GitHub MCP `tools/call` probes. These
examples assume the token has read access to repository metadata and contents
for `mabutterfield/aws-demos`.

```bash
python3 ~/fortigate_ai_app_proxy_touch.py \
  --target-set mcp \
  --mcp-target GitHub.MCP \
  --mcp-mode tool-call \
  --mcp-token-env GITHUB_MCP_TOKEN \
  --mcp-tool get_me \
  --mcp-arguments-json '{}' \
  --execute \
  --insecure \
  --yes
```

```bash
python3 ~/fortigate_ai_app_proxy_touch.py \
  --target-set mcp \
  --mcp-target GitHub.MCP \
  --mcp-mode tool-call \
  --mcp-token-env GITHUB_MCP_TOKEN \
  --mcp-tool list_branches \
  --mcp-arguments-json '{"owner":"mabutterfield","repo":"aws-demos","perPage":5}' \
  --execute \
  --insecure \
  --yes
```

```bash
python3 ~/fortigate_ai_app_proxy_touch.py \
  --target-set mcp \
  --mcp-target GitHub.MCP \
  --mcp-mode tool-call \
  --mcp-token-env GITHUB_MCP_TOKEN \
  --mcp-tool list_commits \
  --mcp-arguments-json '{"owner":"mabutterfield","repo":"aws-demos","perPage":3}' \
  --execute \
  --insecure \
  --yes
```

```bash
python3 ~/fortigate_ai_app_proxy_touch.py \
  --target-set mcp \
  --mcp-target GitHub.MCP \
  --mcp-mode tool-call \
  --mcp-token-env GITHUB_MCP_TOKEN \
  --mcp-tool get_file_contents \
  --mcp-arguments-json '{"owner":"mabutterfield","repo":"aws-demos","path":"README.md"}' \
  --execute \
  --insecure \
  --yes
```

```bash
python3 ~/fortigate_ai_app_proxy_touch.py \
  --target-set mcp \
  --mcp-target GitHub.MCP \
  --mcp-mode tool-call \
  --mcp-token-env GITHUB_MCP_TOKEN \
  --mcp-tool search_code \
  --mcp-arguments-json '{"query":"repo:mabutterfield/aws-demos terraform"}' \
  --execute \
  --insecure \
  --yes
```

FortiGate deep-inspection logs should show JSON-RPC `tools/call`, the selected
tool name, and the argument object when the HTTPS session is decrypted.

Default MCP targets:

| Label | Endpoint |
|---|---|
| `GitHub.MCP` | `https://api.githubcopilot.com/mcp/` |
| `GitLab.MCP` | `https://gitlab.com/api/v4/mcp` |
| `AWS.MCP` | `https://aws-mcp.us-east-1.api.aws/mcp` |

Bedrock probes send a real signed Bedrock Runtime Converse request. This
requires temporary AWS credentials on the VM and may incur a small model charge.
Do not write the credentials into repo files, shell history snippets, or
tracked documentation. Successful Bedrock runs print the assistant response
text plus usage and latency metadata when the response body contains them. The
default Bedrock response budget is 256 output tokens because reasoning models
can consume a small 64-token budget before returning visible text.

```bash
read -r AWS_ACCESS_KEY_ID
read -rs AWS_SECRET_ACCESS_KEY; echo
read -rs AWS_SESSION_TOKEN; echo
export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
export AWS_REGION=us-east-1
export BEDROCK_MODEL_ID=openai.gpt-oss-20b-1:0

python3 ~/fortigate_ai_app_proxy_touch.py \
  --target-set bedrock \
  --bedrock-prompt "tell me a dad joke" \
  --execute \
  --insecure \
  --yes
```

If the credentials are long-lived rather than session credentials, omit
`AWS_SESSION_TOKEN`. The script prints whether the three AWS credential
environment variables are present, but it does not print their values.

MCP and Bedrock can be combined in one run:

```bash
python3 ~/fortigate_ai_app_proxy_touch.py \
  --target-set mcp \
  --target-set bedrock \
  --execute \
  --insecure \
  --yes
```

## Inbound AI Inspection

Use these paths to show FortiGate handling AI traffic before it reaches the
model or FortiAIGate. The LiteLLM path is plain HTTP for straightforward LLM
content inspection. The FortiAIGate path is HTTPS and is useful for testing
FortiGate TLS/deep-inspection behavior before traffic reaches FAIG.

LiteLLM target path:

```text
chatbot or curl -> http://<fgt-ip>:4000/v1 -> FortiGate policy/NAT/proxy -> LiteLLM /v1
```

FortiAIGate target path:

```text
chatbot or curl -> https://<fgt-ip>/v1/<flow> -> FortiGate policy/NAT/proxy -> FortiAIGate HTTPS ingress
```

After FortiGate is configured, enable optional chatbot routing in ignored
`ansible/group_vars/user.yml`:

```yaml
chatbot_fortigate_litellm_base_url: http://<fgt-ip>:4000/v1
chatbot_faig_base_url: https://<fgt-ip>
```

For AWS, prefer FortiGate port1's private IP for chatbot/pod traffic:

```yaml
chatbot_fortigate_litellm_base_url: "http://{{ fortigate_public_private_ip }}:4000/v1"
chatbot_faig_base_url: "https://{{ fortigate_public_private_ip }}"
```

The AWS FortiGate security group exposes TCP `4000` and `443` from trusted
public CIDRs by default. The FortiGate admin service uses `8443` in this demo,
so `443` can be used for the FAIG VIP.

Then redeploy the chatbot:

```bash
ansible-playbook ansible/playbooks/deploy_chatbots.yml
```

The chatbot sidebar shows `FortiGate -> LiteLLM` when
`chatbot_fortigate_litellm_base_url` is configured. FAIG Static and FAIG
Intelligent routes use `chatbot_faig_base_url`; setting that to the FortiGate
HTTPS listener sends the normal `/v1/passthrough`, `/v1/demo-a`, and
`/v1/demo-b` traffic through FortiGate before FAIG.

FortiGate manual setup:

| Area | Requirement |
|---|---|
| Listener | FortiGate accepts HTTP on `<fgt-ip>:4000` for LiteLLM and HTTPS on `<fgt-ip>:443` for FortiAIGate. |
| Forwarding | Traffic is forwarded or NATed to the matching backend service. |
| Policy | Traditional firewall policy permits the source to the listener and enables full traffic logging. |
| Security profiles | LiteLLM HTTP uses SSL/SSH profile `certificate-inspection` plus Application Control `default`; FAIG HTTPS uses SSL/SSH profile `custom-deep-inspection` plus Application Control `default`. |
| Scope | Keep this as a FortiGate inspection demo, not a FAIG guard test. |

Basic curl validation:

```bash
curl -sS http://<fgt-ip>:4000/v1/models
curl -ksS https://<fgt-ip>/v1/passthrough/models
```

Use `-k` only for this lab FAIG HTTPS path when FortiGate deep inspection or
the backend gateway presents a certificate chain your workstation does not
trust.

Chat completion validation:

```bash
curl -sS http://<fgt-ip>:4000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <litellm-api-key>' \
  -d '{
    "model": "demo-a",
    "messages": [
      {
        "role": "user",
        "content": "FORTIGATE_PROXY_TEST: Tell me about FortiGate for a branch office."
      }
    ]
  }'
```

Expected FortiGate evidence:

| Field | What to look for |
|---|---|
| Policy | The inbound policy or VIP/proxy policy handling `:4000`. |
| Service | HTTP traffic to the FortiGate listener and backend LiteLLM service. |
| Content marker | `FORTIGATE_PROXY_TEST` visible in logs or inspection evidence when the selected FortiGate profile records it. |
| Model path | `/v1/models` or `/v1/chat/completions`. |
| Comparison | FortiGate sees HTTP LLM content here; FAIG guard logs remain the source of truth for FAIG-specific detection/prevention demos. |

Pod-local validation through the deployed chatbot agent:

```bash
python3 -m load_test.traffic_generator --mode traffic \
  --route fortigate-litellm \
  --use-case steady \
  --duration 30 \
  --rate 2 \
  --dry-run
```

Remove `--dry-run` after confirming the route plan. The traffic-generator route
uses the deployed chatbot pod. The LiteLLM route path is:

```text
chatbot pod -> FortiGate :4000 -> LiteLLM
```

For FAIG route testing through FortiGate, set `chatbot_faig_base_url` to the
FortiGate HTTPS listener and use the normal FAIG Static route choices in the
chatbot or traffic generator:

```text
chatbot pod -> FortiGate :443 -> FortiAIGate HTTPS ingress
```

## Optional Ansible-Managed FortiGate Objects

The FortiGate role can generate the basic listener services, VIP objects, static
route, and inbound firewall policies for the two Phase 10 cloud inspection
paths. This is off by default.

For AWS cloud labs, this single ignored variable is enough for the FortiGate
config role to resolve the listener IP, k3s backend IP, ports, static route,
VIPs, and policies from generated Terraform and FortiGate inventory values:

```yaml
fortigate_llm_proxy_enabled: true
```

Fresh labs can leave these management flags at their defaults:

```yaml
fortigate_llm_proxy_manage_services: true
fortigate_llm_proxy_manage_vips: true
fortigate_llm_proxy_manage_policies: true
```

In AWS, the role also creates a VPC static route through port2 when
`fortigate_llm_proxy_enabled=true`:

```yaml
fortigate_static_route_vpc_enabled: true
fortigate_static_route_vpc_destination: "{{ aws_vpc_cidr }}"
fortigate_static_route_vpc_gateway: "{{ aws_fortigate_internal_subnet_cidr | regex_replace('\\.[0-9]+/.*$', '.1') }}"
```

The generated proxy policy uses `nat: enable` by default so replies from k3s
NodePorts return through FortiGate instead of taking the k3s host's normal
public-subnet route.

If listener VIPs already exist, keep them in place and disable generated VIP
management:

```yaml
fortigate_llm_proxy_manage_vips: false
fortigate_llm_proxy_paths:
  - name: litellm
    service_name: FAIG_LITELLM_LISTENER_4000
    policy_service_name: FAIG_LITELLM_BACKEND_30083
    policy_service_ports:
      - 4000
      - "{{ litellm_node_port | default(demo_litellm_http_port | default(30083)) | int }}"
    vip_name: LiteLLM
    policy_name: allow-faig-litellm-http-proxy
    policyid: 9400
    extport: 4000
    mappedport: "{{ litellm_node_port | default(demo_litellm_http_port | default(30083)) | int }}"
    utm_status: enable
    ssl_ssh_profile: certificate-inspection
    application_list: default
    comment: "Phase 10 FortiGate plain HTTP LiteLLM inspection path"
  - name: faig_https
    service_name: FAIG_HTTPS_LISTENER_443
    vip_name: FortiAIGateHTTPS
    policy_name: allow-faig-https-proxy
    policyid: 9401
    extport: 443
    mappedport: 443
    utm_status: enable
    ssl_ssh_profile: custom-deep-inspection
    application_list: default
    comment: "Phase 10 FortiGate HTTPS FortiAIGate inspection path"
```

Generated objects:

| Object type | LiteLLM | FortiAIGate |
|---|---|---|
| Listener service | `FAIG_LITELLM_LISTENER_4000` | `FAIG_HTTPS_LISTENER_443` |
| Policy service | `FAIG_LITELLM_BACKEND_30083`, TCP `4000 30083` by default | `FAIG_HTTPS_LISTENER_443` |
| VIP | `VIP_FAIG_LITELLM_HTTP_PROXY` | `VIP_FAIG_HTTPS_PROXY` |
| Policy | `allow-faig-litellm-http-proxy` | `allow-faig-https-proxy` |
| Listener | TCP `4000` | TCP `443` |
| Backend | k3s LiteLLM NodePort | k3s HTTPS ingress |

Run a check first:

```bash
ansible-playbook -i ansible/inventory/fortigate.generated.ini \
  ansible/playbooks/configure_fortigate.yml \
  -e fortigate_llm_proxy_enabled=true \
  --check
```

For a local FortiGate inventory:

```bash
ansible-playbook -i ansible/inventory/fortigate.local.generated.ini \
  ansible/playbooks/configure_fortigate.yml \
  -e deployment_target=local \
  -e fortigate_llm_proxy_enabled=true \
  --check
```

When the check output matches the intended policy shape, remove `--check`.
Use `fortigate_llm_proxy_policy_common` or per-path `policy_overrides` only when
the lab needs additional security-profile, inspection, logging, or policy-order
fields.
