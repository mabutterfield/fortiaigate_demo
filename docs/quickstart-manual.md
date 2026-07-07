# Manual Quick Start

This is the step-by-step manual deployment path for the FortiAIGate demo. Run these commands from the `fortiaigate_demo` repo root unless a step explicitly says otherwise.

## Prerequisites

- Workstation with a POSIX-style shell. macOS and Linux are tested. Windows users should use WSL2; native Windows may work for some tools but is not a supported/tested control-node path.
- AWS CLI configured for your AWS authentication method, such as IAM Identity Center / SSO
- Terraform, Ansible, Docker, Python 3, and SSH available on your workstation
- Docker must be usable by the current workstation user without `sudo`
- SSH key pair already present in AWS
- Existing EC2 IAM instance profile, or allow `terraform/aws-ec2-k3s` to create one
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
credentials for the first FortiAIGate guard/provider.
When `registry_backend = "ecr"`, it reads repository ARNs from the ECR
Terraform state configured by `aws_ecr_state_path`.

Save the Bedrock provider values for later FortiAIGate GUI setup:

```bash
terraform -chdir=terraform/aws-prep output bedrock_access_key_id
terraform -chdir=terraform/aws-prep output -raw bedrock_secret_access_key
terraform -chdir=terraform/aws-prep output bedrock_allowed_regions
terraform -chdir=terraform/aws-prep output bedrock_model_ids
```

Store these values somewhere safe for the initial FortiAIGate guard/provider
configuration. The secret access key is sensitive and is only shown because the
GUI setup currently requires it.

### Terraform 4 - EC2 k3s Foundation

Create the EC2 k3s variables once. Edit the copied file before running
Terraform. Subsequent runs reuse this file.

```bash
cp terraform/aws-ec2-k3s/terraform.tfvars.example terraform/aws-ec2-k3s/terraform.tfvars
```

Set `ssh_key_name`, `ssh_private_key_file`, `instance_type`, and network CIDRs
in `terraform/aws-ec2-k3s/terraform.tfvars`.

Deploy the k3s host and AWS network foundation:

```bash
terraform -chdir=terraform/aws-ec2-k3s init
terraform -chdir=terraform/aws-ec2-k3s apply
```

Minimum `terraform/aws-ec2-k3s/terraform.tfvars` values to review:

- `aws_prep_state_path`
- `ssh_key_name` and `ssh_private_key_file`
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
image used by the consolidated chatbot UI. Because ECR repositories are
immutable by default, bump `chatbot_image_tag` in `ansible/group_vars/all.yml`
before republishing changed chatbot code.

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
`UI -> FortiAIGate /v1 -> LiteLLM -> Bedrock` after FortiAIGate is manually
configured to use LiteLLM as its upstream provider.

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

The default LiteLLM Admin/API URL is:

- `http://<k3s-public-ip>:30083/ui/`

Backend demo instructions are mounted into LiteLLM and injected by the custom
pre-call hook, not by Open WebUI or the custom chatbot frontend.

### Ansible 5 - Deploy Open WebUI

Deploy the consolidated Open WebUI front end:

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

The chatbot has a runtime selector for `Direct LiteLLM` versus `FortiAIGate`.
Both paths use the same LiteLLM model/profile alias. Backend demo instructions
are injected by LiteLLM so FortiAIGate can inspect the user-visible request
before those backend-only demo instructions are added.

Check readiness separately:

```bash
ansible-playbook ansible/playbooks/status_chatbots.yml
```

Use the validation playbook when you want a failing gate:

```bash
ansible-playbook ansible/playbooks/validate_chatbots.yml
```

### Ansible 7 - Deploy Demo Home Page

Deploy a small home page with links to FortiAIGate, LiteLLM Admin UI, Open
WebUI, and chatbot test pages:

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
OpenWebUI `30080`, chatbot `30081`, demo home `30082`, and LiteLLM Admin/API
`30083`.

### Optional - Deploy HTTPS Gateway

HTTP remains the primary demo access path. To add optional HTTPS listeners for
OpenWebUI, the chatbot front end, demo home, and LiteLLM Admin/API, set
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
OpenWebUI `30443` proxies `30080`, chatbot `30444` proxies `30081`, demo home
`30445` proxies `30082`, and LiteLLM Admin/API `30446` proxies `30083`.

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

## Bedrock First Guard

Use this section when Bedrock is the first LLM provider for the FortiAIGate
guard. After `status_fortiaigate.yml` reports `READY`, use the printed HTTPS
login URL to sign in to FortiAIGate and change the default password.

Temporary Bedrock credentials are created by `terraform/aws-prep` when
`enable_bedrock_iam = true`. Retrieve the GUI values from the repo root:

```bash
terraform -chdir=terraform/aws-prep output bedrock_access_key_id
terraform -chdir=terraform/aws-prep output -raw bedrock_secret_access_key
terraform -chdir=terraform/aws-prep output bedrock_model_ids
terraform -chdir=terraform/aws-prep output bedrock_allowed_regions
```

In FortiAIGate, create the first Bedrock-backed guard/provider with:

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

The playbook uses `scripts/fortiaigate_chat_test.py` to send a short test prompt through `https://<fortiaigate-public-ip>:443/v1/chat/completions`, asks the routed model to identify itself, and summarizes the HTTP status and response.
