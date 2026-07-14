# Deployment Runbook

This runbook describes the normal AWS lab deployment workflow.

Unless noted otherwise, command blocks start from the `fortiaigate_demo` repo root.

## 1. Prepare Local Inputs

Required local inputs are intentionally ignored by Git:

- `terraform/common.tfvars`
- `terraform/aws-ecr/terraform.tfvars`
- `terraform/aws-prep/terraform.tfvars`
- `terraform/aws-ec2-k3s/terraform.tfvars`
- `ansible/group_vars/env.yml`
- `ansible/group_vars/all.yml`
- `ansible/group_vars/images.yml`
- FortiAIGate license files
- FortiAIGate release image archives
- FortiAIGate Helm chart archives and extracted chart directories

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

The deployment role expects `fortiaigate_chart_path` to point at the extracted chart directory, not the vendor `.tgz` file.
The vendor Helm chart `.tar.gz` can be stored beside the extracted chart for reference, but automation does not require it.

## 2. Authenticate to AWS

```bash
aws sso login --profile <profile-name>
```

Use the same profile in Terraform and Ansible variables.

Quick AWS CLI troubleshooting:

```bash
aws configure list-profiles
aws sts get-caller-identity --profile <profile-name>
```

If these fail, fix the AWS CLI/SSO session before troubleshooting Terraform.

## 3. Configure Shared Terraform Values

```bash
cd terraform
cp common.tfvars.example common.tfvars
```

Set `aws_profile`, `aws_region`, `name_prefix`, `allowed_ingress_cidr`, and
any shared tags in `common.tfvars`. `allowed_ingress_cidr` can be one CIDR
string or a list of CIDR strings; use `/32` entries for individual public IPs.

## 4. Create ECR Repositories

```bash
cd aws-ecr
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt
terraform validate
terraform apply
```

Terraform writes non-secret registry values to:

```text
ansible/group_vars/ecr.generated.yml
```

If repositories already exist, import them before applying. See [terraform.md](terraform.md).

After ECR create/import completes, image publishing can start. Publishing may
take a while because Docker loads, tags, compares, and pushes large release
images.

## 5. Prepare AWS IAM, EIPs, and Bedrock Credentials

```bash
cd ../aws-prep
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt
terraform validate
terraform apply
```

This creates the k3s EC2 role/profile, scoped ECR pull permissions, trusted
source CIDRs, prep-owned public EIPs, and optional Bedrock IAM credentials. When
`registry_backend = "ecr"`, the pull policy uses repository ARNs from the ECR
Terraform state configured by `aws_ecr_state_path`.

## 6. Deploy AWS Infrastructure

```bash
cd ../aws-ec2-k3s
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt
terraform validate
terraform apply
```

Terraform writes the generated Ansible inventory to:

```text
ansible/inventory/aws.generated.ini
```

Minimum `terraform.tfvars` values to review:

- `aws_prep_state_path`
- `ssh_key_name` in `terraform/common.tfvars`
- `ssh_private_key_file` when the AWS key pair does not use your default SSH key
- `ec2_pull_github_keys` only when importing GitHub public SSH keys on first boot
- `instance_type` when changing from the default `g4dn.4xlarge`
- VPC, subnet, k3s pod, and k3s service CIDRs

If the EC2 key pair uses a non-default SSH key, set `ssh_private_key_file` in `terraform.tfvars`. Terraform includes that key in the generated Ansible inventory and in the `ssh_command` output.

If `ec2_pull_github_keys` is set, cloud-init appends those public GitHub SSH
keys to `/home/ubuntu/.ssh/authorized_keys` during first boot. Leave it empty
for the default AWS key-pair-only behavior.

Validate AWS instance status and SSH before running Ansible:

```bash
AWS_PROFILE="$(terraform output -raw aws_profile)"
AWS_REGION="$(terraform output -raw aws_region)"
INSTANCE_ID="$(terraform output -raw instance_id)"

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
terraform output ssh_command
```

