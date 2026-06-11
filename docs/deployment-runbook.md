# Deployment Runbook

This runbook describes the normal AWS lab deployment workflow.

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
    FAIG_helm_chart-V8.0.0-build0024-FORTINET.tar.gz
    fortiaigate/
      Chart.yaml
  8.0.1/
    FAIG_helm_chart-V8.0.1-build0031-FORTINET.tar.gz
    fortiaigate/
      Chart.yaml
```

The deployment role expects `fortiaigate_chart_path` to point at the extracted chart directory, not the vendor `.tgz` file.

## 2. Authenticate to AWS

```bash
aws sso login --profile <profile-name>
```

Use the same profile in Terraform and Ansible variables.

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

## 4. Prepare Bedrock Access

```bash
cd terraform/aws-bedrock
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt
terraform validate
terraform apply
```

Set `bedrock_model_ids` after choosing models and confirming model access in the AWS account/region. Use exact Bedrock model IDs, for example `openai.gpt-oss-20b-1:0`, not short display names. Set `bedrock_allowed_regions` to the commercial US regions where those models should be invokable. Terraform creates temporary IAM user credentials for manual FortiAIGate GUI entry.

After the EC2 host exists, Bedrock reads `terraform/aws-ec2-k3s/terraform.tfstate` and restricts credentials to the k3s EIP plus `allowed_ingress_cidr`. Set `no_ip_restriction = true` only when the key should work from any source IP.

Retrieve the values after apply:

```bash
terraform output bedrock_access_key_id
terraform output -raw bedrock_secret_access_key
terraform output bedrock_key_expires_at
terraform output bedrock_region
```

The secret access key is stored in Terraform state. Do not commit state or real `terraform.tfvars`.

## 5. Publish Images

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

## 6. Deploy AWS Infrastructure

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

If the EC2 key pair uses a non-default SSH key, set `ssh_private_key_file` in `terraform.tfvars`. Terraform includes that key in the generated Ansible inventory and in the `ssh_command` output.

The AWS and k3s networks must not overlap. The default phase 1 layout is:

```yaml
vpc_cidr: 10.20.0.0/16
public_subnet_cidr: 10.20.1.0/24
k3s_cluster_cidr: 10.60.0.0/16
k3s_service_cidr: 10.70.0.0/16
k3s_cluster_dns: 10.70.0.10
```

Terraform passes these k3s values into the generated Ansible inventory. Override them in `terraform.tfvars` before creating the host when your environment already uses one of these ranges.

## 7. Configure Deployment Variables

```bash
cd ansible
cp group_vars/all.example.yml group_vars/all.yml
```

For FortiAIGate 8.0.0:

```yaml
fortiaigate_version: "8.0.0"
fortiaigate_chart_path: "/path/to/FAIG_helm/{{ fortiaigate_version }}/fortiaigate"
fortiaigate_image_tag: "V8.0.0-build0024"
fortiaigate_triton_model_image_tag: "0.1.4"
fortiaigate_triton_image_tag: "25.11-onnx-trt-agt"
```

For FortiAIGate 8.0.1:

```yaml
fortiaigate_version: "8.0.1"
fortiaigate_chart_path: "/path/to/FAIG_helm/{{ fortiaigate_version }}/fortiaigate"
fortiaigate_image_tag: "V8.0.1-build0031"
fortiaigate_triton_model_image_tag: "0.1.6-s1"
fortiaigate_triton_image_tag: "25.11-onnx-trt-agt-s1"
```

For single-node labs, set:

```yaml
license_source_dir: /path/to/licenses/fortiaigate
fortiaigate_license_files:
  - License1.lic
fortiaigate_licenses: {}
```

Ansible maps the first license file to the discovered Kubernetes node name. Use `fortiaigate_licenses` only when an exact node-to-license mapping is required.

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

This reports Helm release state, pods, PVCs, ingress, and recent events.

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
