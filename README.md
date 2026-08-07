# FortiAIGate Demo

Version 1.0 of this repository provides infrastructure-as-code for a repeatable
FortiAIGate 8.x demonstration on an AWS GPU instance or an operator-owned
Ubuntu 24.04 GPU host. The deployed lab combines FortiAIGate, LiteLLM, a custom
chatbot, deterministic MCP tools, and installable security scenarios.

AWS with Amazon Bedrock is the primary deployment. Local hardware with Ollama
uses the same k3s application layer and scenario model.

## Start Here

All commands are run from the repository root unless a document says
otherwise.

| Goal | Start here |
|---|---|
| Prepare files, credentials, licenses, and prerequisites | [First-Run Preparation](docs/first-run-preparation.md) |
| Review defaults and optional components | [Deployment Options](docs/deployment-options.md) |
| Deploy the default AWS lab | [Automated Quick Start](docs/quickstart-automated.md) |
| Deploy to an existing local Ubuntu GPU host | [Local Hardware Mode](docs/quickstart-automated.md#local-hardware-mode) |
| Diagnose or recover a deployment | [Troubleshooting](docs/troubleshooting.md) and [Deployment Runbook](docs/deployment-runbook.md) |
| Understand the components and traffic paths | [Architecture](docs/architecture.md) |
| See exactly what is supported now | [Current Baseline](docs/reference/current-baseline.md) |
| Review validated and candidate scenarios | [Scenario Catalog](docs/scenario-catalog.md) |
| Find an operator, author, or maintainer task | [Documentation Map](docs/README.md) |

## What The Default Lab Provides

- A single-node k3s application layer with FortiAIGate, LiteLLM, the custom
  chatbot, deterministic MCP tools, Demo Home, syslog preservation when its
  AWS bucket is available, and a self-signed HTTPS gateway.
- FortiGate and FortiWeb appliances desired by default, with explicit opt-outs
  and safe skips when their licenses, inventory, or other prerequisites are
  unavailable.
- FortiWeb as the preferred chatbot-to-MCP transport when it is installed and
  desired; the chatbot falls back to direct MCP with a warning.
- Optional Open WebUI as a secondary UI. The custom chatbot remains the
  primary scenario UI.
- Scenario-owned FAIG paths using `/v1/<scenario>/<action>/*`, plus the
  canonical `/v1/passthrough/*` test path.
- A globally available FAIG re-entry capability that is disabled in each
  built-in scenario unless an operator explicitly enables it in local scenario
  metadata.

See [Deployment Options](docs/reference/current-baseline.md#feature-and-support-matrix)
for the distinction between defaults, optional components, validated behavior,
and deferred paths.

Scenario content is synthetic and intended for repeatable demonstrations, not
production policy guidance. Installed scenarios are local, editable runtime
state; tracked examples remain read-only templates. The
[Scenario Catalog](docs/scenario-catalog.md) is the authority for validated,
candidate, and archived scenario status.

## Deployment Model

Terraform owns AWS infrastructure. Ansible publishes images, configures the
GPU/k3s host and optional appliances, and deploys the application layer.
Local mode replaces Terraform with `scripts/local_setup.py`, which creates
ignored inventory and variable files for the operator's lab.

Tracked inventory shortcuts are available at the repository root:

```bash
ansible-playbook -i local ansible/playbooks/status_demo_home.yml
ansible-playbook -i cloud ansible/playbooks/status_demo_home.yml
```

Additional `local-*` and `cloud-*` aliases target the k3s host, FortiGate, and
FortiWeb inventories. The aliases point to ignored generated files, so lab
addresses and credentials are never stored in the links themselves.

## Repository Layout

```text
terraform/       AWS infrastructure modules
ansible/         Host, appliance, deployment, status, and validation automation
helm-values/     Example FortiAIGate Helm values
k8s-overlays/    Helm post-render patches and notes
chatbot/         Custom chatbot, scenarios, instructions, and demo application assets
functional_test/ Metadata-driven scenario validation for operators
load_test/       Developer-focused dashboard traffic generation
docs/            Quick starts, operations, reference, and authoring documentation
scripts/         Setup, scenario, build, and maintenance helpers
```

See [CHANGELOG.md](CHANGELOG.md) for user-facing changes and
the [Current Baseline](docs/reference/current-baseline.md) for supported
functionality.

## Future Direction

These are directional ideas, not implemented features, release commitments, or
supported setup steps:

- create reusable AMI images to replace the NVIDIA package-cache workaround
  and shorten AWS rebuilds;
- separate container-repository creation and image publishing from the normal
  deployment quickstart;
- integrate FortiFlex-based licensing choices;
- add locally owned blank and copied scenario creation workflows;
- publish selected repository documentation in Demo Home; and
- validate additional candidate scenarios and optional appliance paths.