Run the `ssh_command` output. If SSH does not work, fix AWS networking, the key pair, or `ssh_private_key_file` before starting Ansible.

The AWS and k3s networks must not overlap. The current default layout is:

```yaml
vpc_cidr: 10.20.0.0/16
public_subnet_cidr: 10.20.1.0/24
k3s_private_subnet_cidr: 10.20.2.0/24
fortigate_public_subnet_cidr: 10.20.10.0/24
fortiweb_public_subnet_cidr: 10.20.11.0/24
k3s_cluster_cidr: 10.60.0.0/16
k3s_service_cidr: 10.70.0.0/16
k3s_cluster_dns: 10.70.0.10
```

Terraform passes these k3s values into the generated Ansible inventory. Override them in `terraform.tfvars` before creating the host when your environment already uses one of these ranges.

The default `k3s_subnet_mode` is `public`, which preserves direct SSH and browser access through the prep-owned k3s Elastic IP. The k3s instance does not request an auto-assigned ephemeral public IP. Use `private` only when a private management path or FortiGate/FortiWeb front end is ready.

## 7. Configure Ansible Variables and Publish Images

```bash
cd ../../ansible
cp group_vars/env.example.yml group_vars/env.yml
cp group_vars/images.example.yml group_vars/images.yml
cp group_vars/all.example.yml group_vars/all.yml
ansible-playbook playbooks/publish_images.yml
```

The image publisher reads release archive metadata, loads only missing or changed source images into local Docker, preserves the tags embedded in the archives, and pushes to the configured registry. Docker must be usable by the current workstation user without `sudo`.

The current workflow stages images through the local Docker image store before
ECR upload. Keep at least 2x-3x the total release image archive size available
on the local Docker disk before publishing.

To publish one version:

```bash
ansible-playbook playbooks/publish_images.yml -e publish_image_version=8.0.0
```

To publish only selected FortiAIGate target repositories:

```bash
ansible-playbook playbooks/publish_images.yml \
  -e publish_target_repos=api,webui
```

To publish only the chatbot image without loading FortiAIGate release archives:

```bash
ansible-playbook playbooks/publish_chatbot_images.yml
```

To publish all active builds, set `state: active` in `group_vars/images.yml` and run the playbook without overrides.

For FortiAIGate 8.0.0:

```yaml
fortiaigate_version: "8.0.0"
fortiaigate_image_tag: "V8.0.0-build0024"
fortiaigate_triton_model_image_tag: "0.1.4"
fortiaigate_triton_image_tag: "25.11-onnx-trt-agt"
```

For FortiAIGate 8.0.1:

```yaml
fortiaigate_version: "8.0.1"
fortiaigate_image_tag: "V8.0.1-build0031"
fortiaigate_triton_model_image_tag: "0.1.6-s1"
fortiaigate_triton_image_tag: "25.11-onnx-trt-agt-s1"
```

By default, paths are derived from `faig_workspace_root`, which resolves to the parent `FAIG` directory from the Ansible playbook location:

```yaml
faig_workspace_root: "{{ lookup('env', 'FAIG_WORKSPACE_ROOT') | default((playbook_dir + '/../../..') | realpath, true) }}"
fortiaigate_chart_path: "{{ faig_workspace_root }}/FAIG_helm/{{ fortiaigate_version }}/fortiaigate"
fortiaigate_chart_archive_local_path: "{{ faig_workspace_root }}/tmp/fortiaigate-chart.tgz"
```

Set `FAIG_WORKSPACE_ROOT` when the workspace is somewhere else:

```bash
export FAIG_WORKSPACE_ROOT=/absolute/path/to/FAIG
```

Use absolute paths. Do not use `~` in these variables because Ansible path checks and `command.argv` do not shell-expand it.

For single-node labs, set:

```yaml
license_source_dir: "{{ faig_workspace_root }}/licenses"
fortiaigate_license_files:
  - License1.lic
fortiaigate_licenses: {}
```

