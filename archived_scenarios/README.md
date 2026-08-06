# Archived Scenarios

Status: archived reference material.

These scenario profiles are preserved for reference, but they are no longer in
the active or candidate scenario working set. The active/candidate scenario
tree is `chatbot/scenarios/examples/`.

The scenario catalog still keeps inactive entries for archived scenarios in
`chatbot/scenarios/examples/catalog.json`, with paths that point back to this
directory. This keeps `scripts/scenario_profiles.py list --include-inactive`
and `show --include-inactive` useful for reference.

To revive an archived scenario:

1. Copy or move the scenario folder back under `chatbot/scenarios/examples/`.
2. Update the scenario path in `chatbot/scenarios/examples/catalog.json`.
3. Set `"active": true` only when it should appear in normal scenario picker,
   validation, harness, and traffic-generator flows.
4. Run:

   ```bash
   python3 scripts/scenario_profiles.py validate
   ```

The five earlier resume candidates were consolidated into the active
`resume-tool-injection` scenario. Their archived packages preserve the clean,
prompt-injection, explicit pivot, least-privilege, and vulnerable comparison
iterations for reference.
