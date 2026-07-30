# Scenario Profiles

Scenario profiles package repeatable demo content without replacing instruction
profiles. They do not deploy separate MCP servers; every scenario uses the
same shared MCP service and declares its expected tools in `required_tools`.

Tracked scenario examples live under `examples/`. Installing a scenario copies
its recommended instruction text into an ignored local instruction slot such as
`chatbot/instructions/local/demo-a/instructions.txt` or
`chatbot/instructions/local/demo-b/instructions.txt`.

Detailed scenario walkthroughs live inside each scenario folder when a scenario
has moved beyond the generic prompt/profile summary.

| Scenario | Detailed walkthrough |
|---|---|
| `fortistore-product-advisor` | [examples/fortistore-product-advisor/README.md](examples/fortistore-product-advisor/README.md) |
| `hr-tool-dlp-vulnerable` | [examples/hr-tool-dlp-vulnerable/README.md](examples/hr-tool-dlp-vulnerable/README.md) |

Use the helper from the repo root:

```bash
python3 scripts/scenario_profiles.py list
python3 scripts/scenario_profiles.py show fortistore-product-advisor
python3 scripts/scenario_profiles.py install fortistore-product-advisor --slot demo-b --force
python3 scripts/scenario_profiles.py validate
```

Instruction profiles remain the place to fine-tune local wording after a
scenario has been installed.

Operator-facing prompts, recommended chatbot settings, and expected demo
behavior are documented in `docs/scenarios.md`. Editing workflow, tool-profile
selection, and deploy boundaries are documented in
`docs/scenario-authoring.md`. Raw curl replay payloads are documented in
`docs/curl-payloads.md`.