Ansible maps the first license file to the discovered Kubernetes node name. Use `fortiaigate_licenses` only when an exact node-to-license mapping is required. The default expects license files under `FAIG/licenses`; override `license_source_dir` only when they live somewhere else.

By default, FortiAIGate TLS uses the chart's bundled certificate and key:

```yaml
fortiaigate_ssl_cert_path: "{{ fortiaigate_chart_path }}/files/certificate/dflt.crt"
fortiaigate_ssl_key_path: "{{ fortiaigate_chart_path }}/files/certificate/dflt.key"
```

To use private TLS material, keep it outside this repo and override only the source paths:

```yaml
fortiaigate_ssl_cert_path: /path/to/private/tls.crt
fortiaigate_ssl_key_path: /path/to/private/tls.key
```

Ansible copies the selected files into the temporary remote chart copy before Helm renders.

Minimum `group_vars/env.yml` and `group_vars/all.yml` values to review:

- `fortiaigate_version` and the matching image tags
- `faig_workspace_root` in `env.yml` only when the repo is not under the default parent `FAIG` directory
- `license_source_dir` only when licenses are not under `FAIG/licenses`
- `fortiaigate_license_files`
- `fortiaigate_ingress_host` when using DNS instead of the EC2 public IP
- `validate_faig_ollama_forwarding` only after an Ollama provider exists in FortiAIGate

## 8. Bootstrap k3s

```bash
ansible-playbook playbooks/bootstrap_gpu_k3s.yml
```

Bootstrap prepares Ubuntu 24.04, NVIDIA drivers, NVIDIA container runtime, k3s, local-path storage, nginx ingress, RuntimeClass, and the NVIDIA device plugin.

After bootstrap, the SSH user can run `kubectl` without `sudo` in a new login shell.

Do not change `k3s_cluster_cidr`, `k3s_service_cidr`, or `k3s_cluster_dns` in-place on an existing k3s cluster. Rebuild the host when these values need to change.

Bootstrap ends with the `validate_k3s` role. It verifies:

- Kubernetes API reachability
- all nodes are Ready
- kube-system and ingress-nginx deployments are Available
- NVIDIA device plugin DaemonSet rollout completed
- foundation pods in `kube-system` and `ingress-nginx` are Running/Ready or Succeeded
- DNS resolution from inside a temporary pod works

A successful validation prints `K3s status: GO`. The standalone validation
playbook prints `K3s status: NO GO` with the failed check before exiting on a
validation failure. Application namespaces such as `fortiaigate` are intentionally
left to `status_fortiaigate.yml` and `validate_faig.yml`.

Rerun the same checks independently with:

```bash
ansible-playbook playbooks/validate_k3s.yml
```

## 9. Deploy FortiAIGate

```bash
ansible-playbook playbooks/deploy_fortiaigate.yml
```

The deploy playbook:

- gets an ECR login token from the k3s host EC2 instance role by default
- creates or refreshes the ECR pull secret on the k3s host
- copies the extracted chart to the remote host
- stages licenses into the temporary remote chart copy
- renders values
- runs Helm with the FortiAIGate post-renderer

The default `fortiaigate_ecr_token_source: instance_role` expects the EC2
instance profile role to have scoped ECR pull permissions. `terraform/aws-prep`
attaches those permissions when `registry_backend = "ecr"`. Set
`fortiaigate_ecr_token_source: controller_profile` only when the controller AWS
profile should generate the ECR token instead.

By default Helm does not wait for every Kubernetes workload to become Ready. This keeps the install command responsive and leaves status monitoring to the next step.

## 10. Deploy LiteLLM Proxy

```bash
ansible-playbook playbooks/deploy_litellm.yml
```

