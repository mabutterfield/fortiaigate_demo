# Manual Quick Start

This is the step-by-step manual deployment path for the FortiAIGate demo. Run these commands from the `fortiaigate_demo` repo root unless a step explicitly says otherwise.

## Prerequisites

- Workstation with a POSIX-style shell. macOS and Linux are tested. Windows users should use WSL2; native Windows may work for some tools but is not a supported/tested control-node path.
- AWS CLI configured for your AWS authentication method, such as IAM Identity Center / SSO
- Terraform, Ansible, Docker, Python 3, and SSH available on your workstation
- Docker must be usable by the current workstation user without `sudo`
- SSH key pair already present in AWS
- Allow `terraform/aws-prep` to create the k3s EC2 IAM role/profile, or set the
  prep variables to known existing names before applying
- FortiAIGate release image archives outside this repo
- FortiAIGate Helm chart extracted outside this repo
- FortiAIGate license files outside this repo

Helm and kubectl do not need to be installed locally for the normal AWS workflow.
Ansible installs and uses them on the k3s host.

No custom local Terraform or Ansible builds are required. Before starting, verify AWS CLI profile access:

```bash
aws configure list-profiles
aws sts get-caller-identity --profile <profile-name>
```

Expected parent workspace layout:

The sample variables and documentation assume this parent `FAIG/` layout. You
can use different paths, but then set the corresponding variables in
`ansible/group_vars/all.yml`.

```text
FAIG/
  fortiaigate_demo/          this Git repo
  FAIG_helm/
    8.0.0/
      fortiaigate/           extracted Helm chart directory
    8.0.1/
      fortiaigate/           extracted Helm chart directory
  licenses/
    License1.lic
  images/
    8.0.0/
      FAIG_api-V8.0.0-build0024-FORTINET.tar
      ...
    8.0.1/
      FAIG_api-V8.0.1-build0031-FORTINET.tar
      ...
  tmp/                       generated local chart archives
```

The vendor Helm chart `.tar.gz` files may be stored under `FAIG_helm/<version>/`, but the deployment uses the extracted `fortiaigate/` chart directory.

Local files you normally create or edit are intentionally not tracked:

- `terraform/common.tfvars`
- `terraform/aws-ecr/terraform.tfvars`
- `terraform/aws-prep/terraform.tfvars`
- `terraform/aws-ec2-k3s/terraform.tfvars`
- `ansible/group_vars/env.yml`
- `ansible/group_vars/images.yml`
- `ansible/group_vars/all.yml`

Never commit real `terraform.tfvars`, Ansible secret vars, license files, private keys, kubeconfigs, certificates, API tokens, or generated credentials.

## Quick Start

Run Quick Start commands from the `fortiaigate_demo` repo root unless a step
explicitly says otherwise.
Terraform commands intentionally use `-chdir` so you can stay at the repo root
while moving through the Terraform modules. If you manually `cd` into a module
directory, omit the matching `terraform -chdir=...` prefix.

### Authenticate To AWS

```bash
# Use the login command required by your AWS profile.
# IAM Identity Center / SSO profiles normally use:
aws sso login --profile <profile-name>
# Add --use-device-code when your environment requires device-code login.
```

For non-SSO profiles, use your normal AWS login flow; the workflow only
requires that `aws sts get-caller-identity --profile <profile-name>` succeeds.

### Terraform 1 - Shared Config

Create the shared Terraform config once. Edit the copied file before running
Terraform. Subsequent runs reuse this file.

```bash
cp terraform/common.tfvars.example terraform/common.tfvars
```

Set `aws_profile`, `aws_region`, `name_prefix`, `allowed_ingress_cidr`, and
`tags` in `terraform/common.tfvars`. `allowed_ingress_cidr` can be one CIDR
string or a list of CIDR strings; the list form is preferred for multiple
operators. Do not put secrets or access keys in this file.

Each Terraform module has a tracked `common.auto.tfvars` symlink to
`../common.tfvars`, so shared values are loaded automatically by
`terraform plan` and `terraform apply`.

### Terraform 2 - Registry: ECR

