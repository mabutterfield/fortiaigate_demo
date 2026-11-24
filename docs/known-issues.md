# Known Issues And Workarounds

This page records current operational constraints of the 8.0.2 lab. The
[release notes](release-notes-1.2.0-rc.1.md) list what was tested for this
release; the [instructor guide](instructor-guide-802.md#troubleshooting) covers
common classroom problems.

## NVIDIA Driver Downloads Can Be Slow On AWS

The standard Ubuntu AMI obtains NVIDIA driver packages from Ubuntu package
mirrors. Some rebuilds have taken 30–60 minutes while downloading those
packages. This is slow progress rather than a failed deployment when package
activity continues.

The optional [AWS NVIDIA Package Cache Workaround](troubleshooting/aws-nvidia-package-cache-workaround.md)
documents the current recovery path. Reusable AMI creation is intended to
replace this workaround in a future release, but custom AMIs are not required
by the current quickstart.

Do not commit downloaded packages, cache manifests, Terraform state, or
rendered user data.

## FortiWeb MCP Security Policy Automation Is Deferred

FortiWeb reverse-proxy objects for demo HTTP paths are automated. FortiWeb MCP
Security policy object automation remains deferred because the required object
is not cleanly exposed by the currently used collection/API path.

FortiWeb-fronted MCP transport remains supported when its proxy path is
configured. MCP Security policy tuning is a separate manual or future
integration task.

## Open WebUI Is Deployed Without Demo Configuration

Open WebUI is off by default. When enabled it is deployed as a secondary
interface, but the repository does not configure its model provider,
FortiAIGate paths or MCP tools, and its FAIG path still defaults to the 8.0.1
value. The lab chatbot is the configured scenario UI.

## HR DLP Payment Cards Are Withheld From MCP Responses

In 8.0.1 testing, a multi-record HR employee table built from five tool calls
redacted dates of birth but missed several credit card numbers, while a
single-employee request redacted DOB and card values correctly (see the
CHANGELOG entry for `employee_table_with_cc`). Since then the MCP server strips
`credit_card_number`, `credit_card_expiration`, `credit_card_cvv` and
`salary_usd` from every employee tool response
(`EMPLOYEE_TOOL_HIDDEN_FIELDS` in `mcp/chart/files/server.py`); the values
remain only in the synthetic fixture `mcp/chart/files/tools.json`.

On FortiAIGate 8.0.2 (2026-11-18, Ohio lab) the experimental per-student HR
DLP detectors were extended with the `Credit/debit card` category and the
whole five-row synthetic table, including card numbers, was replayed as one
tool result through each student's HR keys. Whenever the model reproduced the
table, all five DOB, SSN and card values were redacted by the Redact key,
blocked by the Block key, and passed through with an Alert verdict by the Alert
key. This was a single tool result checked on model output, not the earlier
five-tool-loop chatbot flow, so card fields stay hidden from MCP responses
until that flow is retested. The model sometimes refuses to print the table;
the validator reports that as inconclusive rather than as a DLP result. The
procedure is in `experiments/faig-api-lab/README.md` at tag
`faig_8.0.2_gui_experiment`.

## Resume Block Is A Known Failure

In 8.0.2, Resume Block is blocked when the result of
`document_upload_simulation` reaches FortiAIGate, before the model calls
`document_read`. The upload result's metadata for the attack fixture
describes the attack in plain text (summary "Synthetic poisoned resume fixture
containing hidden instructions…", tags `prompt-injection` and `cloud-pivot`),
and the OWASP detectors block on that description rather than on the poisoned
resume content. The security outcome is correct (`cloud_bucket_list_demo`
never runs), but the scenario's block test requires `document_read`, so the
Tests tab reports KNOWN FAIL. Resolving it means either withholding the
self-describing metadata from tool results or changing the test contract in
the catalog.

## FAIG Re-entry Is Not Available

The 8.0.1 LiteLLM → FAIG re-entry chain is off (`faig_chain_capability_enabled:
false`): the 8.0.1 `/v1/passthrough` re-entry path does not exist in 8.0.2, and
the re-entry provider, key and loop prevention need a new design (planned for
v1.2.1).