LiteLLM is the shared OpenAI-compatible model proxy for the demo UIs. Direct
traffic uses `UI -> LiteLLM -> Bedrock`. FortiAIGate-inspected traffic uses
an explicit FortiAIGate path such as `/v1/openwebui`, `/v1/demo-a`, or
`/v1/intelligent` after FortiAIGate is manually
configured to use LiteLLM as an upstream OpenAI-compatible provider.

Check LiteLLM status separately:

```bash
ansible-playbook playbooks/status_litellm.yml
```

Use this when a failing validation gate is preferred:

```bash
ansible-playbook playbooks/validate_litellm.yml
```

The default LiteLLM Admin/API NodePort is `30083`; the Admin UI path is `/ui/`.
Backend demo instructions are injected by LiteLLM through its custom pre-call
hook so the frontend applications do not own the hidden demo prompt.

The default deployment creates LiteLLM model aliases for direct and chained
inspection paths:

- `pass-bedrock`: no backend instruction injection; LiteLLM proxies to Bedrock
- `demo-a`: default backend instructions from
  `chatbot/instructions/default/instructions.txt`
- `demo-b`: alternate backend instructions from
  `chatbot/instructions/alternate/instructions.txt`
- `demo-a-faig-be`: default backend instructions, then an
  OpenAI-compatible call to the configured backend FortiAIGate URI
- `demo-b-faig-be`: alternate backend instructions, then an
  OpenAI-compatible call to the configured backend FortiAIGate URI

To add another backend prompt, add an entry to `litellm_instruction_profiles`,
add a matching `litellm_models` alias with `instruction_profile`, and rerun
`deploy_litellm.yml`.

The chatbot exposes three backend modes: `Direct LiteLLM`, `FAIG Static Route`,
and `FAIG Intelligent Route`. Static routes use route-specific URI paths such as
`/v1/demo-a`; intelligent routes use `/v1/intelligent`. The intelligent
`passthrough` option sends no route header and maps to LiteLLM alias
`pass-bedrock`, while `demo-a` and `demo-b` use the configurable
`X-FAIG-Model-Route` header.

The `demo-a-faig-be` and `demo-b-faig-be` aliases are the default scaffolds for:

```text
chatbot -> FortiAIGate static route -> LiteLLM demo profile -> FortiAIGate /v1/passthrough -> litellm-pass-bedrock -> pass-bedrock
```

FortiAIGate owns the static and intelligent URI/provider mappings. The
post-injection re-entry path reuses `/v1/passthrough`; do not point that flow at
a `*-faig-be` alias or the request can loop. LiteLLM treats
`litellm_faig_backend_base_url` as an OpenAI-compatible base URL, so the default
value ending in `/v1/passthrough` results in requests to
`/v1/passthrough/chat/completions`.

## 11. Optional: Deploy Open WebUI

Open WebUI is available as a secondary chat UI, but it is disabled by default.
The primary lab walkthrough uses the custom chatbot because it exposes the
direct LiteLLM, FAIG static, FAIG intelligent, and MCP controls. To deploy
Open WebUI, set:

```yaml
openwebui_enabled: true
```

```bash
ansible-playbook playbooks/deploy_openwebui.yml
```

The deploy playbook starts or upgrades the Helm releases and then returns. It
does not wait for every Open WebUI pod to become Ready by default.

Check Open WebUI status separately:

```bash
ansible-playbook playbooks/status_openwebui.yml
```

Use this when a failing validation gate is preferred:

```bash
ansible-playbook playbooks/validate_openwebui.yml
```

When enabled, this deploys one Open WebUI release in namespace `openwebui`,
exposed on NodePort `30080`. It is configured with both direct LiteLLM and
FortiAIGate provider URLs. The FortiAIGate URL defaults to the in-cluster nginx
ingress service path configured by `openwebui_faig_default_base_path`, which
avoids public-IP hairpin behavior and avoids making Open WebUI trust the lab's
self-signed public TLS certificate.

Open WebUI should not be path-prefixed by default. Use NodePort for the no-DNS
lab default, or set `ingress_host` values later when host-based routing is
available.