Create the ECR module variables once. Edit the copied file before running
Terraform. Subsequent runs reuse this file.

```bash
cp terraform/aws-ecr/terraform.tfvars.example terraform/aws-ecr/terraform.tfvars
```

Set registry-specific values such as `repo_prefix` and `repositories` in
`terraform/aws-ecr/terraform.tfvars`.

Create or import private ECR repositories:

```bash
terraform -chdir=terraform/aws-ecr init
terraform -chdir=terraform/aws-ecr apply
```

This module writes `ansible/group_vars/ecr.generated.yml` for Ansible.

If ECR repositories already exist, import them into `terraform/aws-ecr`.
Completing ECR create/import is enough for image publishing to start. Image
publishing can take a while because release archives are loaded, tagged, and
pushed. If you are in a hurry, start the Ansible image publishing step after
ECR is ready while continuing the remaining Terraform work in another terminal.
See [ECR](ecr.md).

### Terraform 3 - AWS Prep

Create the AWS prep variables once. Edit the copied file before running
Terraform. Subsequent runs reuse this file.

```bash
cp terraform/aws-prep/terraform.tfvars.example terraform/aws-prep/terraform.tfvars
```

Set IAM, EIP allocation, ECR pull, and Bedrock IAM options in
`terraform/aws-prep/terraform.tfvars`.

Create shared AWS prep resources:

```bash
terraform -chdir=terraform/aws-prep init
terraform -chdir=terraform/aws-prep apply
```

This module creates the k3s EC2 IAM role/profile, scoped ECR pull permissions,
trusted source CIDR outputs, preallocated EIPs, and optional Bedrock IAM
credentials for alternate Bedrock-direct testing.
When `registry_backend = "ecr"`, it reads repository ARNs from the ECR
Terraform state configured by `aws_ecr_state_path`.

The default FortiAIGate GUI setup uses LiteLLM, not Bedrock direct. Bedrock
direct provider values are documented as an alternate/reference path in
`docs/FortiAIGate-initial-config.MD`.

### Terraform 4 - EC2 k3s Foundation

Create the EC2 k3s variables once. Edit the copied file before running
Terraform. Subsequent runs reuse this file.

```bash
cp terraform/aws-ec2-k3s/terraform.tfvars.example terraform/aws-ec2-k3s/terraform.tfvars
```

Set `ssh_key_name` in `terraform/common.tfvars`. Set
`ssh_private_key_file`, `instance_type`, and network CIDRs in
`terraform/aws-ec2-k3s/terraform.tfvars`.

Deploy the k3s host and AWS network foundation:

```bash
terraform -chdir=terraform/aws-ec2-k3s init
terraform -chdir=terraform/aws-ec2-k3s apply
```

Minimum `terraform/aws-ec2-k3s/terraform.tfvars` values to review:

- `aws_prep_state_path`
- `ssh_private_key_file`; `ssh_key_name` is shared from `terraform/common.tfvars`
- `ec2_pull_github_keys`, optionally, to import GitHub public SSH keys on first boot
- `instance_type` if the default `g4dn.4xlarge` is not the target size
- `k3s_subnet_mode`, which defaults to `public`
- VPC, subnet, k3s pod, and k3s service CIDRs

Optionally validate the instance from the CLI:

Set the output-backed shell variables:

```bash
AWS_PROFILE="$(terraform -chdir=terraform/aws-ec2-k3s output -raw aws_profile)"
AWS_REGION="$(terraform -chdir=terraform/aws-ec2-k3s output -raw aws_region)"
INSTANCE_ID="$(terraform -chdir=terraform/aws-ec2-k3s output -raw instance_id)"
```

Run the validation command:

```bash
aws ec2 describe-instance-status \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --instance-ids "$INSTANCE_ID" \
  --include-all-instances \
  --query 'InstanceStatuses[0].{Instance:InstanceState.Name,System:SystemStatus.Status,InstanceStatus:InstanceStatus.Status}' \
  --output table
```

Get the SSH command:

```bash
terraform -chdir=terraform/aws-ec2-k3s output ssh_command
```

