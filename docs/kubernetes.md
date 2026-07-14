# Kubernetes

The demo uses single-node k3s on Ubuntu 24.04. Ansible installs and configures:

- NVIDIA driver and utilities
- container runtime support for NVIDIA GPUs
- k3s
- NVIDIA device plugin
- RuntimeClass
- nginx ingress
- local-path storage

The bootstrap playbook runs the same foundation validation as
`validate_k3s.yml` before it finishes. The standalone validation playbook is
useful after rebuilds, network changes, or manual troubleshooting.

Useful status entry points:

- `ansible/playbooks/validate_k3s.yml`
- `ansible/playbooks/status_fortiaigate.yml`
- `ansible/playbooks/validate_faig.yml`
- `ansible/playbooks/status_litellm.yml`
- `ansible/playbooks/status_chatbots.yml`
- `ansible/playbooks/status_mcp.yml`
- `ansible/playbooks/test_mcp.yml`
- `ansible/playbooks/status_demo_home.yml`

Open WebUI is optional and disabled by default; use
`ansible/playbooks/status_openwebui.yml` only when `openwebui_enabled=true`.

See [AWS k3s Foundation](aws-k3s-foundation.md) and
[Deployment Runbook](deployment-runbook.md) for the full workflow.