For AWS public k3s mode, `terraform/aws-ec2-k3s` generates and opens the
standard demo ports, then writes `ansible/group_vars/ports.generated.yml`.
The default generated HTTP ports are reserved consistently: Open WebUI uses
`30080` when enabled, chatbot `30081`, demo home `30082`, LiteLLM Admin/API
`30083`, and MCP demo tools `30084`.
`show_demo_outputs.yml` prints the matching HTTP/HTTPS URLs, LiteLLM UI
credentials, and the Terraform-generated SSH command for the k3s host.

## 12. Optional MCP Demo Tools

```bash
ansible-playbook playbooks/deploy_mcp.yml
```

The MCP baseline deploys a small tool server in namespace `mcp`.
It provides deterministic customer, ticket, policy, and echo tools for the
later Python agent loop. It exposes a generated NodePort for direct testing,
keeps an internal service endpoint for Kubernetes workloads, and does not
require ECR image publishing.

Check MCP status separately:

```bash
ansible-playbook playbooks/status_mcp.yml
```

Use this when a failing validation gate is preferred:

```bash
ansible-playbook playbooks/validate_mcp.yml
```

See [MCP Demo Tools](mcp.md) for data-file overrides and HTTP/HTTPS test URLs.

## 13. Monitor Status

```bash
ansible-playbook playbooks/status_fortiaigate.yml
```

This is the lightweight readiness check. It reports one of:

- `READY`: Helm is reachable and all FortiAIGate pods are Ready
- `NOT READY`: Kubernetes is reachable but at least one FortiAIGate pod is not Ready
- `ERROR`: Helm or Kubernetes status commands failed

It also prints the HTTPS login URL. The URL uses `fortiaigate_ingress_host` when set, otherwise the generated inventory `public_ip`, otherwise `ansible_host`.

FortiAIGate 8.0.1 serves the web UI under `/ui/`; `/` is preserved for the
chart's core service route. `status_fortiaigate.yml` and `validate_faig.yml`
use `fortiaigate_ui_path` to print and check the correct UI URL for the selected
FortiAIGate version.

Useful manual commands on the k3s host:

```bash
helm status fortiaigate -n fortiaigate
kubectl get pods -A
kubectl get pvc -n fortiaigate
kubectl get events -n fortiaigate --sort-by=.lastTimestamp
```

## 14. Validate

```bash
ansible-playbook playbooks/validate_faig.yml
```

Validation checks the host, Kubernetes, GPU visibility, ingress, and FortiAIGate service reachability.

Use validation after status is `READY` or when you need deeper checks. It validates GPU visibility, Triton device access, `/dev/shm`, UI/API HTTP behavior, and optional provider forwarding. The UI check uses `fortiaigate_ui_path`, which defaults to `/ui/` for FortiAIGate 8.0.1 and `/` for older releases.

At the end, validation prints an interpreted summary:

- `FortiAIGate status: READY` when all FortiAIGate pods are ready
- pod ready count and problem pods when not ready
- UI/API HTTP status checks
- HTTPS login URL

The login URL defaults to `fortiaigate_ingress_host` when set, otherwise `ansible_host`. Override the displayed URL with:

```yaml
validate_faig_login_url_override: https://faig.example.com/
```

## External Ollama

The current chart does not expose a provider bootstrap value for Ollama. Configure the provider in the FortiAIGate UI or a supported API after deployment:

```text
Provider: OpenAI-compatible
Base URL: http://<ollama-host>:11434/v1
Model:    llama3.2:1b
API key:  blank or a dummy value if required
```

The Ansible validation variables keep the same endpoint/model so validation can exercise the provider after it exists. The forwarding check is disabled by default; set `validate_faig_ollama_forwarding: true` only after the FortiAIGate provider is configured.

## Reference: Bedrock Direct Provider

The default GUI setup uses LiteLLM as the FortiAIGate provider. Use this
reference only when testing a Bedrock-direct FortiAIGate guard/provider without
LiteLLM in the middle.

