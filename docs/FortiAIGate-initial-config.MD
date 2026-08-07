# FortiAIGate Initial Configuration

Use this guide after Deployment Quickstart reports FortiAIGate `READY`. It
creates the smallest usable configuration: one LiteLLM provider, the
`pass-model` target, one no-protection AI Guard, and the global
`/v1/passthrough/*` flow.

Do not install scenario-specific FAIG objects yet. After passthrough works,
continue with [Scenario GUI Configuration](fortiaigate-gui-config.md).

All commands run from `<repo_root>`.

## Before Opening The GUI

Select the deployed environment and confirm FortiAIGate and LiteLLM are ready:

```bash
export FAIG_INVENTORY=cloud
# or
export FAIG_INVENTORY=local

ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/status_fortiaigate.yml
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/status_litellm.yml
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/test_litellm_direct.yml
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/show_demo_outputs.yml
```

Use the FortiAIGate Admin URL printed by Demo Outputs. The configuration below
uses these values:

| Variable | Value |
|---|---|
| `{{litellm_url}}` | `http://litellm.litellm.svc.cluster.local:4000/v1` unless locally overridden |
| `{{litellm_api_key}}` | `litellm_master_key` from ignored `ansible/group_vars/user.yml` |
| Passthrough model | `pass-model` |
| Guard name | `pass_model` |
| Flow name | `passthrough` |
| Configured flow URI | `/v1/passthrough/*` |

Never put `{{litellm_api_key}}`, a FortiAIGate API key, passwords, private
addresses, or other environment secrets in screenshots or committed files.

## 1. Complete First Login And Confirm Licensing

Open the Admin URL, complete the FortiAIGate 8.x first-login workflow, and
confirm that the deployed license is active. Change any initial password when
the product prompts for it and store the result outside Git.

> **Screenshot placeholder — `faig-initial-login-license`**
>
> Expected filename: `images/fortiaigate/faig-initial-login-license.png`
>
> Caption: Complete initial FortiAIGate onboarding and confirm that the license is active.
>
> Capture: The licensed/ready landing page after onboarding. Show the 8.x product version and active license state; omit usernames, license identifiers, serial numbers, and addresses.

## 2. Configure LiteLLM As The Provider

In the provider or model-provider area, create an OpenAI-compatible provider
named `litellm`:

| Field | Value |
|---|---|
| Name | `litellm` |
| Provider type | OpenAI-compatible |
| Base URL | `{{litellm_url}}` |
| API key | `{{litellm_api_key}}` |

This key authenticates FortiAIGate to LiteLLM. It is not the optional key that
authenticates a chatbot or curl client to a FortiAIGate flow.

> **Screenshot placeholder — `faig-initial-provider`**
>
> Expected filename: `images/fortiaigate/faig-initial-provider.png`
>
> Caption: Configure the LiteLLM provider at `{{litellm_url}}`.
>
> Capture: The OpenAI-compatible provider editor with provider name and URL populated. Keep the API-key field masked and exclude browser-saved credential prompts.

Add or expose `pass-model` through that provider. The model name must match the
LiteLLM alias exactly.

> **Screenshot placeholder — `faig-initial-model`**
>
> Expected filename: `images/fortiaigate/faig-initial-model.png`
>
> Caption: Configure `pass-model` as the passthrough next-hop model.
>
> Capture: The provider model/target editor showing `pass-model` selected under the `litellm` provider. Do not show the provider API key.

## 3. Create The No-Protection Passthrough Guard

Create an AI Guard named `pass_model` and select the LiteLLM `pass-model`
target. Leave prompt-injection protection, DLP, deny, and redaction actions
disabled. This guard exists to provide a full FAIG traversal control without
scenario protection or LiteLLM scenario instructions.

> **Screenshot placeholder — `faig-initial-passthrough-guard`**
>
> Expected filename: `images/fortiaigate/faig-initial-passthrough-guard.png`
>
> Caption: Create the minimal no-protection guard used by FAIG passthrough.
>
> Capture: The complete `pass_model` guard summary showing the `litellm` provider, `pass-model`, and no enabled protection actions.

Use the built-in AI Guard test with a simple prompt such as `Reply with only:
ok passthrough validation`. Confirm that the request completes and no detector
or enforcement action is applied.

