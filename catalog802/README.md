# FAIG 8.0.2 catalog — scenario migration draft

This directory is a **migration draft**, not yet the active runtime source of
truth and not an installer. It contains a scenario schema, a standard-library
validator/loader, four secret-free generated views, and draft definitions for
HR DLP, FortiStore, and Resume. Existing profiles and runtime consumers still
use their previous sources; duplication remains until consumer migration.

From the repository root:

```bash
python3 -m catalog802 student
python3 -m catalog802 faig
python3 -m catalog802 models
python3 -m catalog802 mcp
python3 -m unittest discover -s catalog802/tests -v
```

`schema/scenario.schema.json` documents the scenario's outer structure;
`loader.py` is the executable stdlib validator and additionally checks model,
tool, guard, prompt and file references. Schema and loader must be brought to
full parity during review before claiming general JSON Schema validation.
The catalog covers three scenarios and their referenced tool contracts. It
references tracked synthetic fixtures and the dispatcher; runtime MCP still
uses its old `TOOLS` registry. The future MCP compiler and the
migration/removal of the duplicate tool registry are not implemented here.

The `student` and `faig` views expose a `platform` object with the shared
hello-world case, resolved pass-model metadata, naming patterns, action, execution, verdict, evidence, and outcome
vocabularies and lab price units. The observed platform passthrough
key has no directly attached policy (`policyIds: []`); inherited policies and
scanning status still need to be checked independently. The object has its
own deterministic hash. `vocabulary.py` owns the current catalog constants;
the existing `functional_test/result_contract.py` has not yet migrated to
them. The proposed ConfigMap keys are `catalog-student.json` and
`catalog-faig.json`; ConfigMap generation and delivery are not implemented.

All paths resolve within the supplied checkout root; credentials, users and
FAIG UUIDs are absent. The model view includes backend instruction text and is
for trusted deployment consumers; the student view omits that text. SHA-256
hashes cover canonical JSON of resolved scenario, model/instruction, tool
contracts, referenced dispatcher/fixture hashes, guards/detectors, naming,
hello-world and pricing metadata. View timestamps and source commit are not
hashed. A matching source hash never proves a live deployment matches.

Prices are decimal strings in USD per million tokens; conversion and FAIG API
read-back are future provisioning adapter work. `known_failure_matches` is a
pure predicate over normalized supplied results; no existing test runner has
been changed and a matching predicate never changes or hides raw evidence.

Review questions: expected view/field names; schema and validator strictness;
model/public/backend identity; naming; detector and template representation;
MCP handler/fixture references and hashing; known-issue scope and predicates;
source-to-ConfigMap packaging; and how later scenario editor drafts validate
without Git write access. No live FAIG operation or vendor API support claim.

The review contract separates execution status, the most severe observed Traffic
Log verdict, client-observed evidence, and outcome. Missing or unreadable rows,
or fewer rows than requests sent, make the verdict unknown; a required unknown
verdict makes the outcome incomplete. A tool returning sensitive data to the
chatbot does not establish that the model received it. A block-message marker
should use an exact configured-message match where available; reply keywords
are not a substitute for a Traffic Log verdict. The future runner must implement
these outcome rules; this slice only validates expectations and issue predicates.

Prompt groups contain objects with a scenario-unique `id` and `text`; tests
reference the ID, so reordering prompts does not change the test. Object names
use underscores between logical sections and hyphens inside a section.
Guardrails can compose multiple reusable, scenario-independent detector
categories. The HR example preserves its existing DOB, SSN, and payment-card
categories while splitting them into independent detector definitions. Broader
address and financial groupings require verification against FAIG's supported
categories. Regex and natural-language kind-specific validation and
provisioning have not yet been implemented or verified.

FortiStore references its compromised frontend instruction file; the student
view includes its contents and the scenario hash covers them. Resume document
fixtures are separately referenced and hashed. Resume Block records the known
early-block issue without suppressing failed-test evidence. Neither scenario
change has been tested against a live FAIG deployment in this migration.

`result_contract.evaluate` implements the approved outcome rules over supplied
observations, preserving the Traffic Log rows and failure reasons. It does not
collect logs, identify evidence, or replace the existing live test runner; the
caller must provide complete rows, evidence, and tools called.

`python3 -m catalog802 mcp-runtime` compiles the currently cataloged tool
contracts to the server's function format. This output contains only tools in
the catalog, not every legacy or candidate tool; it is not installed or used
by either MCP endpoint yet. Do not replace the existing server registry until
non-catalog tools and both endpoints have a verified migration path.

`python3 -m catalog802 litellm` builds the LiteLLM role's matrix subset from
all cataloged models, deduplicated by backend alias. It validates shared alias
targets/instructions and keeps pass-model free of injected instructions. The
role defaults to this catalog output; set `litellm_use_catalog: false` to use
the previous locally installed scenario matrix. This change is not yet live
validated and does not implement the 8.0.2 FAIG re-entry provider.

The MCP Ansible role stages the compiled registry by default and mounts it in
both MCP containers. At startup, catalog definitions replace matching entries
in the legacy server registry; the remaining legacy tools are preserved. This
is an interim adapter: the legacy entries and catalog duplicates still need
consolidation. Missing, duplicate, or unrecognized catalog tool names fail
startup. Set `mcp_use_catalog: false` for the previous registry-only behavior.
The Helm chart used independently defaults the adapter off unless its generated
registry is explicitly staged. This workflow requires live validation.

`python3 -m functional_test evaluate-catalog --scenario ID --test ID
--faig-version 8.0.2 --observations observations.json` evaluates already
collected observations against a catalog test. The observations JSON must
contain `execution`, `verdict_rows`, `requests_sent`, `evidence`, and
`tools_called`. The command does not perform requests or verify evidence
provenance; it reports incomplete when the required Traffic Log rows are
missing. Existing live baseline and chatbot tests still use their legacy
contract until a request-correlated Traffic Log collector is implemented.

`python3 -m functional_test catalog-baseline --help` describes the live
catalog runner. It requires an owner-only scenario key file and administrator
credentials to check Traffic Log details. It adds a unique marker to the
prompt, runs the shared in-cluster agent, and only accepts log rows with the
same key and marker in `prompt.original`. Missing rows produce INCOMPLETE;
results contain no key or prompt/response contents. The marker has been
verified in a blocked FortiStore request, a two-request HR redaction turn,
and a five-request Resume tool turn. This runner executes one test at a time;
key metadata must match the current catalog action, and old `deny` metadata is
not silently treated as `block`.

The HR Redact case currently expects no sensitive data in the reply, whereas
its DLP definition covers date of birth, SSN, and payment card only. A live
run returned a redaction marker but left email and phone visible, so this case
correctly failed under its present expectation. Reconcile the expected outcome
and detector categories before treating that test as a release gate.