Run the `ssh_command` output before starting Ansible. If SSH does not work, Ansible will not work.

### Ansible 1 - Shared Config And Image Publishing

Create the Ansible variable files once. Edit the copied files before running
Ansible. Subsequent runs reuse these files.

```bash
cp ansible/group_vars/env.example.yml ansible/group_vars/env.yml
cp ansible/group_vars/images.example.yml ansible/group_vars/images.yml
cp ansible/group_vars/all.example.yml ansible/group_vars/all.yml
```

When pulling repo updates, sync any newly added example defaults into existing
local files before reviewing values. Existing local values are preserved; new
defaults are appended at the bottom for review.

```bash
python3 scripts/sync_all_vars.py
```

Set local values in `ansible/group_vars/env.yml`, especially:

- `aws_profile`
- `aws_region`
- `faig_workspace_root` when your `FAIG` workspace is not the parent of this repo
- `registry_type`

Set local values in `ansible/group_vars/all.yml`, especially:

- `fortiaigate_version`
- license file list under the default `FAIG/licenses`, or a custom `license_source_dir`
- `litellm_master_key`, `litellm_ui_username`, and `litellm_ui_password` placeholders before exposing LiteLLM
- Ollama endpoint/model if used for validation

By default, `faig_workspace_root` resolves to the parent `FAIG` directory from the Ansible playbook location. You can override it per shell:

```bash
export FAIG_WORKSPACE_ROOT=/absolute/path/to/FAIG
```

Do not use `~` in `fortiaigate_chart_path` or `fortiaigate_chart_archive_local_path`; Ansible path tests and delegated `command` tasks do not reliably expand it.

Expected chart layout:

```text
FAIG_helm/
  8.0.0/
    fortiaigate/
      Chart.yaml
  8.0.1/
    fortiaigate/
      Chart.yaml
```

Publish FortiAIGate release images:

```bash
ansible-playbook ansible/playbooks/publish_images.yml
```

Publish only selected FortiAIGate target repositories when troubleshooting or
refreshing a subset:

```bash
ansible-playbook ansible/playbooks/publish_images.yml \
  -e publish_target_repos=api,webui
```

Image publishing currently reads release archive metadata, loads only missing
or changed source images into the local Docker image store, tags the local
images, and pushes them to ECR. Keep at least 2x-3x the total release image
archive size available on the local Docker disk before running the publish
playbook.

Publish the demo chatbot image after the `chatbot-basic` ECR repository exists:

```bash
ansible-playbook ansible/playbooks/publish_chatbot_images.yml
```

The chatbot image publisher is separate from the FortiAIGate release-image
publisher. It builds `fortiaigate_demo/chatbot/app` and pushes the generic app
image used by the consolidated chatbot UI. The default ECR configuration keeps
FortiAIGate release repositories immutable, but makes `chatbot-basic` mutable
for development. With `chatbot_publish_overwrite_existing_tag: true`, rerunning
the publisher can rebuild and push the same `chatbot_image_tag`. The chatbot
deployment uses `chatbot_image_pull_policy: Always` so redeploying the chart
pulls the updated same-tag image.

The chatbot MCP agent loop and LiteLLM model/profile selector require the
`v0.5.0` chatbot image or newer.

### Ansible 2 - Bootstrap k3s

Bootstrap the k3s host:

```bash
ansible-playbook ansible/playbooks/bootstrap_gpu_k3s.yml
```

`bootstrap_gpu_k3s.yml` runs the k3s foundation validation before it finishes.
Run the standalone validation playbook only when bootstrap does not report
`K3s status: GO`, or when rechecking the host after troubleshooting:

```bash
ansible-playbook ansible/playbooks/validate_k3s.yml
```

### Ansible 3 - Deploy FortiAIGate

Deploy FortiAIGate:

```bash
ansible-playbook ansible/playbooks/deploy_fortiaigate.yml
```