`terraform/aws-prep` creates temporary IAM user credentials for manual FortiAIGate GUI entry when `enable_bedrock_iam = true`.

Set `bedrock_model_ids` after choosing models and confirming model access in the AWS account/region. Use exact Bedrock model IDs, for example `openai.gpt-oss-20b-1:0`, not short display names. Set `bedrock_allowed_regions` to the commercial US regions where those models should be invokable.

By default, Bedrock restricts credentials to the prep-owned k3s EIP plus the
CIDR or CIDRs in `allowed_ingress_cidr`. Set `bedrock_no_ip_restriction = true`
only when the key should work from any source IP.

Retrieve the values after apply:

```bash
terraform -chdir=terraform/aws-prep output bedrock_access_key_id
terraform -chdir=terraform/aws-prep output -raw bedrock_secret_access_key
terraform -chdir=terraform/aws-prep output bedrock_key_expires_at
terraform -chdir=terraform/aws-prep output bedrock_allowed_regions
terraform -chdir=terraform/aws-prep output bedrock_model_ids
```

Paste the Access Key ID, Secret Access Key, one permitted region, and one permitted model ID into the FortiAIGate Bedrock guard/provider setup.

To test Bedrock directly before configuring the FortiAIGate guard/provider, run the direct model playbook:

```bash
cd ansible
ansible-playbook playbooks/test_model_direct.yml
```

By default, `test_model_direct.yml` reads these values directly from `terraform/aws-prep` outputs:

- `bedrock_access_key_id`
- `bedrock_secret_access_key`
- `bedrock_region`
- `bedrock_allowed_regions`
- `bedrock_model_ids`

No shell exports are required for the Ansible default path. The playbook calls the repo-owned `scripts/bedrock_direct_test.py` script, which signs the request at runtime with AWS SigV4 and summarizes the response.

To run with exported credentials instead of reading Terraform outputs, export the standard AWS credential variables from the Bedrock outputs:

```bash
cd terraform/aws-prep
export AWS_ACCESS_KEY_ID="$(terraform output -raw bedrock_access_key_id)"
export AWS_SECRET_ACCESS_KEY="$(terraform output -raw bedrock_secret_access_key)"
# Only needed for temporary session credentials; aws-prep creates a normal IAM access key.
# export AWS_SESSION_TOKEN="<session-token>"
cd ../../ansible
ansible-playbook playbooks/test_model_direct.yml \
  -e direct_model_bedrock_read_credentials_from_terraform=false
```

To run the direct Bedrock script manually from the repo root:

```bash
python3 scripts/bedrock_direct_test.py --region us-east-1
```

Use `--prompt` to send a different test question:

```bash
python3 scripts/bedrock_direct_test.py \
  --region us-east-1 \
  --prompt "what is the square root of pi"
```

The script reads permitted model IDs from `terraform/aws-prep` and prompts for a model when run interactively. Set `BEDROCK_MODEL` when you want to skip the prompt:

```bash
export BEDROCK_MODEL="openai.gpt-oss-20b-1:0"
python3 scripts/bedrock_direct_test.py --region us-east-1
```

The script reads `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and optional `AWS_SESSION_TOKEN` from the environment. If the access key or secret key is missing and the script is run interactively, it prompts for the missing value. In non-interactive automation, missing credentials fail clearly.

If `terraform output -raw bedrock_secret_access_key` appears to end with `%` in an interactive zsh terminal, that `%` is zsh showing that the command did not print a trailing newline. It is not part of the secret. Command substitution in the `export` example above captures the secret value without that prompt marker. The Ansible playbook and direct script also trim surrounding whitespace from credential input before signing.

The direct model playbook sends `Hello, is this thing on? Reply in one short sentence and include the name of the model answering.` and summarizes the provider response. Set `direct_model_provider=ollama` to use the same playbook against the configured Ollama endpoint.

After the guard is configured, run:

```bash
cd ansible
ansible-playbook playbooks/test_fortiaigate_chat.yml
```

The playbook calls the repo-owned `scripts/fortiaigate_chat_test.py` script, sends a short test prompt to `https://<fortiaigate-public-ip>:443/v1/chat/completions`, asks the routed model to identify itself and repeat the URI under test, ignores the self-signed certificate with `curl -k`, and prints the received response in a readable format. The default model is the LiteLLM pass-through alias `pass-bedrock`.