## 4. Create The Passthrough Flow

Create one explicit flow:

| Field | Value |
|---|---|
| Flow name | `passthrough` |
| URI | `/v1/passthrough/*` |
| AI Guard | `pass_model` |
| Client API-key validation | Disabled for the normal isolated lab |

The wildcard is required. A request to this flow uses
`/v1/passthrough/chat/completions`. Do not create a generic `/v1/*` fallback;
it can conceal a missing scenario flow or make URI ordering ambiguous.

> **Screenshot placeholder — `faig-initial-passthrough-flow`**
>
> Expected filename: `images/fortiaigate/faig-initial-passthrough-flow.png`
>
> Caption: Publish `/v1/passthrough/*` through the passthrough guard and `pass-model`.
>
> Capture: The flow editor showing `passthrough`, the complete wildcard URI, and attached `pass_model` guard.

Most lab flows disable client-to-FAIG API-key validation. This keeps scenario
testing focused on AI protections. It does not disable the separate LiteLLM
provider credential.

> **Screenshot placeholder — `faig-initial-flow-auth`**
>
> Expected filename: `images/fortiaigate/faig-initial-flow-auth.png`
>
> Caption: Disable client API-key validation for the isolated lab baseline; identify the control used to enable an explicit API-key test.
>
> Capture: The passthrough flow authentication setting in its disabled state. Show the setting label and flow name without exposing credentials.

## 5. Deploy The Configuration

Review and deploy/apply the provider, model, guard, and flow. Wait until the
deployment reports success before testing the URL.

> **Screenshot placeholder — `faig-initial-deploy`**
>
> Expected filename: `images/fortiaigate/faig-initial-deploy.png`
>
> Caption: Deploy the initial provider, guard, and passthrough flow.
>
> Capture: The deployment review or successful deployment status showing `litellm`, `pass_model`, and `passthrough`; omit unrelated objects and secrets.

## 6. Validate Passthrough

Run the controller-side FortiAIGate test against the exact flow:

```bash
ansible-playbook -i "$FAIG_INVENTORY" \
  ansible/playbooks/test_fortiaigate_chat.yml \
  -e fortiaigate_test_endpoint_path=/v1/passthrough/chat/completions \
  -e fortiaigate_test_model=pass-model
```

Expected result:

- HTTP success;
- response from `pass-model`;
- flow `passthrough` and guard `pass_model` in FortiAIGate telemetry;
- no scenario instruction marker; and
- no prompt-injection, DLP, deny, or redaction action.

If it fails, use
[FortiAIGate Returns 401, 404, Or The Wrong Guard](troubleshooting.md#fortiaigate-returns-401-404-or-the-wrong-guard).

> **Screenshot placeholder — `faig-initial-passthrough-event`**
>
> Expected filename: `images/fortiaigate/faig-initial-passthrough-event.png`
>
> Caption: Confirm the passthrough request reached `pass-model` without scenario protection.
>
> Capture: The FortiAIGate event or request detail showing the passthrough path, `pass_model`, allowed outcome, `pass-model`, and timestamp. Exclude prompt content if it contains anything beyond the synthetic test string.

## Optional: Test Client API-Key Validation

Client API-key validation is not required for the normal lab. To test it
explicitly, create a lab-only key, enable validation on a chosen flow, and
store the key only in ignored local configuration. The optional curl header is:

```bash
-H "Authorization: Bearer $FAIG_API_KEY"
```

Set `fortiaigate_test_api_key` in ignored `ansible/group_vars/user.yml` when
the Ansible test must send that key. Remove or disable the test configuration
when returning to the normal lab baseline.

> **Screenshot placeholder — `faig-optional-api-key`**
>
> Expected filename: `images/fortiaigate/faig-optional-api-key.png`
>
> Caption: Optionally create a lab API key for an explicit authenticated-flow test.
>
> Capture: The API-key creation confirmation or key-list entry with the actual key value, identifier, and any secret-bearing QR/code fully omitted or redacted.

## Next Step

Install scenarios, render their work order, and continue with
[Scenario GUI Configuration](fortiaigate-gui-config.md). The global
passthrough flow is reused by Advanced chatbot testing and by any explicitly
enabled, loop-safe FAIG re-entry chain.