The deploy playbook uses `aws_profile` on the Ansible controller to get an ECR
login token only when `fortiaigate_ecr_token_source: controller_profile`.
By default it uses the EC2 instance role to get the ECR token on the k3s host,
then creates the Kubernetes pull secret. `terraform/aws-prep` creates the EC2
role/profile and attaches scoped ECR pull permissions when
`registry_backend = "ecr"`.

Helm deploys the FortiAIGate release asynchronously. The deploy playbook returns
after Helm accepts the install or upgrade; Kubernetes may still be pulling
images, starting pods, binding storage, and activating FortiAIGate services.

### Ansible 4 - Deploy LiteLLM Proxy

Deploy the shared LiteLLM proxy:

```bash
ansible-playbook ansible/playbooks/deploy_litellm.yml
```

LiteLLM is the shared OpenAI-compatible model proxy for the demo UIs. The
direct path is `UI -> LiteLLM -> Bedrock`. The FortiAIGate path is
`UI -> FortiAIGate explicit /v1/<flow-name> path -> LiteLLM -> Bedrock` after
FortiAIGate is manually configured to use LiteLLM as its upstream provider.

Check readiness separately:

```bash
ansible-playbook ansible/playbooks/status_litellm.yml
```

Use the validation playbook when you want a failing gate:

```bash
ansible-playbook ansible/playbooks/validate_litellm.yml
```

Use the direct test playbook when checking model alias routing or backend
system-prompt injection:

```bash
ansible-playbook ansible/playbooks/test_litellm_direct.yml
```

By default this checks the core pre-GUI profiles from
`litellm_direct_test_models`: `pass-bedrock`, `demo-a`, and `demo-b`. Adjust
that list in Ansible vars when you want a different default set.

To test every configured LiteLLM model/profile alias from
`litellm_direct_test_models` or the LiteLLM `/models` response when the list is
empty:

```bash
ansible-playbook ansible/playbooks/test_litellm_direct.yml \
  -e litellm_direct_test_poll_all_endpoints=true
```

The shorter shared extra var `-e poll_all_endpoints=true` works for both the
LiteLLM and FortiAIGate test playbooks.

The default LiteLLM Admin/API URL is:

- `http://<k3s-public-ip>:30083/ui/`

Backend demo instructions are mounted into LiteLLM and injected by the custom
pre-call hook, not by Open WebUI or the custom chatbot frontend.

The default LiteLLM deployment exposes model aliases backed by the same Bedrock
model, plus an optional chained FAIG inspection alias:

- `pass-bedrock`: no backend instruction injection; LiteLLM proxies to Bedrock
- `demo-a`: uses `chatbot/instructions/default/instructions.txt`
- `demo-b`: uses `chatbot/instructions/alternate/instructions.txt`
- `demo-a-faig-be`: uses default instructions, then calls the
  configured backend FortiAIGate URI as an OpenAI-compatible upstream
- `demo-b-faig-be`: uses alternate instructions, then calls the
  configured backend FortiAIGate URI as an OpenAI-compatible upstream

Add more aliases by extending `litellm_models` and `litellm_instruction_profiles`
in `ansible/group_vars/all.yml`, then rerun `deploy_litellm.yml`.

### Optional - Deploy Open WebUI

Open WebUI is available as a secondary chat UI, but it is disabled by default.
The primary lab walkthrough uses the custom chatbot because it exposes the
direct LiteLLM, FAIG static, FAIG intelligent, and MCP controls. To deploy
Open WebUI, set this in `ansible/group_vars/all.yml`:

```yaml
openwebui_enabled: true
```

Then deploy the consolidated Open WebUI front end:

```bash
ansible-playbook ansible/playbooks/deploy_openwebui.yml
```

The deploy playbook returns after Helm accepts the install or upgrade. Open
WebUI may still be pulling images, creating PVCs, or waiting for probes. Check
readiness separately:

```bash
ansible-playbook ansible/playbooks/status_openwebui.yml
```

Use the validation playbook when you want a failing gate after the instance
should be ready:

```bash
ansible-playbook ansible/playbooks/validate_openwebui.yml
```

The default Open WebUI URL is:

- `http://<k3s-public-ip>:30080`

