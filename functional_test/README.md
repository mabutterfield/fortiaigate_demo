# Functional Test Package

`functional_test` is the supported operator-facing validator for installed
scenarios. Its implementation, output root, response classification, metadata
planner, and curl renderer live in this package. The dashboard load generator
may reuse these functions, but it does not own the validation contract.

From `<repo_root>`:

```bash
python3 -m functional_test validate
python3 -m functional_test render-curl --help
```

Running `python3 -m functional_test` without a command remains a transition
alias for `validate`.

`validate` executes the chatbot-owned agent loop, including frontend
instructions and live MCP rounds. It asserts each case's expected result,
required tools, and forbidden tools. Output is written below the ignored
`functional_test/output/` tree.

`render-curl` validates a scenario-owned request template against the
installed profile, inserts the selected frontend instructions, writes a
rendered JSON body under `functional_test/output/rendered-curl/`, and prints a
direct FortiAIGate curl command. It does not execute a live MCP agent loop.

See [Functional Validation](../docs/functional-validation.md) for the operator
workflow and [Scenario Authoring](../docs/scenario-authoring.md) for the
metadata/template contract.
