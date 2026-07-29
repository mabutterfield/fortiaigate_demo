# Known Issues And Workarounds

This page centralizes release notes for issues that are known operational
constraints, not missing quickstart steps.

## Slow NVIDIA Driver Downloads On AWS

AWS EC2 Ubuntu images normally download `nvidia-driver-*-server` packages from
Ubuntu regional EC2 mirrors. Some rebuilds have seen NVIDIA driver package
downloads take 30-60 minutes. The default quickstart still rebuilds from the
standard Ubuntu AMI path so the demo remains reproducible without custom images.

Current workaround:

1. Run Terraform normally, but stop before Ansible:

   ```bash
   python3 scripts/automated_quickstart.py --skip-ansible
   ```

2. SSH to the k3s instance with the command printed by Terraform or quickstart.

3. Update apt metadata and install or pre-download the NVIDIA driver packages
   manually on the instance.

4. Optionally copy the downloaded `.deb` package set to S3 or another
   customer-owned cache for the next rebuild.

5. Rerun quickstart from the Ansible phase:

   ```bash
   python3 scripts/automated_quickstart.py --skip-terraform
   ```

The S3 package-cache approach is documented in
[AWS NVIDIA Package Cache Workaround](aws-nvidia-package-cache-workaround.md).
That workaround is optional and temporary. Phase 10 is evaluating custom AMI
support as a cleaner way to shorten AWS rebuilds, but a custom AMI must not be
required for the default v1.0 quickstart.

Do not commit downloaded packages, local cache manifests, Terraform state, or
rendered user-data from these experiments.

## FortiAIGate GUI Setup Is Manual

Quickstart deploys FortiAIGate, LiteLLM, chatbot, MCP, demo home, and appliance
baselines, then prints the values needed for FortiAIGate GUI setup. Provider,
flow, route, and guard configuration in the FortiAIGate GUI remains a manual
v1.0 boundary.

Use [FortiAIGate Initial Config](FortiAIGate-initial-config.MD) for the current
manual steps and [Scenario Catalog Matrix](scenario-catalog.md) for the
recorded-demo route and guard expectations.

## FortiWeb MCP Security Automation Is Deferred

FortiWeb reverse-proxy objects are automated for the demo HTTP paths. FortiWeb
MCP Security policy object automation is deferred because the current
collection/API coverage does not expose the required FortiWeb 8.0.3+ MCP
Security object cleanly.

The local and AWS demos can still use FortiWeb-fronted MCP routing when the
proxy path is configured, but MCP Security policy tuning remains a manual or
future integration item.

## Local Ollama NodePort Is Trusted-Lab Only

Local hardware mode exposes Ollama on a plain HTTP NodePort for validation and
operator convenience. Stock Ollama does not provide built-in API authentication.
Keep that NodePort restricted to a trusted lab network and do not expose it to
the internet.