Open WebUI is configured with both provider URLs: direct LiteLLM and
FortiAIGate. Use Open WebUI's model/provider selection to compare the direct
and inspected paths. The FortiAIGate URL uses the in-cluster nginx ingress
service by default, which avoids public-IP hairpinning and self-signed TLS trust
issues.

### Ansible 6 - Deploy Chatbot Test Page

Deploy the consolidated custom chatbot UI:

```bash
ansible-playbook ansible/playbooks/deploy_chatbots.yml
```

The default chatbot URL is:

- `http://<k3s-public-ip>:30081`

The chatbot has three backend modes:

- `Direct LiteLLM`: shows a LiteLLM profile selector populated from
  `chatbot_model_options`, which defaults to `pass-bedrock`, `demo-a`,
  `demo-b`, `demo-a-faig-be`, and `demo-b-faig-be`.
- `FAIG Static Route`: sends to route-specific FortiAIGate URI paths from
  `chatbot_faig_static_routes`.
- `FAIG Intelligent Route`: sends to `/v1/intelligent`. The `passthrough`
  option sends no model-route header and maps to LiteLLM alias `pass-bedrock`;
  `demo-a` and `demo-b` send the configurable `faig_model_route_header_name`
  header, default `X-FAIG-Model-Route`.

Backend demo instructions are normally injected by LiteLLM so FortiAIGate can
inspect the user-visible request before those backend-only demo instructions
are added.

The `demo-a-faig-be` and `demo-b-faig-be` aliases are scaffolds for this
chained inspection path:

```text
chatbot
  -> FortiAIGate static URI
  -> LiteLLM model demo-a-faig-be or demo-b-faig-be
  -> FortiAIGate /v1/passthrough
  -> litellm-pass-bedrock
  -> LiteLLM pass-bedrock
```

The static and intelligent FortiAIGate URI/provider mappings still need to be
configured in FortiAIGate. The post-injection re-entry path reuses
`/v1/passthrough`; do not configure that flow to route back to a `*-faig-be`
model, or the chain can loop. LiteLLM treats the re-entry URI as an
OpenAI-compatible base URL, so `/v1/passthrough` receives
`/v1/passthrough/chat/completions`.

When a frontend-layer prompt is intentionally needed, set either
`chatbot_frontend_system_prompt` or
`chatbot_frontend_system_prompt_source_path` in `ansible/group_vars/all.yml`.
The sample file is `chatbot/instructions/frontend/instructions.txt`.

Check readiness separately:

```bash
ansible-playbook ansible/playbooks/status_chatbots.yml
```

Use the validation playbook when you want a failing gate:

```bash
ansible-playbook ansible/playbooks/validate_chatbots.yml
```

### Optional - Deploy MCP Demo Tools

Deploy the optional MCP demo tool server:

```bash
ansible-playbook ansible/playbooks/deploy_mcp.yml
```

The MCP baseline runs in namespace `mcp`. It provides deterministic customer,
ticket, policy, and echo tools for the later Python agent loop. It exposes HTTP
on the generated default NodePort `30084`; if the optional HTTPS gateway is
enabled, it also exposes HTTPS on `30447`. It does not require ECR image
publishing.

Check readiness separately:

```bash
ansible-playbook ansible/playbooks/status_mcp.yml
```

Use the validation playbook when you want a failing gate:

```bash
ansible-playbook ansible/playbooks/validate_mcp.yml
```

### Ansible 7 - Deploy Demo Home Page

Deploy a small home page with links to FortiAIGate, LiteLLM Admin UI, Open
WebUI, chatbot test pages, and MCP tools:

```bash
ansible-playbook ansible/playbooks/deploy_demo_home.yml
```

The default home page URL is:

- `http://<k3s-public-ip>:30082`

Check readiness separately:

```bash
ansible-playbook ansible/playbooks/status_demo_home.yml
```

Use the validation playbook when you want a failing gate:

```bash
ansible-playbook ansible/playbooks/validate_demo_home.yml
```

