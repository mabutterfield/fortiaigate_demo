# AWS k3s Foundation

## Scope

The current AWS foundation creates a single-node FortiAIGate lab:

- new AWS VPC
- public and private k3s subnets
- FortiGate and FortiWeb public placeholder subnets
- internet gateway and public route table
- security group for SSH, HTTP, and HTTPS
- Ubuntu 24.04 GPU EC2 instance
- Elastic IP
- k3s with Traefik disabled
- nginx ingress controller
- NVIDIA driver, runtime, RuntimeClass, and device plugin
- k3s local-path storage backed by instance-store NVMe when available
- FortiAIGate deployed with Helm and a post-renderer

`terraform/aws-prep` creates the EC2 IAM role/profile and attaches scoped ECR
pull access when `registry_backend = "ecr"`. The EC2 module consumes the prep
state and attaches the prepared instance profile to the k3s host.

See [VPC Layout](vpc-layout.md) for the visual network layout, including the
current public k3s path and future private/appliance paths.

## Network CIDRs

AWS VPC, k3s pod, and k3s service networks must not overlap. The defaults intentionally stay in `10.x` space with second octets between 20 and 90:

| Network | Default |
|---|---|
| AWS VPC | `10.20.0.0/16` |
| AWS k3s public subnet | `10.20.1.0/24` |
| AWS k3s private subnet | `10.20.2.0/24` |
| AWS FortiGate public subnet | `10.20.10.0/24` |
| AWS FortiWeb public subnet | `10.20.11.0/24` |
| k3s pod network | `10.60.0.0/16` |
| k3s service network | `10.70.0.0/16` |
| k3s cluster DNS | `10.70.0.10` |

Terraform passes the k3s values into the generated Ansible inventory. The k3s role then writes them into `/etc/rancher/k3s/config.yaml` as `cluster-cidr`, `service-cidr`, and `cluster-dns`.

`k3s_subnet_mode = "public"` is the default and preserves direct SSH/HTTP/HTTPS access through the prep-owned k3s Elastic IP. The k3s host does not request an auto-assigned ephemeral public IP. `k3s_subnet_mode = "private"` places the k3s host in the private subnet without a public IP; use private mode only after a private management path or FortiGate/FortiWeb appliance-fronted path exists.

The k3s role validates that the k3s networks do not overlap with each other or with the AWS networks supplied by inventory. Change these values before cluster creation; changing k3s network CIDRs on an existing cluster requires a rebuild.

## Terraform Output

`terraform/aws-ec2-k3s` writes:

```text
ansible/inventory/aws.generated.ini
```

The generated inventory is ignored by Git and used by the Ansible playbooks.

## Host Bootstrap

`ansible/playbooks/bootstrap_gpu_k3s.yml` prepares the host in this order:

1. common Ubuntu packages
2. NVIDIA driver
3. NVIDIA container runtime
4. k3s with Traefik disabled
5. instance-store local-path storage setup
6. nginx ingress
7. NVIDIA RuntimeClass and device plugin
8. k3s cluster sanity validation

The k3s role waits for flannel before checking system deployments. `metrics-server` is handled separately because it can start before service networking is fully ready on a fresh host.

Bootstrap also runs `validate_k3s` as a final gate. The validation checks Kubernetes API reachability, node readiness, kube-system and ingress-nginx deployments, NVIDIA device plugin rollout, all pod health, and DNS resolution from inside a temporary pod.

After bootstrap, the SSH user has:

- passwordless sudo
- `/home/<user>/.kube/config`
- shell profile configuration for `KUBECONFIG=$HOME/.kube/config`

Open a new SSH session before testing interactive `kubectl`.

## Storage

When instance-store NVMe is available, Ansible formats and mounts it under `k3s_instance_store_mount`, then uses it for k3s data through `k3s_data_dir`.

The default FortiAIGate storage path is:

```yaml
k3s_data_dir: /var/lib/rancher
k3s_local_storage_dir: "{{ k3s_data_dir }}/k3s/storage"
fortiaigate_storage_class: local-path
fortiaigate_storage_access_modes:
  - ReadWriteOnce
```

On non-AWS hosts or hosts without instance-store NVMe, Ansible still creates the local-path storage directory.

## Helm Chart Handling

The FortiAIGate chart is not vendored into this repo. Store release charts outside the repo as:

```text
FAIG_helm/<version>/fortiaigate
```

Set:

```yaml
faig_workspace_root: "{{ lookup('env', 'FAIG_WORKSPACE_ROOT') | default((playbook_dir + '/../../..') | realpath, true) }}"
fortiaigate_chart_path: "{{ faig_workspace_root }}/FAIG_helm/{{ fortiaigate_version }}/fortiaigate"
```

Override `FAIG_WORKSPACE_ROOT` when the parent workspace is not the default parent directory of this repo. Use an absolute path, not `~`.

Ansible copies the extracted chart to the remote host under `fortiaigate_chart_remote_root`, stages licenses into that temporary copy, renders values, and runs Helm with the post-renderer.

The remote staged chart is intentionally left behind for review.

TLS defaults to the chart-bundled `files/certificate/dflt.crt` and `files/certificate/dflt.key`. Override `fortiaigate_ssl_cert_path` and `fortiaigate_ssl_key_path` in `ansible/group_vars/user.yml` to stage private certificate material from outside the repo.

## Helm Wait Behavior

By default:

```yaml
fortiaigate_helm_wait: false
```

This means the deploy playbook returns once Helm accepts the install or upgrade. Use `status_fortiaigate.yml` to monitor application readiness.

Set `fortiaigate_helm_wait: true` only when you want Helm to block until Kubernetes reports readiness.

## External Ollama

The chart currently does not expose a provider bootstrap value for Ollama. Configure the OpenAI-compatible provider in the FortiAIGate UI or a supported API after deployment.

Use these Ansible vars for validation once the provider exists:

```yaml
ollama_base_url: http://<ollama-host>:11434/v1
ollama_model: llama3.2:1b
validate_faig_ollama_forwarding: true
```

## Required Local Inputs

- `terraform/aws-ec2-k3s/terraform.tfvars`
- `ansible/group_vars/system.yml`
- `ansible/group_vars/user.yml`
- license files in `FAIG/licenses` by default, or another `license_source_dir`
- FortiAIGate chart under `FAIG_helm/<version>/fortiaigate`
- AWS SSO session before Terraform and ECR operations

All of these are environment-specific and must remain out of Git.
