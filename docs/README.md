# FortiAIGate Demo Documentation

Use this page to find the shortest path from a task to its owning document.
For FortiAIGate 8.0.2, use the [8.0.2 quickstart](quickstart-802.md), [instructor guide](instructor-guide-802.md), and [release notes](release-notes-1.2.0-rc.1.md). The [legacy baseline](reference/current-baseline.md) describes the earlier 8.0.1 workflow. For 8.0.2, `catalog802/data/index.json` is the authority for active scenarios;
see [Scenario Management](scenario-management.md).

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
| Configure scenario flows and guards (8.0.1, historical) | [Scenario GUI Configuration](fortiaigate-gui-config.md) |
| Select, provision, test or change 8.0.2 scenarios | [Scenario Management](scenario-management.md) |
| Test scenarios (student Tests tab, `catalog-baseline`) | [Scenario Management](scenario-management.md#testing-scenarios) and [Functional Validation](functional-validation.md) |
| Check a documented limitation or workaround | [Known Issues](known-issues.md) |
| Sign students in to the shared lab chatbot | [Lab Login Gateway](lab-gateway.md) |
| Run the 8.0.2 student lab chatbot | [Student Lab Chatbot](lab-chatbot.md) |
| Understand 8.0.2 state, generated secrets and static passwords | [Lab Secrets and State](lab-secrets-and-state.md) |

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
| [Scenario Management](scenario-management.md) | 8.0.2 catalog, Lab Management provisioning, testing and changing scenarios |
| [Advanced Scenario Management](advanced-scenario-management.md) | Historical (8.0.1): package tuning, matrix diagnostics, Detailed controls, optional chaining |
| [Scenario Catalog](../chatbot/scenarios/examples/scenario-catalog.md) | Historical (8.0.1) package classification; 8.0.2 active set is `catalog802/data/index.json` |
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
| [AWS NVIDIA Package Cache](troubleshooting/aws-nvidia-package-cache-workaround.md) | Optional verified, version-pinned NVIDIA package cache for AWS bootstrap |

### Author

| Document | Owns |
|---|---|
| [Scenario Authoring](scenario-authoring.md) | Historical (8.0.1) package schema; 8.0.2 authoring is in [Scenario Management](scenario-management.md#changing-a-scenario) |

### Maintain

| Document | Owns |
|---|---|
| [Release Validation Matrix](release-validation-matrix.md) | No-apply and live release checks |
| [Developer Load Testing](development/load-testing.md) | Bounded dashboard traffic, statistics, GPU collection, and safe shutdown |
| [Future Direction](../README.md#future-direction) | Directional ideas, not supported features or commitments |
| [Changelog](../CHANGELOG.md) | User-facing change history |

Internal plans, progress notes, and experiments belong in the parent FAIG
workspace rather than this deployment repository.