When using the default public NodePort flow, `terraform/aws-ec2-k3s` generates
and opens the standard demo ports, then writes
`ansible/group_vars/ports.generated.yml`. The default generated HTTP ports are
reserved consistently: Open WebUI uses `30080` when enabled, chatbot `30081`,
demo home `30082`, LiteLLM Admin/API `30083`, and MCP demo tools `30084`.

### Optional - Deploy HTTPS Gateway

HTTP remains the primary demo access path. To add optional HTTPS listeners for
the chatbot front end, demo home, LiteLLM Admin/API, MCP demo tools, and
Open WebUI when enabled, set
`demo_https_gateway_enabled: true` in `ansible/group_vars/all.yml`, apply
`terraform/aws-ec2-k3s` so the generated HTTPS ports are open, then run:

```bash
ansible-playbook ansible/playbooks/deploy_demo_https_gateway.yml
```

By default the role generates a self-signed certificate on the k3s host and
reuses it on later runs. Set `demo_https_gateway_self_signed: false` with
`demo_https_gateway_cert_local_path` and `demo_https_gateway_key_local_path`
to use your own certificate pair. Browser warnings are expected for self-signed
certificates.

The default generated HTTPS ports use the same index as the HTTP services:
Open WebUI `30443` proxies `30080` when enabled, chatbot `30444` proxies
`30081`, demo home `30445` proxies `30082`, LiteLLM Admin/API `30446` proxies
`30083`, and MCP demo tools `30447` proxies `30084`.

### Validation And First Provider Setup

Use the status playbook to monitor readiness and get the login URL:

```bash
ansible-playbook ansible/playbooks/status_fortiaigate.yml
```

FortiAIGate 8.0.1 serves the web UI under `/ui/`; `/` is preserved for the
chart's core service route. The status and validation playbooks use
`fortiaigate_ui_path` to print and check the right UI URL for the selected
version.

Rerun `status_fortiaigate.yml` until it reports `FortiAIGate status: READY`,
then run the deeper validation checks:

```bash
ansible-playbook ansible/playbooks/validate_faig.yml
```

For the first GUI login, AI flow, guard, deploy, and lab API-key settings, see
[FortiAIGate-initial-config.MD](FortiAIGate-initial-config.MD).

To print the Bedrock and LiteLLM values needed by the FortiAIGate GUI:

```bash
ansible-playbook ansible/playbooks/show_demo_outputs.yml
```

The output includes LiteLLM API details, LiteLLM UI credentials, application
URLs, optional HTTPS URLs, and the Terraform-generated SSH command for the k3s
host.

The default network layout avoids overlap between the AWS VPC and k3s internals: AWS VPC `10.20.0.0/16`, k3s pods `10.60.0.0/16`, and k3s services `10.70.0.0/16`. Override these in `terraform/aws-ec2-k3s/terraform.tfvars` before creating the host if they conflict with your environment.

## Operating Notes

Run `bootstrap_gpu_k3s.yml` before `deploy_fortiaigate.yml`. The deploy playbook expects `/etc/rancher/k3s/k3s.yaml` to exist on the target host.

Bootstrap runs the same k3s foundation checks as `validate_k3s.yml` before it completes. The standalone playbook is useful after rebuilds, network changes, or manual troubleshooting. A successful run prints `K3s status: GO`; the standalone validation playbook prints `K3s status: NO GO` with the failed check before exiting on validation failure.

`terraform/aws-prep` creates IAM, EIP, and Bedrock prep resources. `terraform/aws-ec2-k3s` writes `ansible/inventory/aws.generated.ini` and `ansible/group_vars/ports.generated.yml`. `terraform/aws-ecr` writes `ansible/group_vars/ecr.generated.yml`. Generated Ansible files are ignored by Git.

By default, `deploy_fortiaigate.yml` submits the Helm release and returns after Helm accepts the install or upgrade. It does not wait for every pod to become Ready. Use `status_fortiaigate.yml` for the lightweight `READY` / `NOT READY` / `ERROR` answer and login URL. Use `validate_faig.yml` for deeper GPU, Triton, UI/API, and optional provider checks.

Playbook intent:

