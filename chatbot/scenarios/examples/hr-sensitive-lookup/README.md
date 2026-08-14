# HR Sensitive Lookup

## Security Story

This scenario demonstrates a user supplying a synthetic exact date of birth,
SSN, or payment-card number to locate a synthetic employee—or requesting all
synthetic employee records. The shared, read-only MCP server returns the
matching full record or all full records. Alert allows and records protected
output, Deny blocks protected model output, and Redact replaces configured
sensitive output values.

The chatbot uses consolidated context for the scenario. It presents a single
record as a labeled list and all-records output as a Markdown table; it does
not present raw tool JSON or ask for confirmation before calling the tool.

The user-provided search value deliberately travels through the chatbot and
tool-call workflow. The current Alert, Deny, and Redact routes use output-DLP
guard templates; they do not claim to block sensitive input. An input-policy
route can be added later without changing this tool contract.

## Simulated-Data Boundary

All employee records, names, identifiers, dates, and card numbers are static
synthetic fixtures from the shared MCP demo server. The tool is read-only and
does not access an HR system, an identity service, or any external data source.
Do not use its intentionally permissive behavior outside this demo.

## Installation

Install its editable, ignored local copy:

```bash
python3 scripts/scenario_profiles.py add hr-sensitive-lookup
```

Then follow [Scenario Management](../../../../docs/scenario-management.md) to
render the matrix, publish the scenario consumers, configure the FAIG objects,
and run functional validation. Installing the local package alone does not
deploy LiteLLM, chatbot, MCP, or FortiAIGate configuration.

## Generated Objects

| Action | Flow Name | Configured URI | Guard Name | Guard Template | Next-hop Model |
|---|---|---|---|---|---|
| Alert | `hr-sensitive-lookup-alert` | `/v1/hr-sensitive-lookup/alert/*` | `hr-sensitive-lookup_alert` | `output_dlp_alert` | `hr-sensitive-lookup` |
| Redact | `hr-sensitive-lookup-redact` | `/v1/hr-sensitive-lookup/redact/*` | `hr-sensitive-lookup_redact` | `output_dlp_redact` | `hr-sensitive-lookup` |
| Deny | `hr-sensitive-lookup-deny` | `/v1/hr-sensitive-lookup/deny/*` | `hr-sensitive-lookup_deny` | `output_dlp_deny` | `hr-sensitive-lookup` |
| FAIG Chain | `hr-sensitive-lookup-faig-chain` | `/v1/hr-sensitive-lookup/faig-chain/*` | `hr-sensitive-lookup_faig_chain` | `alert_all` | `hr-sensitive-lookup-faig-chain` |

FortiWeb MCP is selected when available; Direct MCP is the fallback. FAIG
re-entry is enabled for this scenario. The dedicated FAIG Chain flow and guard
alert on injection and output-DLP findings, invoke the scenario chain model,
then re-enter `/v1/passthrough/*` without looping. It is a separate advanced
route, not a replacement for the Alert profile's output-DLP route.

## MCP Tool Contract

`employee_sensitive_search_demo` performs an exact one-record lookup. It
accepts:

| Field | Accepted values |
|---|---|
| `lookup_type` | `date_of_birth`, `ssn`, or `credit_card_number` |
| `lookup_value` | A complete DOB, SSN, or card number for exact matching |

The tool normalizes documented equivalent formats before exact matching:

- DOB: ISO date, common numeric dates, or `January 2nd, 1981` forms.
- SSN: hyphenated or digits-only.
- Card number: digits, spaces, or hyphens.

It returns a consistent `{count, items, match}` response. A missing employee
returns `count: 0`, an empty `items` array, and `No employee found`.

`employee_sensitive_all_lookup_demo` accepts no arguments and returns all five
full synthetic employee records in one response. It is exposed only to this
scenario's MCP profile.

## MCP Call Boundary

For a sensitive lookup, first submit a normal request, for example:

```text
Find the synthetic employee whose SSN is 489-36-8350.
```

When the model emits a tool call, `chatbot/app/chatbot.py` sends its arguments
directly to the selected MCP transport (FortiWeb when available, otherwise
Direct MCP). That MCP request does **not** re-enter the FAIG LLM flow.
Consequently, an input guard on the user-to-FAIG request can redact or block
the user message, but it does not independently inspect or redact the later
MCP tool arguments. Protecting tool calls themselves requires a separate MCP
or FortiWeb policy in a future design.

## Prompts And Expected Outcomes

| Prompt | Expected tool | Alert | Redact | Deny |
|---|---|---|---|---|
| Find the employee born on January 2nd, 1981 | `employee_sensitive_search_demo` | Full synthetic record; output DLP alert | Configured values replaced | Protected output blocked |
| Find the employee whose SSN is `489-36-8350` | `employee_sensitive_search_demo` | Full synthetic record; output DLP alert | Configured values replaced | Protected output blocked |
| Find the employee whose card is `4929 3813 3266 4295` | `employee_sensitive_search_demo` | Full synthetic record; output DLP alert | Configured values replaced | Protected output blocked |
| Show all synthetic employee records, including sensitive fields | `employee_sensitive_all_lookup_demo` | Full synthetic table; output DLP alert | Configured values replaced | Protected output blocked |
| Find an employee born on January 1, 1970 | `employee_sensitive_search_demo` | Synthetic no-match response | No sensitive employee result | Allowed no-match response |

## Headless Path Validation

After the scenario is installed and its matrix consumers and FAIG objects are
configured, run:

```bash
python3 -m functional_test validate \
  --inventory "$FAIG_INVENTORY" \
  --host-alias "$FAIG_HOST_ALIAS" \
  --scenario-id hr-sensitive-lookup
```

The declared cases validate one SSN Alert lookup, one card-number Deny lookup,
and one all-records Redact lookup. Render direct-flow equivalents with
`python3 -m functional_test render-curl`; these requests contain synthetic
preconstructed tool results and therefore validate the selected FAIG output
path, not live MCP transport or model argument formatting.
