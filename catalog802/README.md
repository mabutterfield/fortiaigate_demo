# FAIG 8.0.2 catalog — initial HR DLP schema review

This directory is the **first review slice**, not the active runtime source of
truth and not an installer. It contains a concrete scenario schema, a
standard-library validator/loader, four secret-free generated views, and an HR
DLP example with model and MCP tool references. Existing scenario profiles,
LiteLLM and MCP runtime consumers remain unchanged until the owner and Agent2
review the exact schema. Their current data is temporarily duplicated in this
review slice; it must be consolidated when migration is approved.

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
The initial catalog covers HR DLP and only its four referenced tool contracts.
It references the existing tracked synthetic fixture and dispatcher; runtime
MCP still uses its old `TOOLS` registry. The future MCP compiler and the
migration/removal of the duplicate tool registry are not implemented here.

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
