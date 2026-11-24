# Functional Validation (8.0.2)

Two ways to check that a scenario behaves as the catalog expects on a live
lab. Both send a catalog test prompt through FortiAIGate with the student's
key, run the scenario's MCP tools, and grade the result against the matching
FortiAIGate Traffic Log entry: PASS, FAIL, KNOWN FAIL (a documented
limitation) or INCOMPLETE (the verdict could not be confirmed).

- **Student chatbot Tests tab** (normal path): students run their own tests;
  instructors use *Act as student*. See the
  [Student Guide](student-guide-802.md#tests) and
  [Lab Chatbot](lab-chatbot.md).
- **`catalog-baseline`** (maintainers): one case from the command line,
  described below.

These are functional path checks, not exhaustive security assertions. Unit
tests (`python3 -m unittest discover -s tests`) check code and catalog data
without contacting a lab.

## Run one case from the command line

```bash
python3 -m functional_test catalog-baseline \
  --scenario hr-tool-dlp --action redact \
  --key-file /path/outside/git/student01_hr-tool-dlp_redact.json \
  --admin-credentials /path/outside/git/admin-login.json \
  --inventory ansible/inventory/aws.generated.ini \
  --faig-url https://<lab-ip> --insecure
```

- `--key-file`: an owner-only (`0600`) JSON file for that student key:
  `scenario`, `action`, `model` (the catalog model alias), `keyName` and
  `secretKey`. The scenario, action and model must match the catalog case.
  Key values come from Lab Management (Secret `lab-data/lab-keys`); never
  paste them into a shared terminal.
- `--admin-credentials`: an owner-only JSON file with the FAIG administrator
  `username` and `password`, used only to read the Traffic Log.
- `--test`: a specific catalog test ID; the default is the action's attack
  test. List them with `python3 -m catalog802 student`.
- `--block-message-file`: required when the case checks for FAIG's exact block
  message.
- `--insecure`: accept the lab's self-signed certificate on the external FAIG
  address. The in-cluster FAIG address is reached over HTTPS without
  certificate verification by default, because the lab certificate doesn't
  match the service name; supply a matching certificate and
  `--internal-verify-tls` to require it.

The runner stages the shared agent loop in the MCP pod over SSH, adds a
unique marker to the prompt, and looks for the Traffic Log rows that carry it
for up to `--log-wait` seconds (default 20). It never prints keys, passwords,
prompts or responses. If the marker itself trips a detector or the row isn't
found in time, the result is INCOMPLETE, not PASS.

`python3 -m functional_test evaluate-catalog --help` grades a saved
observations file against a catalog test without contacting a lab.

## Known limitations

- **Resume Block** reports KNOWN FAIL: FortiAIGate blocks before the
  `document_read` tool runs.
- One case per run. A catalog-driven batch runner over all Lab Management keys
  is planned.

The 8.0.1 `functional_test validate`, `scenario-pack`, `baseline` and
`render-curl` commands are retired; they are preserved on branch
`archive/8.0.1` and tag `faig_8.0.2_gui_experiment`.
