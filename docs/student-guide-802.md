# Student guide — FortiAIGate 8.0.2 lab

Your instructor gives you an address, an email (`studentNN@…`) and a password.

## Sign in

Open `https://<host>:30444/` and sign in with your FortiAIGate email and
password. Accept the certificate warning the first time (the lab uses its own
certificate). You stay signed in until 25 minutes without activity or 8 hours,
whichever comes first; then sign in again.

The same account opens the FortiAIGate GUI at `https://<host>/ui`, where you
manage your workspace (`studentNN_workspace`): detectors, guardrails, policies
and keys. Changes you submit there are approved by the instructor, usually
automatically within about a minute.

## Pick a scenario and action

In the sidebar choose a **Scenario** (for example HR tool DLP) and an
**Action** (alert, redact or block). The sidebar shows the scenario's notes,
its MCP tools and which of your keys is used.

## Keys

Each action needs a FortiAIGate key whose policy matches it. If your
instructor prepopulated your workspace, your keys are already mapped.
Otherwise, in the **Keys** tab:

1. Create a key in the FortiAIGate GUI (copy its value: FortiAIGate shows it
   only once), then click **Refresh from FortiAIGate**.
2. **Map a new key**: choose the key, the scenario and the action, paste the
   value and **Save mapping**. FortiAIGate checks the value first; a wrong value
   is refused. Warnings tell you if the key's policies or models don't match
   the lab's one key → one policy → one model rule.
3. **Hello-world** sends a harmless prompt through the key; a pass means the
   key works and FortiAIGate logged it.
4. **Rotate a key** creates a new value and stores it for you; the old value
   stops working within about a minute.

Use **Change a mapping or paste a new value** to fix an existing mapping.

## Chat

The **Chat** tab sends your messages through FortiAIGate with the selected
key. The debug options can send the same message directly to the model
(bypassing FortiAIGate) to compare, and simulate a compromised frontend for
the injection scenarios.

## Tests

The **Tests** tab:

- **Run one test** sends the catalog test prompt for the selected action and
  checks the result against the Traffic Log: **PASS**, **FAIL**, **KNOWN FAIL**
  (a documented limitation) or **INCOMPLETE** (the verdict could not be
  confirmed, for example the Traffic Log entry was not found). Each request
  shows the payload sent, the payload returned and the matching Traffic Log
  entry.
- **Try a prompt** sends a catalog prompt or your own text and shows
  FortiAIGate's verdict without grading it.
- **Run all tests** runs every test for the selected scenario (or all
  scenarios) that has a mapped key.

## When something goes wrong

| Message | Meaning |
|---|---|
| "FortiAIGate rejected the key (HTTP 401 …)" | The stored value is wrong or the key was rotated or deleted: paste the current value or rotate the key. |
| "FortiAIGate refused the request (HTTP 400 …)" | The key's model or policy does not match this scenario and action; check the Keys tab warnings. |
| "Rate or budget limit reached (HTTP 429)" | Wait a moment and retry. |
| "Traffic Log not available … sign in again" | Your session ended (idle or a lab restart); sign in again. |
| "Map a key to this scenario and action" | Create or map a key in the Keys tab first. |
| Rotation "outcome unknown" | Run hello-world in a minute; rotate again only if it fails. |
