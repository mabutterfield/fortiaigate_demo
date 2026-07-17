# Scenario Profiles

Scenario profiles package repeatable demo content without replacing instruction
profiles.

Tracked scenario examples live under `examples/`. Installing a scenario copies
its recommended instruction text into an ignored local instruction slot such as
`chatbot/instructions/local/demo-a/instructions.txt` or
`chatbot/instructions/local/demo-b/instructions.txt`.

Use the helper from the repo root:

```bash
python3 scripts/scenario_profiles.py list
python3 scripts/scenario_profiles.py show fastfood-ordering
python3 scripts/scenario_profiles.py install fastfood-ordering --slot demo-b --force
python3 scripts/scenario_profiles.py validate
```

Instruction profiles remain the place to fine-tune local wording after a
scenario has been installed.

Operator-facing prompts, recommended chatbot settings, and expected demo
behavior are documented in `docs/scenarios.md`.
