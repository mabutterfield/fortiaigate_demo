# FortiAIGate Initial Config

This guide covers the first FortiAIGate GUI steps after the Helm deployment is
ready. Use it after `status_fortiaigate.yml` reports `FortiAIGate status: READY`.

## Required Provider Inputs

Before starting the GUI flow, collect the provider values you will enter into
FortiAIGate. The consolidated output playbook prints the current values from
Terraform outputs and Ansible vars. It also prints the main access URLs for
FortiAIGate, the chatbot front end, OpenWebUI, and LiteLLM Admin:

```bash
ansible-playbook ansible/playbooks/show_demo_outputs.yml
```

By default, the playbook does not print the Bedrock secret access key. To print
it for GUI entry, run:

```bash
ansible-playbook ansible/playbooks/show_demo_outputs.yml -e demo_outputs_show_secrets=true
```

Treat terminal scrollback as sensitive when printing secrets.

### Bedrock Direct Provider

Use these values if FortiAIGate will connect directly to AWS Bedrock:

| FortiAIGate input | Source |
|---|---|
| LLM model | `terraform -chdir=terraform/aws-prep output bedrock_model_ids` |
| Access key ID | `terraform -chdir=terraform/aws-prep output bedrock_access_key_id` |
| Secret access key | `terraform -chdir=terraform/aws-prep output -raw bedrock_secret_access_key` |

Use one of the permitted regions from:

```bash
terraform -chdir=terraform/aws-prep output bedrock_allowed_regions
```

### LiteLLM Proxy Provider

Use these values when FortiAIGate should proxy through the in-cluster LiteLLM
provider:

| FortiAIGate input | Default/source |
|---|---|
| API endpoint | `http://litellm.litellm.svc.cluster.local:4000/v1` |
| API key | `litellm_master_key` in `ansible/group_vars/all.yml` |
| Model name | `litellm_model_alias`, default `demo-profile` |

The LiteLLM API endpoint is private to the Kubernetes cluster. It is reachable
from FortiAIGate pods and other in-cluster workloads, but not directly from a
browser unless you use the LiteLLM NodePort or another published route.

If `demo_https_gateway_enabled` is true, `show_demo_outputs.yml` also prints
optional HTTPS URLs for OpenWebUI, the chatbot front end, demo home, and
LiteLLM Admin/API. These URLs use a self-signed certificate by default and are
an optional encrypted public access path; the primary internal provider
endpoint remains plain HTTP inside the cluster.

## 1. Log In

Open the login URL printed by `status_fortiaigate.yml`.

Default lab credentials:

| Version | Username | Password |
|---|---|---|
| 8.0.0 | `admin` | `fortinet` |
| 8.0.1 | `admin` | blank |

FortiAIGate 8.0.1 serves the UI under `/ui/`. The status and validation
playbooks print the version-aware UI URL when `fortiaigate_ui_path` is set or
derived from `fortiaigate_version`.

Change the default password when prompted.

## 2. Define The AI Flow

Create the initial AI flow that will receive OpenAI-compatible chat requests.

![Define flow](images/step1.png)

## 3. Define The Guard

Create the Bedrock-backed guard/provider. This step needs the Bedrock access
key, secret access key, permitted region, and model ID from
`terraform/aws-prep`.

![Define guard](images/step2.png)

## 4. Configure Guards

Enable the guard for the flow with the toggle switch.

![Configure guards](images/step3.png)

## 5. Deploy

Review the summary page and deploy the configuration.

![Deploy summary](images/step4.png)

## 6. Disable API Key Validation For Lab Testing

Edit the AI flow and disable API key validation for easier first-pass testing.
This is a lab convenience so `test_fortiaigate_chat.yml` can call
`/v1/chat/completions` without a client API key.

![Disable API key validation](images/step5.png)

After this is complete, run the external chat test:

```bash
cd ansible
ansible-playbook playbooks/test_fortiaigate_chat.yml
```