By default the playbook checks one endpoint. To poll the default FAIG route
matrix, including static route paths, one intelligent route path, and the
default `/v1` fallback, run:

```bash
ansible-playbook playbooks/test_fortiaigate_chat.yml \
  -e fortiaigate_test_poll_all_endpoints=true
```

The shared extra var `-e poll_all_endpoints=true` is also supported by both the
FortiAIGate and LiteLLM direct test playbooks.

The default FAIG route matrix is seven endpoints: `passthrough`, `demo-a`,
`demo-b`, `demo-a-faig-be`, `demo-b-faig-be`, `intelligent`, and `default`.
`/v1/openwebui` and every intelligent-route profile can be included for
troubleshooting with `fortiaigate_test_include_openwebui_endpoint` or
`fortiaigate_test_include_all_header_route_profiles`.

The same test can be run directly from the repo root:

```bash
python3 scripts/fortiaigate_chat_test.py \
  --host 3.233.174.17 \
  --model openai.gpt-oss-20b-1:0 \
  --prompt "hello, this is a test. Reply in one short sentence and include the name of the model answering."
```

When `--host` is omitted, the script tries `terraform/aws-ec2-k3s` output `public_ip`. When `--model` is omitted, it prompts from `terraform/aws-prep` output `bedrock_model_ids` in interactive mode, or uses the first permitted model in non-interactive mode.

The script only sends an API key header when a key is provided. The default key source is `FAIG_API_KEY`, then `FORTIAIGATE_API_KEY`, then `FORTIAIGATE_TEST_API_KEY`. The default header name is `Authorization`, or set `AIG_HEADER` when the FortiAIGate AI Flow is configured with a custom authentication header:

```bash
export FAIG_API_KEY="<api-key>"
export AIG_HEADER="X-FAIG-Key"
python3 scripts/fortiaigate_chat_test.py --host 3.233.174.17
```

The same settings can be passed as arguments:

```bash
python3 scripts/fortiaigate_chat_test.py \
  --host 3.233.174.17 \
  --apikey "<api-key>" \
  --auth-header "X-FAIG-Key"
```

Additional headers can be added:

```bash
python3 scripts/fortiaigate_chat_test.py \
  --host 3.233.174.17 \
  --header "X-Test-Run: fresh-install" \
  --header "X-Trace-Source: local"
```

Use `--debug` to print the effective curl command before it runs. API key values are redacted by default:

```bash
FAIG_API_KEY="<api-key>" AIG_HEADER="X-FAIG-Key" \
python3 scripts/fortiaigate_chat_test.py --host 3.233.174.17 --debug
```

Only use `--debug-show-secrets` when you need an exact local copy/paste command and will not paste the output into logs or tickets.

## Cleanup

Destroy AWS infrastructure only when the FortiAIGate license lifecycle is understood for the test:

```bash
python3 scripts/automated_teardown.py
```

The teardown script backs up local config/state, removes ECR repositories from
Terraform state so they are not deleted, destroys ECR lifecycle/local output
resources, then destroys EC2 k3s and AWS prep.

Manual equivalent:

```bash
cd terraform/aws-ecr
terraform state rm 'aws_ecr_repository.this["api"]'
# repeat for each repository that should be retained
terraform destroy

cd ../aws-ec2-k3s
terraform destroy

cd ../aws-prep
terraform destroy
```

Private ECR repositories are managed separately in `terraform/aws-ecr` and
should not be destroyed unless image retention is no longer required.