- `validate_k3s.yml`: validates the Kubernetes foundation, including system pod health and DNS from inside the cluster, and prints a `GO` / `NO GO` summary
- `status_fortiaigate.yml`: gives a simple FortiAIGate `READY`, `NOT READY`, or `ERROR` answer plus the HTTPS login URL
- `validate_faig.yml`: performs deeper FortiAIGate checks after status is ready

After bootstrap, the SSH user has passwordless sudo, `/home/<user>/.kube/config`, and shell profile configuration so interactive `kubectl` works without `sudo` on the k3s host.

FortiAIGate licenses bind to instance identity and may require time to reset after repeated destroy/redeploy cycles. Keep licenses outside this repo; the default `license_source_dir` is `{{ faig_workspace_root }}/licenses`, which resolves to `FAIG/licenses`. Use `fortiaigate_license_files` for single-node labs unless an explicit node-to-license map is required.

## Reference: Bedrock Direct Provider

The default GUI setup uses LiteLLM as the FortiAIGate provider. Use this section
only when testing a Bedrock-direct FortiAIGate guard/provider without LiteLLM in
the middle.

Temporary Bedrock credentials are created by `terraform/aws-prep` when
`enable_bedrock_iam = true`. Retrieve the GUI values from the repo root:

```bash
terraform -chdir=terraform/aws-prep output bedrock_access_key_id
terraform -chdir=terraform/aws-prep output -raw bedrock_secret_access_key
terraform -chdir=terraform/aws-prep output bedrock_model_ids
terraform -chdir=terraform/aws-prep output bedrock_allowed_regions
```

In FortiAIGate, create the Bedrock-direct guard/provider with:

- Access Key ID from `terraform output bedrock_access_key_id`
- Secret Access Key from `terraform output -raw bedrock_secret_access_key`
- Region from the permitted `bedrock_allowed_regions`
- Model ID from the permitted `bedrock_model_ids`

To test Bedrock directly before configuring the FortiAIGate guard:

```bash
ansible-playbook ansible/playbooks/test_model_direct.yml
```

The Bedrock direct test uses `scripts/bedrock_direct_test.py` to generate the AWS SigV4 signature at runtime. Run that script directly from the repo root when you want a local-only Bedrock smoke test; it prompts from the permitted Terraform model list unless `BEDROCK_MODEL` is set.

Set `direct_model_provider=ollama` to use the same playbook for direct Ollama testing.

After the guard is configured, generate and run the first external chat test:

```bash
ansible-playbook ansible/playbooks/test_fortiaigate_chat.yml
```

The playbook uses `scripts/fortiaigate_chat_test.py` to send a short test prompt through `https://<fortiaigate-public-ip>:443/v1/chat/completions`, asks the routed model to identify itself and repeat the URI under test, and summarizes the HTTP status and response.

By default this checks only `fortiaigate_test_endpoint_path`, which defaults to
`/v1/chat/completions`, and sends the LiteLLM model alias `pass-bedrock`. To
test the default FAIG route matrix built from `chatbot_faig_static_routes`, the
selected intelligent route, and the default `/v1` fallback:

```bash
ansible-playbook ansible/playbooks/test_fortiaigate_chat.yml \
  -e fortiaigate_test_poll_all_endpoints=true
```

The shorter shared extra var `-e poll_all_endpoints=true` can be used instead
when running either FortiAIGate or LiteLLM endpoint tests.

The default FAIG route matrix is seven endpoints: `passthrough`, `demo-a`,
`demo-b`, `demo-a-faig-be`, `demo-b-faig-be`, `intelligent`, and `default`.
`/v1/openwebui` and every intelligent-route profile are optional diagnostic
cases controlled by `fortiaigate_test_include_openwebui_endpoint` and
`fortiaigate_test_include_all_header_route_profiles`.

Ollama route testing is skipped by default. Include it only when the Ollama
provider is deployed and configured in FortiAIGate:

```bash
ansible-playbook ansible/playbooks/test_fortiaigate_chat.yml \
  -e fortiaigate_test_poll_all_endpoints=true \
  -e fortiaigate_test_include_ollama_endpoint=true
```
