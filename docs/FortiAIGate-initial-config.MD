# FortiAIGate Initial Configuration

Use this guide after Deployment Quickstart reports FortiAIGate `READY`. It
uses the FortiAIGate 8.x onboarding wizard to create the smallest usable
configuration: the global `/v1/passthrough/*` flow and a no-protection AI
Guard whose `pass-model` next hop is LiteLLM.

Do not run functional scenario validation yet. First complete this guide,
install the desired scenarios, and create their FortiAIGate objects with
[Scenario GUI Configuration](fortiaigate-gui-config.md). The command
`python3 -m functional_test validate` is the final check after that GUI
configuration is deployed.

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

Use the FortiAIGate Admin URL and LiteLLM values printed by Demo Outputs. The
LiteLLM URL and provider credential are shared by every FortiAIGate guard;
flow names, flow paths, guard names, and model aliases vary by scenario.

| Value | Initial passthrough setting |
|---|---|
| LiteLLM endpoint | `{{litellm_url}}`, normally `http://litellm.litellm.svc.cluster.local:4000/v1` |
| LiteLLM API key | `{{litellm_api_key}}`, the ignored `litellm_master_key` value |
| Flow name | `passthrough` |
| Flow path | `/v1/passthrough/*` |
| Guard name | `pass_model` |
| Model | `pass-model` |

Never put `{{litellm_api_key}}`, a FortiAIGate API key, passwords, private
addresses, or other environment secrets in screenshots or committed files.

## 1. Log In And Set The Password

Open the Admin URL and complete the FortiAIGate 8.x first-login workflow.
Change the initial password when prompted, store it outside Git, and confirm
that the deployed license is active before starting the onboarding wizard.

> **Screenshot placeholder — `faig-initial-login-password`**
>
> Expected filename: `images/fortiaigate/faig-initial-login-password.png`
>
> Caption: Complete first login, set the administrator password, and confirm the FortiAIGate license is active.
>
> Capture: The licensed/ready first-login state. Show the 8.x product version and active license state; omit usernames, password fields, license identifiers, serial numbers, and addresses.

## 2. Complete The Onboarding Wizard

The onboarding wizard creates the initial flow and its AI Guard together.
LiteLLM is configured on this guard; there is no separate global provider
setup in this workflow.

### 2.1 Define Your First AI Flow

Enter the passthrough flow identity:

| Field | Value |
|---|---|
| Flow name | `passthrough` |
| Path | `/v1/passthrough/*` |

The wildcard is required. Requests use
`/v1/passthrough/chat/completions`. Do not create a generic `/v1/*` fallback;
it can conceal a missing scenario flow or make path ordering ambiguous.

> **Screenshot placeholder — `faig-onboarding-flow`**
>
> Expected filename: `images/fortiaigate/faig-onboarding-flow.png`
>
> Caption: Define the initial `passthrough` flow at `/v1/passthrough/*`.
>
> Capture: The first onboarding step with the complete flow name and wildcard path visible. Exclude browser-saved credentials and unrelated objects.

### 2.2 Set Up Your First AI Guard

Configure the passthrough guard with LiteLLM as its private OpenAI-compatible
endpoint:

| Field | Value |
|---|---|
| AI Guard name | `pass_model` |
| Provider | `OpenAI` |
| Model | `pass-model` |
| Private endpoint | Enabled |
| Endpoint | `{{litellm_url}}` |
| API key | `{{litellm_api_key}}` |
| Token pricing | Enabled |
| Input token cost | A non-secret demonstration value |
| Output token cost | A non-secret demonstration value |

Select `OpenAI` as the provider even though LiteLLM is the next hop: LiteLLM
exposes the OpenAI-compatible API used by this guard. Turn on **Private
endpoint** and enter `{{litellm_url}}` in the field labeled **Endpoint**. The
model name must match the LiteLLM alias `pass-model` exactly.

Token costs are used only for FortiAIGate GUI cost calculations in this lab.
They do not represent actual local-model or cloud billing, so synthetic input
and output prices are acceptable. Use the same demonstration pricing policy
for later scenario guards so dashboard comparisons remain understandable.

The API key authenticates FortiAIGate to LiteLLM. It is separate from optional
client authentication on a FortiAIGate flow.

> **Screenshot placeholder — `faig-onboarding-guard`**
>
> Expected filename: `images/fortiaigate/faig-onboarding-guard.png`
>
> Caption: Configure `pass_model` with the OpenAI provider, `pass-model`, the private LiteLLM endpoint, and demonstration token costs.
>
> Capture: The second onboarding step showing OpenAI, `pass-model`, Private endpoint enabled, the Endpoint value, and populated input/output token costs. Keep the API-key field masked.

### 2.3 Configure Your AI Guard Protection

Leave every protection switch off. This guard provides a full FortiAIGate
traversal control without prompt-injection, DLP, deny, or redaction behavior.
It also avoids scenario-specific LiteLLM instructions because `pass-model` is
the next-hop alias.

> **Screenshot placeholder — `faig-onboarding-protection`**
>
> Expected filename: `images/fortiaigate/faig-onboarding-protection.png`
>
> Caption: Leave all protection features disabled for the passthrough guard.
>
> Capture: The third onboarding step with every protection switch visibly off and the `pass_model` guard identified.

### 2.4 Review And Finish

Review the flow, guard, endpoint, model, and disabled protections, then click
**Deploy**. Wait for deployment to report success before editing or testing
the new objects.

