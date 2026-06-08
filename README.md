# FortiAIGate Demo Foundation

This repository provisions and deploys a FortiAIGate lab on AWS EC2 with k3s, NVIDIA GPU support, nginx ingress, ECR-hosted images, and an external Ollama-compatible backend.

Phase 1 is intentionally scoped to AWS infrastructure plus an Ansible-driven single-node k3s deployment. Local Ubuntu 24.04 GPU hardware follows the same Ansible roles later.

## Current Target

- Ubuntu 24.04 on AWS EC2
- `g4dn.xlarge` Terraform default for infrastructure smoke tests
- `g4dn.4xlarge` recommended for full FortiAIGate validation
- k3s with default Traefik disabled
- nginx ingress
- NVIDIA driver, container runtime, RuntimeClass, and device plugin
- k3s `local-path` storage with `ReadWriteOnce`
- FortiAIGate Helm chart supplied from an external read-only path
- External Ollama configured manually in FortiAIGate after install

## Prerequisites

- AWS CLI configured for IAM Identity Center / SSO
- Terraform
- Ansible
- SSH key pair already present in AWS
- Existing IAM instance profile with ECR read permission, such as a role containing `AmazonEC2ContainerRegistryReadOnly`
- FortiAIGate Helm chart available locally
- FortiAIGate license files available locally but outside this repo

Never commit real `terraform.tfvars`, Ansible secret vars, licenses, private keys, kubeconfigs, certificates, or API tokens.

## Workflow

```bash
cd terraform/aws-ec2-k3s
cp terraform.tfvars.example terraform.tfvars
aws sso login --profile <profile-name>
terraform init
terraform apply

cd ../../ansible
cp group_vars/all.example.yml group_vars/all.yml
ansible-playbook playbooks/bootstrap_gpu_k3s.yml
ansible-playbook playbooks/deploy_fortiaigate.yml
ansible-playbook playbooks/status_fortiaigate.yml
ansible-playbook playbooks/validate.yml
```

`terraform apply` writes `ansible/inventory/aws.generated.ini`. That generated inventory is ignored by Git.

Run `bootstrap_gpu_k3s.yml` before `deploy_fortiaigate.yml`. The deploy playbook expects `/etc/rancher/k3s/k3s.yaml` to exist on the target host.

Before deploying FortiAIGate, fill in the ignored `ansible/group_vars/all.yml` file with the ECR registry, image tag, chart path if different from the default, and license information. For a single-node lab, set `fortiaigate_license_files`; Ansible will map the first file to the discovered Kubernetes node name. Use `fortiaigate_licenses` only when you want to provide the exact node-to-license mapping yourself.

By default, `deploy_fortiaigate.yml` submits the Helm release and returns after Helm accepts the install or upgrade. It does not wait for every pod to become Ready. Use `status_fortiaigate.yml` to monitor pods, PVCs, ingress, Helm release state, and recent events. Set `fortiaigate_helm_wait: true` only when you want Helm to block until Kubernetes reports readiness.

After bootstrap, the SSH user has passwordless sudo, `/home/<user>/.kube/config`, and `KUBECONFIG=$HOME/.kube/config` in `.profile` and `.bashrc`, so interactive `kubectl` works without `sudo` on the k3s host. Open a new SSH session or run `source ~/.profile` after bootstrap.

Bootstrap waits for k3s system deployments (`coredns`, `local-path-provisioner`, and `metrics-server`) before continuing. On a fresh host this can take a few minutes while images pull and flannel/API networking settles. Tune `k3s_system_rollout_timeout` in `ansible/group_vars/all.yml` if needed.

The deploy playbook stages the chart on the remote host under `/home/<user>/tmp/fortiaigate-chart` by default. The staged chart, rendered values file, and post-renderer are left there after deployment for review.

## External Ollama

The Helm chart inspected for FortiAIGate 8.0.0 exposes only the upstream LLM timeout in values. It does not expose a provider bootstrap value for Ollama. For phase 1, configure the provider in the FortiAIGate UI or supported API after the deployment:

```text
Provider: OpenAI-compatible
Base URL: http://<ollama-host>:11434/v1
Model:    llama3.2:1b
API key:  blank or a dummy value if required
```

The Ansible validation variables include the same endpoint and model so the final validation can exercise `/v1/chat/completions` once the provider exists.
