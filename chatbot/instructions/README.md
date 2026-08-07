# Instruction Library

Current scenario backend and frontend instructions belong inside installable
scenario packages under `chatbot/scenarios/examples/<scenario-id>/`. Installed
copies under `chatbot/scenarios/local/` are Git-ignored and operator-editable.
Use [Scenario Authoring](../../docs/scenario-authoring.md) for the current
contract.

The tracked files under this directory's `examples/` tree are a general prompt
library and compatibility source for older local instruction slots. They are
not the runtime identity or naming model for current scenarios.

The helper remains available for existing installations that explicitly use
those local slots:

```bash
python3 scripts/instruction_profiles.py --help
python3 scripts/instruction_profiles.py examples
python3 scripts/instruction_profiles.py validate
```

Local activated files remain under the Git-ignored
`chatbot/instructions/local/` tree and can be included in an exported user
profile. Do not add new scenario behavior by assigning lettered slots; create
or edit a named scenario package instead.