> **Screenshot placeholder — `faig-onboarding-review-deploy`**
>
> Expected filename: `images/fortiaigate/faig-onboarding-review-deploy.png`
>
> Caption: Review and deploy the initial passthrough flow and `pass_model` guard.
>
> Capture: The fourth onboarding step or deployment-success state showing `passthrough`, `/v1/passthrough/*`, `pass_model`, and `pass-model`. Omit the API key and private addresses.

## 3. Correct And Test The Wizard Configuration

### 3.1 Remove Flow Authentication

Edit the wizard-created `passthrough` flow and remove or disable its client
authentication requirement. Most lab flows disable client-to-FortiAIGate API
key validation so testing focuses on AI protections. This does not disable the
separate LiteLLM API key configured on the guard.

> **Screenshot placeholder — `faig-initial-flow-auth-disabled`**
>
> Expected filename: `images/fortiaigate/faig-initial-flow-auth-disabled.png`
>
> Caption: Edit the wizard-created passthrough flow and disable client authentication for the isolated lab baseline.
>
> Capture: The `passthrough` flow authentication setting in its disabled state. Show the setting label and flow name without exposing credentials.

Deploy the flow change before testing the request path.

### 3.2 Test The Model From The Guard

Edit `pass_model` and click **Test Model**. A successful test proves that the
OpenAI provider selection, private Endpoint, API key, and `pass-model` alias
work before the flow and client path are added to the diagnosis.

Use a simple prompt such as `Reply with only: ok passthrough validation`.
If the test fails, compare the provider, Private endpoint switch, Endpoint,
API key, and model alias with the onboarding table. Correct the guard and test
again until it succeeds.

> **Screenshot placeholder — `faig-initial-model-test-failed`**
>
> Expected filename: `images/fortiaigate/faig-initial-model-test-failed.png`
>
> Caption: A failed Test Model result identifies a guard-to-LiteLLM configuration problem before flow validation.
>
> Capture: A representative failed Test Model result with its useful error visible. Do not expose the endpoint address, API key, prompt history, or unrelated guard details.

> **Screenshot placeholder — `faig-initial-model-test-success`**
>
> Expected filename: `images/fortiaigate/faig-initial-model-test-success.png`
>
> Caption: Confirm `pass_model` reaches the LiteLLM `pass-model` alias successfully.
>
> Capture: The successful Test Model result for the synthetic validation prompt, with guard and model names visible and secrets omitted.

## 4. Validate Passthrough

After flow authentication is disabled and **Test Model** succeeds, run the
controller-side test against the exact flow:

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

## Optional: Configure Syslog

The repository's Fluent Bit collector is an optional stop-gap when
FortiAnalyzer is unavailable. First print the deployed destination:

```bash
ansible-playbook -i "$FAIG_INVENTORY" \
  ansible/playbooks/show_demo_outputs.yml
ansible-playbook -i "$FAIG_INVENTORY" \
  ansible/playbooks/status_fortiaigate_syslog_collector.yml
```

Use the **FAIG Syslog target/IP** value. Current FortiAIGate builds require the
printed ClusterIP rather than the service DNS name.

For AWS, durable syslog storage is enabled only by the Terraform variable in
ignored `terraform/aws-prep/99-local.auto.tfvars`:

```hcl
fortiaigate_syslog_bucket_enabled = true
```

This is an AWS Prep module setting, not a shared `terraform/user.tfvars`
setting. Do not add it to `50-user.auto.tfvars`, which is a link to the shared
file loaded by every module. If the bucket was disabled during the first run,
set the AWS Prep override and rerun quickstart; Terraform and Ansible will
bring the existing deployment to the newly requested state. See
[FortiAIGate Syslog Preservation](troubleshooting/fortiaigate-syslog-preservation.md)
for AWS and local collector details.

> **Screenshot placeholder — `faig-optional-syslog-output`**
>
> Expected filename: `images/fortiaigate/faig-optional-syslog-output.png`
>
> Caption: Read the deployed FortiAIGate syslog destination from Demo Outputs or collector status.
>
> Capture: The output lines containing the syslog target IP, UDP port, and S3 or file destination. Omit host addresses, bucket account identifiers, credentials, and unrelated output.

In FortiAIGate, navigate to **Logs > Log Settings** and create or enable a
syslog destination using the printed values:

| Field | Value |
|---|---|
| Server | Printed syslog target IP |
| Port | `514` |
| Protocol | `UDP` |
| Status | Enabled |

Save the settings, generate a synthetic passthrough event, and use the status
playbook to confirm that the collector received it.

> **Screenshot placeholder — `faig-optional-syslog-settings`**
>
> Expected filename: `images/fortiaigate/faig-optional-syslog-settings.png`
>
> Caption: Configure FortiAIGate to send logs by UDP/514 to the deployed syslog collector.
>
> Capture: Logs > Log Settings with the syslog destination enabled and UDP/514 visible. Replace the real ClusterIP with `{{syslog_target_ip}}` or obscure it before committing.

## Next Step

Install scenarios, render their work order, and continue with
[Scenario GUI Configuration](fortiaigate-gui-config.md). After all desired
scenario flows are created, run `python3 -m functional_test validate` from
`<repo_root>`.

The global passthrough flow is reused by Detailed chatbot testing and by any
explicitly enabled, loop-safe FortiAIGate re-entry chain.
