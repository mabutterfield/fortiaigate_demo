# FortiAIGate Demo Documentation

Use this page to find the shortest path from a task to its owning document.
The [Current Baseline](reference/current-baseline.md) is the authority for what
is supported today. The [Scenario Catalog](scenario-catalog.md) is the
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
| Configure FortiAIGate flows and guards | [FortiAIGate GUI Configuration](FortiAIGate-initial-config.MD) |
| Install, update, remove, or validate scenarios | [Scenario Management](scenarios.md) |
| Check a documented limitation or workaround | [Known Issues](known-issues.md) |

The automated quickstart is the only normal installation journey. Detailed
Terraform and Ansible command sequences are reference and recovery material,
not a second installation lane.

## Documentation Ownership Map

Each current documentation page has one primary task group below. Historical
references remain available but are not part of the current runtime contract.

### Prepare

| Document | Owns |
|---|---|
| [First-Run Preparation](first-run-preparation.md) | Control workstation, AWS/local prerequisites, user files, licenses, generated-state warnings, and preflight |
| [Deployment Quickstart](quickstart.md) | The single guided AWS and local first-run journey |
| [AWS Instance Sizing](aws_instance.MD) | GPU instance selection |
| [Command And Inventory Reference](reference/command-inventory.md) | Repo-root commands, inventory aliases, Terraform user links, generated files, and recovery hints |

### Choose Options

| Document | Owns |
|---|---|
| [Deployment Options](deployment-options.md) | Default and optional features, controls, prerequisites, validation, and impact |
| [Architecture](architecture.md) | Deployment topologies and request paths |
| [Current Baseline](reference/current-baseline.md) | Default, optional, configurable, and deferred runtime behavior |
| [AWS](aws.md) | AWS service and infrastructure choices |
| [Bedrock](bedrock.md) | Bedrock model-provider setup and IAM credentials |
| [Ollama](ollama.md) | Local model-provider behavior |
| [FortiGate](fortigate.md) | Optional FortiGate deployment and baseline configuration |
| [FortiWeb](fortiweb.md) | Optional FortiWeb deployment and MCP reverse proxy |
| [VPC Layout](vpc-layout.md) | Detailed network layout choices |

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
| [FortiAIGate GUI Configuration](FortiAIGate-initial-config.MD) | Provider, passthrough, scenario flow, route, and guard setup |
| [FortiAIGate Lab Flows](fortiaigate-lab-flows.md) | Canonical request-path diagrams and generated names |
| [Legacy Transcript Replay Fixtures](curl-payloads.md) | Preconstructed assistant/tool transcripts pending reclassification; not live functional-test equivalents |

### Manage Scenarios

| Document | Owns |
|---|---|
| [Scenario Management](scenarios.md) | Install, update, remove, inspect, and validate local scenarios |
| [Scenario Catalog](scenario-catalog.md) | Scenario lifecycle and support classification |
| [MCP](mcp.md) | Deterministic tools, tool profiles, and MCP transports |
| [Functional Test](../functional_test/README.md) | Operator-facing metadata-driven validation of installed scenario paths |

### Operate

| Document | Owns |
|---|---|
| [FortiAIGate Syslog Preservation](fortiaigate-syslog-preservation.md) | Syslog collection, retention, and export |
| [FortiGate Traffic Demo](fortigate-proxy-demo.md) | Optional investigation of FortiGate-observed AI traffic; not a baseline scenario path |

### Troubleshoot

| Document | Owns |
|---|---|
| [Troubleshooting](troubleshooting.md) | Common diagnosis and recovery procedures |
| [Known Issues](known-issues.md) | Current limitations and workarounds |
| [AWS NVIDIA Package Cache Workaround](aws-nvidia-package-cache-workaround.md) | Temporary recovery for slow driver downloads; future AMI builds are intended to replace it |

### Author

| Document | Owns |
|---|---|
| [Scenario Authoring](scenario-authoring.md) | Scenario package schema and deployment boundaries |
| [Scenario Documentation Process](scenario-documentation-process.md) | Scenario evidence, walkthrough, and documentation expectations |

### Maintain

| Document | Owns |
|---|---|
| [Release Validation Matrix](release-validation-matrix.md) | No-apply and live release checks |
| [Traffic Generator](traffic-generator.md) | Developer-only dashboard load generation; not required for demo setup |
| [Future Direction](../README.md#future-direction) | Directional ideas, not supported features or commitments |
| [Historical Scenario/Model Matrix](phase8-reference-matrix.md) | Historical test evidence only; not the current naming model |
| [Changelog](../CHANGELOG.md) | User-facing change history |

Internal plans, progress notes, and experiments belong in the parent FAIG
workspace rather than this deployment repository.

The former Automated Quick Start, Deployment Runbook, and Manual Deployment
Reference paths remain as concise compatibility pointers to the current
quickstart, operations, and troubleshooting owners.
