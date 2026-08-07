# FortiAIGate Demo Documentation

Use this page to find the shortest path from a task to its owning document.
The [Current Baseline](reference/current-baseline.md) is the authority for what
is supported today; [Upcoming Features](upcoming-features.md) describes
directional work only.

All commands are run from the repository root unless a document explicitly
changes directories.

## Start Here

| Task | Document |
|---|---|
| Prepare and deploy the default AWS lab | [Automated Quick Start](quickstart-automated.md) |
| Prepare and deploy a local Ubuntu GPU lab | [Local Hardware Mode](quickstart-automated.md#local-hardware-mode) |
| Inspect or recover one deployment step | [Manual Quick Start](quickstart-manual.md) |
| Choose components and understand traffic paths | [Architecture](architecture.md) and [Current Baseline](reference/current-baseline.md) |
| Configure FortiAIGate flows and guards | [FortiAIGate GUI Configuration](FortiAIGate-initial-config.MD) |
| Install, update, remove, or validate scenarios | [Scenario Management](scenarios.md) |
| Diagnose a problem | [Troubleshooting](troubleshooting.md) and [Known Issues](known-issues.md) |

The automated quickstart is the normal first-run path. The manual quickstart
is the recovery and inspection path, not a second required installation
workflow.

## Documentation Ownership Map

Each current documentation page has one primary task group below. Historical
references remain available but are not part of the current runtime contract.

### Prepare

| Document | Owns |
|---|---|
| [Automated Quick Start](quickstart-automated.md) | Prerequisites, guided AWS deployment, and local-hardware entry point |
| [AWS Instance Sizing](aws_instance.MD) | GPU instance selection |
| [AWS NVIDIA Package Cache Workaround](aws-nvidia-package-cache-workaround.md) | Optional package-cache preparation for slow downloads |

### Choose Options

| Document | Owns |
|---|---|
| [Architecture](architecture.md) | Deployment topologies and request paths |
| [Current Baseline](reference/current-baseline.md) | Default, optional, configurable, validated, candidate, and deferred behavior |
| [AWS](aws.md) | AWS service and infrastructure choices |
| [Bedrock](bedrock.md) | Bedrock model-provider setup and IAM credentials |
| [Ollama](ollama.md) | Local model-provider behavior |
| [FortiGate](fortigate.md) | Optional FortiGate deployment and baseline configuration |
| [FortiWeb](fortiweb.md) | Optional FortiWeb deployment and MCP reverse proxy |
| [VPC Layout](vpc-layout.md) | Detailed network layout choices |

### Deploy

| Document | Owns |
|---|---|
| [Manual Quick Start](quickstart-manual.md) | Step-by-step deployment and recovery commands |
| [Deployment Runbook](deployment-runbook.md) | End-to-end operational deployment sequence |
| [Terraform Reference](terraform.md) | Terraform modules, generated Ansible data, and imports |
| [ECR And Image Publishing](ecr.md) | Current container-repository and image-publishing workflow |
| [AWS k3s Foundation](aws-k3s-foundation.md) | AWS host bootstrap and k3s mechanics |
| [Kubernetes](kubernetes.md) | k3s, Helm, namespaces, and post-render behavior |

### Configure FortiAIGate

| Document | Owns |
|---|---|
| [FortiAIGate GUI Configuration](FortiAIGate-initial-config.MD) | Provider, passthrough, scenario flow, route, and guard setup |
| [FortiAIGate Lab Flows](fortiaigate-lab-flows.md) | Canonical request-path diagrams and generated names |
| [Curl Payloads](curl-payloads.md) | Replayable request equivalents for validated scenario tests |

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
| [Upcoming Features](upcoming-features.md) | Directional roadmap, not supported features or commitments |
| [Current Baseline Compatibility Pointer](current-baseline.md) | Preserves old inbound links to the authoritative reference page |
| [Historical Scenario/Model Matrix](phase8-reference-matrix.md) | Historical test evidence only; not the current naming model |
| [Changelog](../CHANGELOG.md) | User-facing change history |

Internal plans, progress notes, and experiments belong in the parent FAIG
workspace rather than this deployment repository.
