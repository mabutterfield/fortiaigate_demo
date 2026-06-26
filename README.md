# FortiAIGate Lab Deployment

Infrastructure-as-code for deploying a FortiAIGate lab on AWS GPU instances and, where practical, local Ubuntu GPU hosts.

This repository provides a repeatable deployment process using:

- Terraform for AWS infrastructure and private ECR repositories
- Ansible for image publishing, host bootstrap, Kubernetes setup, and deployment
- k3s for single-node Kubernetes orchestration
- Helm plus a post-renderer for FortiAIGate deployment
- Amazon ECR or a local registry for FortiAIGate container images

## Goals

- Deploy FortiAIGate consistently with minimal manual steps
- Support AWS EC2 GPU labs first, then local Ubuntu 24.04 GPU hosts
- Keep FortiAIGate charts and release images outside this repo
- Publish release images to private ECR with immutable tags
- Keep secrets, licenses, kubeconfigs, and generated values out of Git
- Preserve a path for Ollama, Bedrock, and other provider integrations

## Current Status

- AWS EC2 single-node k3s deployment is implemented
- NVIDIA driver, container runtime, RuntimeClass, and device plugin are automated
- nginx ingress replaces the default k3s Traefik path
- Private ECR repository creation and image publishing are implemented
- FortiAIGate Helm deployment uses external release charts and post-render patches
- FortiAIGate 8.0.0 and 8.0.1 image/chart version patterns are documented

## To-Do

- Add a first-class local Ubuntu GPU host workflow
- Expand Terraform support for using existing AWS resources without import friction
- Move Terraform state to a remote backend when the workflow leaves phase 1
- Automate FortiAIGate provider setup when a supported API is identified
- Add more deployment validation around FortiAIGate application readiness
- Add cleanup and recovery runbooks for failed Helm releases and license resets

## Repository Layout

```text
terraform/      AWS infrastructure modules
ansible/        Image publishing, host bootstrap, deploy, status, and validation playbooks
helm-values/    Example FortiAIGate Helm values
k8s-overlays/   Helm post-renderer and patch notes
docs/           Deployment, ECR, Terraform, and architecture documentation
scripts/        Operational helper and smoke-test scripts for Bedrock and FortiAIGate chat APIs
```

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

- `terraform/aws-ecr/terraform.tfvars`
- `terraform/aws-bedrock/terraform.tfvars`, when using Bedrock
- `terraform/aws-ec2-k3s/terraform.tfvars`
- `ansible/group_vars/images.yml`
- `ansible/group_vars/all.yml`

Never commit real `terraform.tfvars`, Ansible secret vars, license files, private keys, kubeconfigs, certificates, API tokens, or generated credentials.

## Quick Start

Authenticate to AWS:

```bash
# Use the login command required by your AWS profile.
# IAM Identity Center / SSO profiles normally use:
aws sso login --profile <profile-name>
# Add --use-device-code when your environment requires device-code login.
```

For non-SSO profiles, use your normal AWS login flow; the workflow only
requires that `aws sts get-caller-identity --profile <profile-name>` succeeds.

### ECR Repositories And Pull Permissions

Create or import private ECR repositories:

```bash
cd terraform/aws-ecr
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars before terraform init.
# Set non-secret values such as aws_profile, aws_region, repo_prefix, and
# optional ec2_pull_role_name. Do not put secrets or access keys in this file.
terraform init
terraform apply
```

The ECR module can attach scoped ECR pull permissions to an EC2 IAM role when
`ec2_pull_role_name` is set. If the k3s EC2 role is created later by
`terraform/aws-ec2-k3s`, rerun this module after the EC2 module is applied and
set `ec2_pull_role_name` to the `terraform output -raw iam_role_name` value.
Review [docs/ECR.md](docs/ECR.md) for the IAM role and ECR pull-permission
workflow.

If ECR repositories already exist, either import them into `terraform/aws-ecr` or configure the registry values manually in Ansible. See [docs/ECR.md](docs/ECR.md).

Publish FortiAIGate release images:

```bash
cd ../../ansible
cp group_vars/images.example.yml group_vars/images.yml
ansible-playbook playbooks/publish_images.yml
```

Image publishing currently reads release archive metadata, loads only missing
or changed source images into the local Docker image store, tags the local
images, and pushes them to ECR. Keep at least 2x-3x the total release image
archive size available on the local Docker disk before running the publish
playbook.

### Deploy AWS Infrastructure

Deploy AWS infrastructure:

```bash
cd ../terraform/aws-ec2-k3s
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars before terraform init.
# Set non-secret values such as aws_profile, ssh_key_name,
# ssh_private_key_file, allowed_ingress_cidr, and IAM profile settings.
# Do not put secrets or access keys in this file.
terraform init
terraform apply
```

Minimum `terraform/aws-ec2-k3s/terraform.tfvars` values to review:

- `aws_profile` and `aws_region`
- `ssh_key_name` and `ssh_private_key_file`
- `allowed_ingress_cidr` as a valid CIDR, such as `<your-public-ip>/32`
- `iam_instance_profile_name`, or `create_iam_instance_profile = true`
- `instance_type` if the default `g4dn.4xlarge` is not the target size

Optionally validate the instance from the CLI:

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

Run the `ssh_command` output before starting Ansible. If SSH does not work, Ansible will not work.

