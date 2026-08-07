# Functional Scenario Validation

This is the supported operator-facing validation entry point. From the
repository root, run:

```bash
python3 -m functional_test
```

The default validates FAIG passthrough plus every validation case declared by
every installed scenario. It checks expected completion, denial, redaction,
sensitive results, and required or forbidden MCP tool calls. Restrict a run
with repeatable `--scenario-id` options, or inspect all options with:

```bash
python3 -m functional_test --help
```

Results are written under the ignored `functional_test/output/` directory.
All paths use the same response-classification contract so expected-result
counts remain consistent.
