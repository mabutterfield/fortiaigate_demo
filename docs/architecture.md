# Architecture

The current demo architecture is a single-node k3s lab deployed on an AWS GPU
instance. Terraform creates the AWS foundation and Ansible configures the host,
Kubernetes, FortiAIGate, and demo applications.

## Current Flow

```text
Operator workstation
  -> Terraform
     -> ECR repositories
     -> AWS prep IAM/EIPs/Bedrock credentials
     -> VPC/subnets/security group/EC2 k3s host
  -> Ansible
     -> publish images
     -> bootstrap GPU k3s
     -> deploy FortiAIGate
     -> deploy LiteLLM/OpenWebUI/chatbot/demo home
```

## Runtime Components

- k3s runs on a single Ubuntu 24.04 GPU host.
- nginx ingress replaces the default k3s Traefik path.
- FortiAIGate is deployed from the vendor Helm chart plus post-render patches.
- LiteLLM provides the shared OpenAI-compatible direct model proxy.
- OpenWebUI and the custom chatbot provide demo user interfaces.
- Amazon Bedrock and Ollama are provider targets; Bedrock is the current AWS-first path.

## Traffic Direction

The default no-DNS demo path uses public NodePorts for demo UIs and direct
FortiAIGate access. Future phases add FortiGate/FortiWeb appliance-fronted
routing and private k3s subnet mode.

See [AWS k3s Foundation](aws-k3s-foundation.md) for detailed AWS network
layout, subnet mode, and instance behavior.
