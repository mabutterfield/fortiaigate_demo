# Deployment Runbook

This runbook describes the normal AWS lab deployment workflow.

Unless noted otherwise, command blocks start from the `fortiaigate_demo` repo root.

## 1. Prepare Local Inputs

Required local inputs are intentionally ignored by Git:

- `terraform/aws-ecr/terraform.tfvars`
- `terraform/aws-bedrock/terraform.tfvars`
- `terraform/aws-ec2-k3s/terraform.tfvars`
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

## 3. Create ECR Repositories

```bash
cd terraform/aws-ecr
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

## 4. Publish Images

```bash
cd ansible
cp group_vars/images.example.yml group_vars/images.yml
ansible-playbook playbooks/publish_images.yml
```

The image publisher loads release archives locally with Docker, preserves the tags embedded in the archives, and pushes to the configured registry.

To publish one version:

```bash
ansible-playbook playbooks/publish_images.yml -e publish_image_version=8.0.0
```

To publish all active builds, set `state: active` in `group_vars/images.yml` and run the playbook without overrides.

## 5. Deploy AWS Infrastructure

```bash
cd terraform/aws-ec2-k3s
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

- `aws_profile`
- `aws_region`
- `ssh_key_name`
- `ssh_private_key_file` when the AWS key pair does not use your default SSH key
- `allowed_ingress_cidr`
- `iam_instance_profile_name`, or `create_iam_instance_profile = true`
- `instance_type` when changing from the default `g4dn.4xlarge`

If the EC2 key pair uses a non-default SSH key, set `ssh_private_key_file` in `terraform.tfvars`. Terraform includes that key in the generated Ansible inventory and in the `ssh_command` output.

Validate AWS instance status and SSH before running Ansible:

```bash
terraform output ssh_command
aws ec2 describe-instance-status \
  --profile <profile-name> \
  --region <region> \
  --instance-ids "$(terraform output -raw instance_id)" \
  --include-all-instances \
  --query 'InstanceStatuses[0].{Instance:InstanceState.Name,System:SystemStatus.Status,InstanceStatus:InstanceStatus.Status}' \
  --output table
```

Run the `ssh_command` output. If SSH does not work, fix AWS networking, the key pair, or `ssh_private_key_file` before starting Ansible.

The AWS and k3s networks must not overlap. The default phase 1 layout is:

```yaml
vpc_cidr: 10.20.0.0/16
public_subnet_cidr: 10.20.1.0/24
k3s_cluster_cidr: 10.60.0.0/16
k3s_service_cidr: 10.70.0.0/16
k3s_cluster_dns: 10.70.0.10
```

Terraform passes these k3s values into the generated Ansible inventory. Override them in `terraform.tfvars` before creating the host when your environment already uses one of these ranges.

## 6. Prepare Bedrock Access

Run this after EC2 exists because the Bedrock module reads `terraform/aws-ec2-k3s/terraform.tfstate` for source-IP restrictions.

```bash
cd terraform/aws-bedrock
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt
terraform validate
terraform apply
```

Set `bedrock_model_ids` after choosing models and confirming model access in the AWS account/region. Use exact Bedrock model IDs, for example `openai.gpt-oss-20b-1:0`, not short display names. Set `bedrock_allowed_regions` to the commercial US regions where those models should be invokable. Terraform creates temporary IAM user credentials for manual FortiAIGate GUI entry.

By default, Bedrock restricts credentials to the k3s EIP plus `allowed_ingress_cidr`. Set `no_ip_restriction = true` only when the key should work from any source IP.

Retrieve the values after apply:

```bash
terraform output bedrock_access_key_id
terraform output -raw bedrock_secret_access_key
terraform output bedrock_key_expires_at
terraform output bedrock_region
```

The secret access key is stored in Terraform state. Do not commit state or real `terraform.tfvars`.

## 7. Configure Deployment Variables

```bash
cd ansible
cp group_vars/all.example.yml group_vars/all.yml
```

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

Minimum `group_vars/all.yml` values to review:

- `fortiaigate_version` and the matching image tags
- `faig_workspace_root` only when the repo is not under the default parent `FAIG` directory
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
- all pods are Running/Ready or Succeeded
- DNS resolution from inside a temporary pod works

Rerun the same checks independently with:

```bash
ansible-playbook playbooks/validate_k3s.yml
```

## 9. Deploy FortiAIGate

```bash
ansible-playbook playbooks/deploy_fortiaigate.yml
```

The deploy playbook:

- creates or refreshes the ECR pull secret
- copies the extracted chart to the remote host
- stages licenses into the temporary remote chart copy
- renders values
- runs Helm with the FortiAIGate post-renderer

By default Helm does not wait for every Kubernetes workload to become Ready. This keeps the install command responsive and leaves status monitoring to the next step.

## 10. Monitor Status

```bash
ansible-playbook playbooks/status_fortiaigate.yml
```

This is the lightweight readiness check. It reports one of:

- `READY`: Helm is reachable and all FortiAIGate pods are Ready
- `NOT READY`: Kubernetes is reachable but at least one FortiAIGate pod is not Ready
- `ERROR`: Helm or Kubernetes status commands failed

It also prints the HTTPS login URL. The URL uses `fortiaigate_ingress_host` when set, otherwise the generated inventory `public_ip`, otherwise `ansible_host`.

Useful manual commands on the k3s host:

```bash
helm status fortiaigate -n fortiaigate
kubectl get pods -A
kubectl get pvc -n fortiaigate
kubectl get events -n fortiaigate --sort-by=.lastTimestamp
```

## 11. Validate

```bash
ansible-playbook playbooks/validate_faig.yml
```

Validation checks the host, Kubernetes, GPU visibility, ingress, and FortiAIGate service reachability.

Use validation after status is `READY` or when you need deeper checks. It validates GPU visibility, Triton device access, `/dev/shm`, UI/API HTTP behavior, and optional provider forwarding.

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

## Cleanup

Destroy AWS infrastructure only when the FortiAIGate license lifecycle is understood for the test:

```bash
cd terraform/aws-ec2-k3s
terraform destroy
```

Private ECR repositories are managed separately in `terraform/aws-ecr` and should not be destroyed unless image retention is no longer required.
