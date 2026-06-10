# Documentation

This directory holds the canonical operational documentation for the FortiAIGate lab deployment.

| Document | Purpose |
|---|---|
| [deployment-runbook.md](deployment-runbook.md) | End-to-end deployment steps from local inputs through validation |
| [ECR.md](ECR.md) | Private ECR repositories, image publishing, immutable tag handling, and deployment tag mapping |
| [terraform.md](terraform.md) | Terraform module usage, generated Ansible files, and import commands |
| [aws-k3s-foundation.md](aws-k3s-foundation.md) | AWS k3s architecture, host bootstrap behavior, and FortiAIGate deployment mechanics |

The standalone k3s sanity check is:

```bash
cd ansible
ansible-playbook playbooks/validate_k3s.yml
```

The root [README.md](../README.md) is intentionally short. Use it to get oriented and use these documents for details.

Internal build notes, experiments, and progress notes should live outside this Git repo in the parent FAIG workspace.
