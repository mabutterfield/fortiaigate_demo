# FortiAIGate Demo Documentation

Use this page to find the shortest path from a task to its owning document.
The [Current Baseline](reference/current-baseline.md) is the authority for what
is supported today. The [Scenario Catalog](../chatbot/scenarios/examples/scenario-catalog.md) is the
authority for validated, candidate, and archived scenario status.

All commands are run from the repository root unless a document explicitly
changes directories.

## Start Here

| Task | Document |
|---|---|
| Prepare files, credentials, licenses, and prerequisites | [First-Run Preparation](first-run-preparation.md) |
| Review defaults and optional components | [Deployment Options](deployment-options.md) |
| Prepare and deploy the default AWS lab | [Deployment Quickstart](quickstart.md#aws-lane) |
| Prepare and deploy a local Ubuntu GPU lab | [Deployment Quickstart](quickstart.md#local-ubuntu-lane) |
| Check, update, recover, or remove a deployment | [Operations](operations.md) |
| Diagnose a failed checkpoint | [Troubleshooting](troubleshooting.md) |
| Choose components and understand traffic paths | [Architecture](architecture.md) and [Current Baseline](reference/current-baseline.md) |
| Complete first login and create passthrough | [FortiAIGate Initial Configuration](fortiaigate-initial-config.md) |
| Configure scenario flows and guards | [Scenario GUI Configuration](fortiaigate-gui-config.md) |
| Install, update, remove, or validate scenarios | [Scenario Management](scenario-management.md) |
| Prove passthrough and all installed scenarios | [Functional Validation](functional-validation.md) |
| Check a documented limitation or workaround | [Known Issues](known-issues.md) |

The automated quickstart is the only normal installation journey. Detailed
Terraform and Ansible command sequences are reference and recovery material,
not a second installation lane.

## Documentation Ownership Map

Each current documentation page has one primary task group below. Retired
experiments are available from Git history rather than the release tree.

### Prepare

| Document | Owns |
|---|---|
| [First-Run Preparation](first-run-preparation.md) | Control workstation, AWS/local prerequisites, user files, licenses, generated-state warnings, and preflight |
| [Deployment Quickstart](quickstart.md) | The single guided AWS and local first-run journey |
| [AWS Instance Sizing](aws-instance.md) | GPU instance selection |
| [Command And Inventory Reference](reference/command-inventory.md) | Repo-root commands, inventory aliases, Terraform user links, generated files, and recovery hints |

### Choose Options

| Document | Owns |
|---|---|
| [Deployment Options](deployment-options.md) | Default and optional features, controls, prerequisites, validation, and impact |
| [Architecture](architecture.md) | Deployment topologies and request paths |
| [Current Baseline](reference/current-baseline.md) | Default, optional, configurable, and deferred runtime behavior |
| [Bedrock](bedrock.md) | Bedrock model-provider setup and IAM credentials |
| [Ollama](ollama.md) | Local model-provider behavior |
| [FortiGate](fortigate.md) | Optional FortiGate deployment and baseline configuration |
| [FortiWeb](fortiweb.md) | Optional FortiWeb deployment and MCP reverse proxy |
| [VPC Layout](vpc-layout.md) | AWS topology, trusted source CIDRs, routing, and network values |

### Deploy

| Document | Owns |
|---|---|
| [Operations](operations.md) | Status, repeat deployment, component reruns, updates, validation, recovery, and teardown |
| [Terraform Reference](terraform.md) | Terraform modules, generated Ansible data, and imports |
| [Container Repository Management](container-repository-management.md) | Docker inputs/builds, tags, ECR/local registries, publishing, verification, rollback, and future separation |
| [AWS k3s Foundation](aws-k3s-foundation.md) | AWS host bootstrap and k3s mechanics |
| [Kubernetes](kubernetes.md) | k3s, Helm, namespaces, and post-render behavior |

### Configure FortiAIGate

| Document | Owns |
|---|---|
| [FortiAIGate Initial Configuration](fortiaigate-initial-config.md) | First login, per-guard LiteLLM endpoint settings, `pass-model`, and global passthrough proof |
| [Scenario GUI Configuration](fortiaigate-gui-config.md) | Reusable work-order-driven Alert, Deny, Redact, flow, test, and telemetry workflow |
| [Transcript Replays](transcript-replays.md) | Preconstructed assistant/tool requests for raw FAIG/LLM diagnostics; not live functional tests |

### Manage Scenarios

| Document | Owns |
|---|---|
| [Scenario Management](scenario-management.md) | Install, update, remove, inspect, and validate local scenarios |
| [Advanced Scenario Management](advanced-scenario-management.md) | Candidate/archive inspection, local tuning, matrix diagnostics, Detailed controls, and optional chaining |
| [Scenario Catalog](../chatbot/scenarios/examples/scenario-catalog.md) | Scenario lifecycle and support classification |
| [MCP](mcp.md) | Deterministic tools, tool profiles, and MCP transports |
| [Functional Validation](functional-validation.md) | Operator-facing metadata-driven validation, evidence, filters, and direct-flow curl rendering |

### Operate

| Document | Owns |
|---|---|
| [FortiAIGate Syslog Preservation](troubleshooting/fortiaigate-syslog-preservation.md) | Detailed syslog collection, retention, and export procedure |

### Troubleshoot

| Document | Owns |
|---|---|
| [Troubleshooting](troubleshooting.md) | Common diagnosis and recovery procedures |
| [Known Issues](known-issues.md) | Current limitations and workarounds |
| [AWS NVIDIA Package Cache Workaround](troubleshooting/aws-nvidia-package-cache-workaround.md) | Temporary recovery for slow driver downloads; future AMI builds are intended to replace it |

### Author

| Document | Owns |
|---|---|
| [Scenario Authoring](scenario-authoring.md) | Scenario package schema and deployment boundaries |

### Maintain

| Document | Owns |
|---|---|
| [Release Validation Matrix](release-validation-matrix.md) | No-apply and live release checks |
| [Developer Load Testing](development/load-testing.md) | Bounded dashboard traffic, statistics, GPU collection, and safe shutdown |
| [Future Direction](../README.md#future-direction) | Directional ideas, not supported features or commitments |
| [Changelog](../CHANGELOG.md) | User-facing change history |

Internal plans, progress notes, and experiments belong in the parent FAIG
workspace rather than this deployment repository.