### Configure k3s And FortiAIGate

Configure deployment variables:

```bash
cd ../../ansible
cp group_vars/all.example.yml group_vars/all.yml
```

Set local values in `group_vars/all.yml`, especially:

- AWS profile/region/account values when not supplied by generated vars
- `fortiaigate_version`
- `faig_workspace_root` when your `FAIG` workspace is not the parent of this repo
- license file list under the default `FAIG/licenses`, or a custom `license_source_dir`
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

Bootstrap k3s and deploy FortiAIGate:

```bash
ansible-playbook playbooks/bootstrap_gpu_k3s.yml
ansible-playbook playbooks/validate_k3s.yml
ansible-playbook playbooks/deploy_fortiaigate.yml
```

Helm deploys the FortiAIGate release asynchronously. The deploy playbook returns
after Helm accepts the install or upgrade; Kubernetes may still be pulling
images, starting pods, binding storage, and activating FortiAIGate services.
Use the status playbook to monitor readiness and get the login URL:

```bash
ansible-playbook playbooks/status_fortiaigate.yml
```

FortiAIGate 8.0.1 serves the web UI under `/ui/`; `/` is preserved for the
chart's core service route. The status and validation playbooks use
`fortiaigate_ui_path` to print and check the right UI URL for the selected
version.

Rerun `status_fortiaigate.yml` until it reports `FortiAIGate status: READY`,
then run the deeper validation checks:

```bash
ansible-playbook playbooks/validate_faig.yml
```

For the first GUI login, AI flow, guard, deploy, and lab API-key settings, see
[docs/FortiAIGate-initial-config.MD](docs/FortiAIGate-initial-config.MD).

The default network layout avoids overlap between the AWS VPC and k3s internals: AWS VPC `10.20.0.0/16`, k3s pods `10.60.0.0/16`, and k3s services `10.70.0.0/16`. Override these in `terraform/aws-ec2-k3s/terraform.tfvars` before creating the host if they conflict with your environment.

## Documentation

| Document | Purpose |
|---|---|
| [docs/README.md](docs/README.md) | Documentation index |
| [docs/deployment-runbook.md](docs/deployment-runbook.md) | End-to-end deployment workflow |
| [docs/FortiAIGate-initial-config.MD](docs/FortiAIGate-initial-config.MD) | First GUI login, flow, guard, and lab API-key setup |
| [docs/ECR.md](docs/ECR.md) | ECR repository and image publishing workflow |
| [docs/Bedrock.md](docs/Bedrock.md) | Temporary Bedrock IAM credentials for manual provider setup |
| [docs/terraform.md](docs/terraform.md) | Terraform module usage and import notes |
| [docs/aws-k3s-foundation.md](docs/aws-k3s-foundation.md) | AWS k3s architecture and implementation notes |
| [k8s-overlays/fortiaigate/README.md](k8s-overlays/fortiaigate/README.md) | Helm post-render patch behavior |

## Operating Notes

Run `bootstrap_gpu_k3s.yml` before `deploy_fortiaigate.yml`. The deploy playbook expects `/etc/rancher/k3s/k3s.yaml` to exist on the target host.

Bootstrap runs the same k3s foundation checks as `validate_k3s.yml` before it completes. The standalone playbook is useful after rebuilds, network changes, or manual troubleshooting. A successful run prints `K3s status: GO`; the standalone validation playbook prints `K3s status: NO GO` with the failed check before exiting on validation failure.

`terraform/aws-ec2-k3s` writes `ansible/inventory/aws.generated.ini`. `terraform/aws-ecr` writes `ansible/group_vars/ecr.generated.yml`. Both generated files are ignored by Git.

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

Then create temporary Bedrock credentials from the repo root:

```bash
cd terraform/aws-bedrock
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars before terraform init.
# Set non-secret values such as aws_profile, aws_region, bedrock_model_ids,
# bedrock_allowed_regions, and source IP settings.
terraform init
terraform apply
terraform output bedrock_access_key_id
terraform output -raw bedrock_secret_access_key
terraform output bedrock_model_ids
terraform output bedrock_allowed_regions
```

In FortiAIGate, create the first Bedrock-backed guard/provider with:

- Access Key ID from `terraform output bedrock_access_key_id`
- Secret Access Key from `terraform output -raw bedrock_secret_access_key`
- Region from the permitted `bedrock_allowed_regions`
- Model ID from the permitted `bedrock_model_ids`

To test Bedrock directly before configuring the FortiAIGate guard:

```bash
cd ansible
ansible-playbook playbooks/test_model_direct.yml
```

The Bedrock direct test uses `scripts/bedrock_direct_test.py` to generate the AWS SigV4 signature at runtime. Run that script directly from the repo root when you want a local-only Bedrock smoke test; it prompts from the permitted Terraform model list unless `BEDROCK_MODEL` is set.

Set `direct_model_provider=ollama` to use the same playbook for direct Ollama testing.

After the guard is configured, generate and run the first external chat test:

```bash
cd ansible
ansible-playbook playbooks/test_fortiaigate_chat.yml
```

The playbook uses `scripts/fortiaigate_chat_test.py` to send a short test prompt through `https://<fortiaigate-public-ip>:443/v1/chat/completions`, asks the routed model to identify itself, and summarizes the HTTP status and response.
