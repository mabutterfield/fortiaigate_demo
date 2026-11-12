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
- k3s local-path volumes on encrypted root EBS (300 GiB by default)
- on fresh AWS hosts, container image cache on a instance-store NVMe disk without detected signatures

The 8.0.2 application path is under live development; see
[FortiAIGate 8.0.2 Deployment](fortiaigate-802-deployment.md).

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

Use the staged workflow below; the automated quickstart still continues into the
8.0.1 application deployment and must not be used for the 8.0.2 test.

1. Set up the AWS SSO profile and operator-owned `terraform/user.tfvars` and
   `ansible/group_vars/user.yml` using `scripts/user_profile.py`. Review existing
   values; they take precedence over the tracked defaults.
2. Reconcile the existing ECR repositories into `terraform/aws-ecr` state before
   applying that module. Do not create duplicate repositories or destroy retained
   images. Review `terraform/aws-prep` state too; it reads ECR state and provides
   the instance profile and EIP. Disable optional appliance resources in its
   ignored overrides. Review each Terraform plan before applying it.
3. Initialize and apply the approved AWS prep and `terraform/aws-ec2-k3s`
   modules, in that order. Set `instance_type` and `availability_zone` in an
   ignored module override; an offered AZ is not a capacity guarantee. Set
   `ubuntu_ami_id` to a tested Ubuntu 24.04 amd64 AMI if reproducibility is needed.
   Defaults are `g6.4xlarge` (L4 development-only), 300 GiB root EBS and a
   guarded instance-store image cache. The
   exact 8.0.2 storage requirement has not yet been measured. Check instance
   and EBS costs, quotas and SSH CIDRs before applying.
4. Use the generated `ansible/inventory/aws.generated.ini` to run only:

   ```bash
   ansible-playbook -i ansible/inventory/aws.generated.ini ansible/playbooks/bootstrap_gpu_k3s.yml
   ```

   This installs common packages, the NVIDIA driver, k3s, NVIDIA runtime and
   device plugin, ingress, and validates the foundation. Set
   `nvidia_expected_gpu_count` in the ignored user vars to match the host (for
   example, `2` for `g7e.12xlarge`). Existing user overrides are never changed.
5. Confirm the GPU model, version output, free disk and pod logs. Reboot the host
   and rerun the playbook to verify runtime persistence and idempotence. Confirm
   ECR image pulls through the instance role separately after uploads finish.
   The GPU and storage tests create and clean up an isolated namespace; public
   images must be reachable. Do not install the FortiAIGate chart at this stage.

The initial candidate pin is k3s `v1.35.10+k3s1`; the Ubuntu NVIDIA 595-server
driver, NVIDIA toolkit, GPU test image and full combination remain unverified on
a live 8.0.2 host. The pinned ingress-nginx 4.15.1 chart is **retired upstream**:
use it only for an isolated, trusted-source lab while an actively maintained
replacement is evaluated before application exposure. The existing Helm
installer and NVIDIA toolkit package versions are not pinned yet.

After bootstrap, the SSH user has:

- passwordless sudo
- `/home/<user>/.kube/config`
- shell profile configuration for `KUBECONFIG=$HOME/.kube/config`

Open a new SSH session before testing interactive `kubectl`.

## Storage

On a fresh AWS host the default `k3s_use_instance_store: true` selects a whole
NVMe disk whose model is `Amazon EC2 NVMe Instance Storage`. It refuses EBS and
root devices, partitions, ambiguous choices, mounted disks, pre-existing disk
signatures, a populated mountpoint, and an existing containerd directory. It
formats a disk without detected signatures as ext4 and uses it for the k3s containerd image
cache only. It never automatically migrates an existing deployment. When
multiple instance-store disks exist, explicitly choose one using
`k3s_instance_store_device`. Set `k3s_use_instance_store: false` in ignored
user vars for an EBS-only deployment. The original 8.0.2 test host was created
before this change and is EBS-only; do not rerun bootstrap with instance-store
enabled on that host.

Signature checks do not detect arbitrary raw data, so use this automatic path
only for a new host whose instance store can be erased.

The cache is ephemeral and is lost on an EC2 stop or termination. A systemd
mount condition prevents k3s from silently using root EBS if its image cache is
not mounted. After instance-store loss the old fstab UUID must be reconciled
and the new disk verified before k3s starts; this recovery is not automatic.
Pre-pull the images again after recovery. The format-and-mount path and idempotent rerun were validated on a fresh AWS
L4 host. Recovery after instance-store loss has not yet been tested.

Local-path PVCs and k3s cluster state remain on root EBS, which survives EC2
stop but can be deleted with instance termination or Terraform destroy. Size it
for application data, model copies, logs and headroom. The 300 GiB default is
provisional; the first L4 test used approximately 108 GiB after image pulls.

## Helm Chart Handling (8.0.1; Not Yet Ported)

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

Advanced users can set these Ansible vars manually for validation once the
provider exists:

```yaml
# ollama_base_url: http://<ollama-host>:11434/v1
# ollama_model: gpt-oss:20b
# validate_faig_ollama_forwarding: true
```

## Required Local Inputs

- `terraform/aws-ec2-k3s/99-local.auto.tfvars`
- `ansible/group_vars/system.yml`
- `ansible/group_vars/user.yml`
- license files in `FAIG/licenses` by default, or another `license_source_dir`
- FortiAIGate chart under `FAIG_helm/<version>/fortiaigate`
- AWS SSO session before Terraform and ECR operations

User overrides, generated files and licenses are environment-specific and must remain out of Git; `system.yml` is tracked. Chart and license inputs are not needed for foundation-only bootstrap.
