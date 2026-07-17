# Instruction Profiles

Tracked files under `examples/` are the prompt library. Active deployable
instruction slots live under `local/`, are ignored by Git, and can be exported
with the user profile.

The default deployable slots are:

- `demo-a`: backend LiteLLM profile used by the `demo-a` model aliases
- `demo-b`: backend LiteLLM profile used by the `demo-b` model aliases
- `frontend`: optional browser-facing chatbot instruction layer

Example metadata is stored in `examples/catalog.json`. Ansible owns the default
slot-to-example mapping in `ansible/group_vars/system.yml`.

Use the helper from the repo root:

```bash
python3 scripts/instruction_profiles.py
python3 scripts/instruction_profiles.py init
python3 scripts/instruction_profiles.py list
python3 scripts/instruction_profiles.py examples
python3 scripts/instruction_profiles.py activate demo-b --from fastfood-bot --force
python3 scripts/instruction_profiles.py edit demo-a
python3 scripts/instruction_profiles.py validate
```

Running the helper with no subcommand starts a short wizard. It shows current
slot metadata, lets you choose one slot, then installs either a fresh tracked
example or an unused local instruction file after confirmation.

Ansible also initializes missing active files from examples before rendering
LiteLLM instruction profiles. Automated quickstart initializes missing local
slots during user profile setup.
