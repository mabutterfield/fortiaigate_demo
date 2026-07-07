# Helm

FortiAIGate is deployed from the vendor Helm chart outside this repo. The
Ansible role copies the extracted chart to the k3s host, stages local licenses,
renders values, and applies post-render patches before submitting the release.

The demo application layer also uses Helm charts:

- LiteLLM proxy and Admin UI
- OpenWebUI
- custom chatbot
- demo home page

FortiAIGate Helm behavior intentionally does not wait for every pod to become
Ready by default. Use status and validation playbooks after Helm accepts the
install or upgrade.

More detail:

- [Deployment Runbook](deployment-runbook.md)
- [k8s-overlays FortiAIGate README](../k8s-overlays/fortiaigate/README.md)
