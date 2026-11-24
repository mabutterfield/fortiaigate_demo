# FortiAIGate Demo Documentation (8.0.2)

Use this page to find the document for a task. This release
(`v1.2.0-rc.1`) deploys FortiAIGate 8.0.2 on an AWS GPU host. Start with the
[8.0.2 quickstart](quickstart-802.md), the
[instructor guide](instructor-guide-802.md) and the
[release notes](release-notes-1.2.0-rc.1.md). `catalog802/data/index.json` is
the authority for active scenarios; see
[Scenario Management](scenario-management.md).

The 8.0.1 workflow (local Ubuntu lane, scenario installer, manual GUI work
orders, the 8.0.1 chatbot) and its documentation are preserved on branch
`archive/8.0.1` (tag `v1.0_faig8.0.1`). Earlier 8.0.2 tools removed from this
release are at tag `faig_8.0.2_gui_experiment`.

All commands run from the repository root unless a document says otherwise.

## Start Here

| Task | Document |
|---|---|
| Prepare the workstation, AWS account, files and licenses | [First-Run Preparation](first-run-preparation.md) |
| Deploy or tear down the AWS lab | [8.0.2 Quickstart](quickstart-802.md) |
| Run a class: scenarios, students, auto-approval | [Instructor Guide](instructor-guide-802.md) |
| Hand out to students | [Student Guide](student-guide-802.md) |
| Select, provision, test or change scenarios | [Scenario Management](scenario-management.md) |
| Understand state, generated secrets and static passwords | [Lab Secrets and State](lab-secrets-and-state.md) |
| Check a documented limitation | [Known Issues](known-issues.md) and the [release notes](release-notes-1.2.0-rc.1.md) |

## Reference

### Lab services

| Document | Covers |
|---|---|
| [Lab Management](lab-management.md) | Instructor page at `/manage/`: models, students, prepopulation, auto-approval |
| [Student Lab Chatbot](lab-chatbot.md) | Student chat, keys and graded tests |
| [Lab Login Gateway](lab-gateway.md) | Sign-in, sessions, HTTPS routing |
| [Functional Validation](functional-validation.md) | Command-line `catalog-baseline` checks |
| [MCP](mcp.md) | Deterministic demo tools and transports |
| [Bedrock](bedrock.md) | Bedrock model provider and IAM credentials |

### Infrastructure

| Document | Covers |
|---|---|
| [AWS Instance Sizing](aws-instance.md) | GPU instance selection |
| [AWS k3s Foundation](aws-k3s-foundation.md) | Host bootstrap and k3s |
| [Kubernetes](kubernetes.md) | k3s, Helm, namespaces and post-render patches |
| [Terraform Reference](terraform.md) | Modules, generated Ansible data, imports |
| [VPC Layout](vpc-layout.md) | AWS topology, trusted CIDRs, routing |
| [Container Repository Management](container-repository-management.md) | Images, ECR and publishing (maintainers) |
| [State Migration Recovery](state-migration-recovery.md) | Recovering an interrupted state move or backend upgrade |
| [AWS NVIDIA Package Cache](troubleshooting/aws-nvidia-package-cache-workaround.md) | Optional pinned NVIDIA package cache |

### Optional components

| Document | Covers |
|---|---|
| [FortiGate](fortigate.md) | Optional FortiGate appliance |
| [FortiWeb](fortiweb.md) | Optional FortiWeb appliance and MCP reverse proxy |
| [Ollama](ollama.md) | Local model provider (not used by the default AWS lab) |

### Project

| Document | Covers |
|---|---|
| [Changelog](../CHANGELOG.md) | Change history |
| [Catalog](../catalog802/README.md) | Catalog views, hashes and the result contract |

Internal plans, progress notes and experiments belong in the parent FAIG
workspace, not in this repository.
