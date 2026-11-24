# FortiAIGate Demo

> **FortiAIGate 8.0.2 release candidate:** The project release is `v1.2.0-rc.1`, targeting `v1.2.0`. Start with the [8.0.2 quickstart](docs/quickstart-802.md), [instructor guide](docs/instructor-guide-802.md), and [release notes](docs/release-notes-1.2.0-rc.1.md). The 8.0.1 workflow is preserved on branch `archive/8.0.1`.

This repository deploys a repeatable FortiAIGate 8.0.2 training lab on an AWS
GPU instance: k3s, FortiAIGate, LiteLLM with Amazon Bedrock, deterministic MCP
demo tools, and a lab gateway with an instructor page (Lab Management) and a
student chatbot. One command builds the lab and one command tears it down.

## Start Here

All commands are run from the repository root unless a document says
otherwise.

| Goal | Start here |
|---|---|
| Prepare the workstation, AWS account, files and licenses | [First-Run Preparation](docs/first-run-preparation.md) |
| Deploy or tear down the 8.0.2 AWS lab | [8.0.2 Quickstart](docs/quickstart-802.md) |
| Run a class | [Instructor Guide](docs/instructor-guide-802.md) |
| Select, provision, test or change scenarios | [Scenario Management](docs/scenario-management.md) |
| Check a documented limitation | [Known Issues](docs/known-issues.md) and [release notes](docs/release-notes-1.2.0-rc.1.md) |
| Find any other document | [Documentation Map](docs/README.md) |

## What The Lab Provides

- A single-node k3s host on an AWS GPU instance running FortiAIGate 8.0.2,
  LiteLLM (Amazon Bedrock models) and the MCP demo tools.
- HTTPS everywhere a browser connects: FAIG's GUI and API, and the lab
  gateway on port 30444, which serves the student chatbot and, for FAIG
  administrators, Lab Management at `/manage/`. Plain HTTP ports redirect.
- Lab Management: select scenarios, add their models to FAIG, create student
  accounts and workspaces, prepopulate per-student detectors, guardrails,
  policies and keys, and auto-approve student changes.
- A student chatbot that chats through the student's own FAIG keys and runs
  graded tests against the FortiAIGate Traffic Log.
- Three catalog scenarios: FortiStore Injection, HR Tool DLP and Resume Tool
  Injection, defined in `catalog802/`. See
  [Scenario Management](docs/scenario-management.md).
- Generated per-instance credentials kept outside the repository, removed by
  teardown. See [Lab Secrets and State](docs/lab-secrets-and-state.md).

FortiGate and FortiWeb appliances are optional and not required for the lab.
Scenario content is synthetic and intended for training, not production
policy guidance.

## Deployment Model

Terraform owns the AWS infrastructure (`terraform/aws-prep`,
`terraform/aws-ec2-k3s`; ECR in `terraform/aws-ecr` is maintained
separately). Ansible configures the GPU/k3s host and deploys the
applications. `scripts/automated_quickstart.py` runs both and initializes
FAIG; `scripts/teardown_802.py` removes the lab while keeping ECR, S3 and
shared IAM. See the [8.0.2 quickstart](docs/quickstart-802.md).

## Repository Layout

```text
terraform/       AWS infrastructure modules
ansible/         Host and application deployment, status and validation
k8s-overlays/    Helm post-render patches and notes
catalog802/      Scenario catalog: models, tools, actions, prompts and tests
chatbot/         Lab gateway, Lab Management, student chatbot, shared agent loop
mcp/             MCP demo tool server
functional_test/ Command-line catalog checks (catalog-baseline)
docs/            Guides and reference
scripts/         Quickstart, teardown, state and setup helpers
tests/           Unit tests
```

See [CHANGELOG.md](CHANGELOG.md) for changes. The 8.0.1 workflow is preserved
on branch `archive/8.0.1` (tag `v1.0_faig8.0.1`).

## Future Direction

These are directional ideas, not implemented features, release commitments, or
supported setup steps:

- evaluate reusable AMI images alongside the optional NVIDIA package cache
  to shorten AWS rebuilds;
- separate container-repository creation and image publishing from the normal
  deployment quickstart;
- integrate FortiFlex-based licensing choices;
- add a scenario editor for the 8.0.2 catalog;
- publish selected repository documentation in Demo Home; and
- validate additional candidate scenarios and optional appliance paths.
