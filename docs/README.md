# Documentation

This directory holds the canonical operational documentation for the FortiAIGate lab deployment.

| Document | Purpose |
|---|---|
| [deployment-runbook.md](deployment-runbook.md) | End-to-end deployment steps from local inputs through validation |
| [FortiAIGate-initial-config.MD](FortiAIGate-initial-config.MD) | First GUI login, AI flow, guard, deploy, and lab API-key setup |
| [ECR.md](ECR.md) | Private ECR repositories, image publishing, immutable tag handling, and deployment tag mapping |
| [Bedrock.md](Bedrock.md) | Temporary Bedrock IAM credentials for manual FortiAIGate provider setup |
| [terraform.md](terraform.md) | Terraform module usage, generated Ansible files, and import commands |
| [aws_instance.MD](aws_instance.MD) | AWS GPU instance sizing guidance |
| [aws-k3s-foundation.md](aws-k3s-foundation.md) | AWS k3s architecture, host bootstrap behavior, and FortiAIGate deployment mechanics |

The standalone k3s sanity check is:

```bash
cd ansible
ansible-playbook playbooks/validate_k3s.yml
```

FortiAIGate status and validation are intentionally separate:

- `status_fortiaigate.yml` gives a simple `READY`, `NOT READY`, or `ERROR` answer and prints the HTTPS login URL.
- `validate_faig.yml` runs deeper checks after status is ready, including GPU/Triton, `/dev/shm`, UI/API HTTP behavior, and optional provider forwarding.
- `test_model_direct.yml` runs a direct Bedrock or Ollama model test; Bedrock signing is handled by `scripts/bedrock_direct_test.py`.
- `test_fortiaigate_chat.yml` runs the first external chat completion test after a guard/provider is configured; request execution is handled by `scripts/fortiaigate_chat_test.py`.

The repo-owned scripts in `../scripts/` can also be run directly from the repo root for faster provider/API troubleshooting.

The root [README.md](../README.md) is intentionally short. Use it to get oriented and use these documents for details.

Internal build notes, experiments, and progress notes should live outside this Git repo in the parent FAIG workspace.
