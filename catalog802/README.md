# FAIG 8.0.2 scenario catalog

The catalog defines the three active scenarios (FortiStore Injection, HR Tool
DLP and Resume Tool Injection), their model aliases and instruction files,
reusable MCP tool contracts, FAIG detector/guardrail templates, sample prompts,
and test expectations. `data/index.json` selects active definitions. Other
candidate scenarios remain in the legacy scenario index and are not active in
this catalog.

```bash
python3 -m catalog802 student       # secret-free student-facing view
python3 -m catalog802 faig          # provisioning view
python3 -m catalog802 models        # model instructions for trusted consumers
python3 -m catalog802 mcp           # resolved MCP contracts
python3 -m catalog802 litellm       # LiteLLM Ansible matrix
python3 -m catalog802 mcp-runtime   # MCP function definitions
python3 -m unittest discover -s catalog802/tests
```

The `student` and `faig` views include the platform hello-world, passthrough
model, naming, labeled action/result vocabularies, and lab price units. Prices
are artificial USD per million tokens. View headers carry a schema version,
source revision and generation time; scenario and platform hashes exclude the
timestamp and cover relevant definitions, model instructions and tool
fixtures. A source hash does not prove the live configuration matches it.
The student view excludes backend model instructions but includes the expressly
labeled FortiStore compromised-frontend fixture; it is used only when a test or
student explicitly selects it, never by default.

Prompt groups contain objects with scenario-unique `id` and `text` fields;
tests refer to IDs rather than positions. Names use underscores between
sections and hyphens within sections. HR Redact covers DOB, SSN, payment card,
email and phone through reusable detectors. Broader groupings and support for
regex/natural-language detector kinds require validation. The scenario JSON
Schema documents structure; the standard-library loader additionally validates
cross-references and rules. It is not a full JSON Schema validator.

## Deployment and transitional adapters

The LiteLLM role reads catalog aliases and instructions by default. Set
`litellm_use_catalog: false` to restore its previous installed-scenario matrix.
The 8.0.2 FAIG re-entry provider remains separate and unfinished; catalog mode
rejects the legacy FAIG-chain option.

The MCP role compiles the catalog definitions and mounts them in both server
containers. Catalog contracts replace matching legacy entries; the remaining
legacy tools are preserved. The duplicate legacy registry is a transitional
adapter and parity tests detect drift for cataloged tool definitions. Set
`mcp_use_catalog: false` for the old registry. The chart used without the role
defaults the adapter off. Installing a new handler remains a development and
redeployment task; a scenario cannot install executable code at runtime.

The existing `functional_test scenario-pack`, `functional_test/result_contract.py`
and `chatbot/agent/faig_agent.py` remain in place for the existing chatbot until
its catalog reader lands. Transitional legacy scenario profiles and FAIG
configuration templates remain editable files; `test_legacy_adapter_parity.py`
checks the active profiles, prompts, tools, actions and guard behavior against
the catalog to detect drift. These files and parity checks should be retired
when their consumers are replaced; they are not a second long-term source of
truth. Existing student keys with old `deny` names require reseeding; the new
catalog and current templates use `block` and underscore-separated sections.

## Testing

`catalog802/result_contract.evaluate` evaluates supplied observations against a
catalog test. Its imports include `catalog802.loader` and
`catalog802.vocabulary`; package those dependencies together. It does not
collect logs or independently verify evidence provenance. Execution, traffic
verdict, client-observed evidence and outcome remain separate. Missing
required Traffic Log rows produce an incomplete result. A tool result observed
by the chatbot does not prove the model received it.

`python3 -m functional_test evaluate-catalog` evaluates an observations JSON
file; `python3 -m functional_test catalog-baseline --help` describes the live
one-case runner. The live runner needs an owner-only virtual-key file and FAIG
admin credentials. It uses a unique prompt marker and checks each matching
Traffic Log detail; it does not print secrets or prompt/response content. An
exact block-message file is required if a case checks block-message evidence.
A missing or unreadable required row produces INCOMPLETE. The existing legacy
baseline and chatbot are not yet switched to this runner.

Live lab checks have exercised FortiStore Alert/Block, HR Alert/Block, Resume
Alert, the opt-in compromised frontend, and Resume Block's scoped early-block
known failure. A previous HR Redact run against the *older* policy correctly
failed because it allowed email/phone. The catalog now includes those
categories; validate the newly provisioned policy independently. The marker
may itself affect a detector and is not guaranteed to survive every policy;
when it does not, the runner must report incomplete.
