# Known Issues And Workarounds

This page records current operational constraints. Use
[Troubleshooting](troubleshooting.md) for symptom-driven diagnosis and
[Operations](operations.md) for normal reruns and recovery.

## NVIDIA Driver Downloads Can Be Slow On AWS

The standard Ubuntu AMI obtains NVIDIA driver packages from Ubuntu package
mirrors. Some rebuilds have taken 30–60 minutes while downloading those
packages. This is slow progress rather than a failed deployment when package
activity continues.

The optional [AWS NVIDIA Package Cache Workaround](aws-nvidia-package-cache-workaround.md)
documents the current recovery path. Reusable AMI creation is intended to
replace this workaround in a future release, but custom AMIs are not required
by the current quickstart.

Do not commit downloaded packages, cache manifests, Terraform state, or
rendered user data.

## FortiAIGate GUI Object Creation Is Manual

Automation deploys the services and generates scenario-specific work orders,
but the corresponding provider, flow, route, and guard objects must still be
created in the FortiAIGate 8.x GUI.

Create the minimal passthrough configuration first, then use the installed
scenario work order for protected paths. See
[FortiAIGate Initial Configuration](FortiAIGate-initial-config.MD),
[Scenario GUI Configuration](fortiaigate-gui-config.md), and
[Scenario Management](scenarios.md). Functional validation cannot repair a
missing or stale GUI flow.

## FortiWeb MCP Security Policy Automation Is Deferred

FortiWeb reverse-proxy objects for demo HTTP paths are automated. FortiWeb MCP
Security policy object automation remains deferred because the required object
is not cleanly exposed by the currently used collection/API path.

FortiWeb-fronted MCP transport remains supported when its proxy path is
configured. MCP Security policy tuning is a separate manual or future
integration task.

## Open WebUI Is Deployed Without Demo Configuration

Open WebUI can be deployed as an optional secondary interface, but the
repository does not configure its model provider, FortiAIGate paths, MCP tools,
or scenario profiles. The custom chatbot is the configured scenario UI.

## Local Ollama NodePort Is Trusted-Lab Only

Local mode exposes Ollama through plain HTTP for validation and operator
convenience. Stock Ollama does not provide built-in API authentication. Keep
the NodePort restricted to a trusted lab network and do not expose it to the
internet.

## Local Lab Uninstall Is Not Automated

The repository supports local reconciliation and updates through repeated
quickstart or component playbooks. It does not currently provide an automated
uninstall for the local k3s host. Exporting generated local state moves local
inventory and variable files; it does not remove k3s, images, applications, or
appliances.
