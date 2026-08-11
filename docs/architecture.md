# Architecture

The demo has two supported v1.0 topologies:

- AWS quickstart, the primary supported path.
- Local Ubuntu hardware mode, a supported lab path for operator-owned GPU
  hosts and trusted local networks.

Both paths converge on the same single-node k3s application layer: FortiAIGate,
LiteLLM, MCP demo tools, custom chatbot, demo home, optional HTTPS gateway, and
optional Open WebUI.

## AWS Default Topology

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

AWS defaults use Amazon Bedrock through LiteLLM as the model provider path.
FortiGate and FortiWeb are enabled by default for the full AWS demo and can be
disabled with ignored local Terraform overrides.

## Local Topology

```text
Operator workstation
  -> scripts/local_setup.py
     -> generated ignored local inventory and vars
     -> optional managed FortiGate/FortiWeb local appliance credentials
  -> Ansible
     -> bootstrap existing Ubuntu 24.04 GPU host
     -> deploy FortiAIGate
     -> deploy Ollama in k3s
     -> deploy LiteLLM/MCP/chatbot/demo home/HTTPS gateway
     -> configure optional local FortiGate/FortiWeb baselines when present

Local Ubuntu GPU host
  -> k3s
     -> FortiAIGate
     -> LiteLLM
     -> Ollama
     -> MCP demo tools
     -> custom chatbot
     -> demo home
```

Local mode skips AWS Terraform. It uses generated local inventory such as
`ansible/inventory/local.generated.ini` and generated local vars such as
`ansible/group_vars/local.generated.yml`. Those files are ignored because they
describe a specific lab and may be paired with ignored local secrets.

Local defaults keep application access direct to the k3s host's static LAN IP
and generated NodePorts. Local FortiGate and FortiWeb appliances are optional.
When present, `local_setup.py` can onboard managed `apiadmin` credentials and
the existing AWS-compatible appliance roles can run against local inventory.

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
- Amazon Bedrock is the AWS default provider target through LiteLLM.
- Ollama is the local default provider target through LiteLLM and is deployed
  in k3s for local hardware mode.

## Traffic Direction

The AWS no-DNS demo path uses public NodePorts for demo UIs and direct
FortiAIGate access. FortiWeb also publishes pass-through reverse-proxy paths
for the generated demo NodePorts. FortiGate configuration is in place for
address/service/VIP/policy objects, but active traffic policies are
intentionally empty until a specific FortiGate traffic path is selected.

The local no-DNS demo path uses the local k3s host's static LAN IP and the same
NodePort contract. Local Ollama is also exposed on a trusted-lab NodePort for
validation. Do not expose local NodePorts, especially the Ollama NodePort, to
untrusted networks.

Current LLM paths:

```text
Direct path:
Browser UI -> LiteLLM -> Bedrock on AWS
Browser UI -> LiteLLM -> Ollama on local hardware

FortiAIGate-inspected path:
Browser UI -> FortiAIGate explicit /v1/<flow-name> path -> LiteLLM -> Bedrock on AWS
Browser UI -> FortiAIGate explicit /v1/<flow-name> path -> LiteLLM -> Ollama on local hardware
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
sends the selected MCP tool-profile schemas to the model path, executes
model-requested tool calls, and sends results back for the final answer. The
MCP endpoint defaults to direct in-cluster MCP and can be switched to the
FortiWeb-fronted MCP URL.

Local FortiWeb MCP mode follows the same chatbot setting, but the proxy path is
lab-topology dependent. The first supported local model uses the FortiWeb
listener/proxy IP and forwards to the k3s host MCP NodePort. Source NAT may be
needed in flat local networks to avoid asymmetric return traffic.

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

Local FortiWeb uses operator-provided port1/operator-side and port2/backend
addresses when present. Local generated facts preserve existing AWS-shaped
variable names for compatibility, but the addresses describe local lab
interfaces rather than public cloud EIPs.

Current ports and deployment defaults are documented in
[Current Baseline](current-baseline.md).

See [AWS k3s Foundation](aws-k3s-foundation.md) for detailed AWS network
layout, subnet mode, and instance behavior.
