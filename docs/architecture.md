# Architecture

The current demo architecture is a single-node k3s lab deployed on an AWS GPU
instance with FortiGate and FortiWeb appliances enabled by default for the full
AWS demo. Terraform creates AWS infrastructure. Ansible configures the
host, Kubernetes, FortiAIGate, demo applications, and appliance baselines.

## Current Flow

```text
Operator workstation
  -> Terraform
     -> ECR repositories
     -> AWS prep IAM/EIPs/Bedrock credentials
     -> VPC/subnets/security group/EC2 k3s host
     -> FortiGate/FortiWeb appliance EC2 instances
  -> Ansible
     -> publish images
     -> bootstrap GPU k3s
     -> deploy FortiAIGate
     -> configure FortiGate baseline and API accounts
     -> configure FortiWeb routes, interfaces, and reverse proxy
     -> deploy LiteLLM/MCP/chatbot/demo home/HTTPS gateway
     -> deploy Open WebUI when enabled
```

## Runtime Components

- k3s runs on a single Ubuntu 24.04 GPU host.
- nginx ingress replaces the default k3s Traefik path.
- FortiAIGate is deployed from the vendor Helm chart plus post-render patches.
- LiteLLM provides the shared OpenAI-compatible direct model proxy.
- The custom chatbot is the primary consolidated demo UI.
- Open WebUI is available as an optional secondary chat UI when `openwebui_enabled=true`.
- The MCP demo server provides deterministic internal tool responses for the chatbot agent path, including customer/ticket examples, a fast-food ordering demo, and read-only FortiGate status/config queries.
- The HTTPS gateway provides self-signed HTTPS listener ports for the demo services.
- The demo home page links to direct, FortiWeb-fronted, HTTP, and HTTPS endpoints when available.
- FortiGate is configured by Ansible for system baseline, generated address and service objects, VIP support, and application API accounts.
- FortiWeb is configured by Ansible for front/back interfaces, static routes, traffic logging, and no-inspection reverse-proxy policies for demo NodePorts.
- Amazon Bedrock is the current AWS-first provider target.
- Ollama is an alternate/future provider path and is not deployed by the default workflow.

## Traffic Direction

The default no-DNS demo path uses public NodePorts for demo UIs and direct
FortiAIGate access. FortiWeb also publishes pass-through reverse-proxy paths
for the generated demo NodePorts. FortiGate configuration is in place for
address/service/VIP/policy objects, but active traffic policies are intentionally
empty until a specific FortiGate traffic path is selected.

Current LLM paths:

```text
Direct path:
Browser UI -> LiteLLM -> Bedrock

FortiAIGate-inspected path:
Browser UI -> FortiAIGate explicit /v1/<flow-name> path -> LiteLLM -> Bedrock
```

MCP baseline:

```text
custom chatbot UI -> MCP demo tools
  -> deterministic customer/ticket/policy/menu data
  -> read-only FortiGate API when appliance credentials are available
```

The MCP service keeps the internal Kubernetes endpoint
`http://mcp-demo.mcp.svc.cluster.local:8000` and exposes generated demo ports
for direct HTTP/HTTPS testing.

Chatbot agent/tool path:

```text
Browser
  -> custom chatbot UI
      -> Direct LiteLLM or FortiAIGate -> LiteLLM -> Bedrock
      -> MCP demo tools
      -> Direct LiteLLM or FortiAIGate -> LiteLLM -> Bedrock
```

The chatbot UI has a browser-side MCP on/off toggle. When enabled, the chatbot
sends all MCP tool schemas to the selected model path, executes model-requested
tool calls, and sends results back for the final answer. The MCP endpoint
defaults to direct in-cluster MCP and can be switched to the FortiWeb-fronted
MCP URL.

FortiWeb front/back model:

```text
Browser or VPC client
  -> FortiWeb port1 listener
      -> FortiWeb reverse-proxy server policy
          -> FortiWeb port2 route to VPC/k3s private IP
              -> k3s NodePort service
```

FortiWeb listens on port1 using the public EIP or port1 private IP. It reaches
k3s through port2 using the configured VPC static route. HTTP listeners proxy
to HTTP NodePorts. HTTPS listeners use SSL on both the FortiWeb front end and
the k3s HTTPS gateway back end.

Current ports and deployment defaults are documented in
[Current Baseline](current-baseline.md).

See [AWS k3s Foundation](aws-k3s-foundation.md) for detailed AWS network
layout, subnet mode, and instance behavior.
