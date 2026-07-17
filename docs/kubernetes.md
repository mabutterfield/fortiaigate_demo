# Kubernetes

The demo uses single-node k3s on Ubuntu 24.04. Ansible installs and configures:

- NVIDIA driver and utilities
- container runtime support for NVIDIA GPUs
- k3s
- NVIDIA device plugin
- RuntimeClass
- nginx ingress
- local-path storage

## Helm Deployments

FortiAIGate is deployed from the vendor Helm chart stored outside this repo.
The default path is:

```text
FAIG_helm/<version>/fortiaigate
```

`deploy_fortiaigate.yml` packages that local chart on the Ansible controller,
copies the archive to the k3s host, extracts it into a temporary staging
directory, stages license and TLS files into that temporary copy, renders a
values file, installs the repo-owned post-renderer, then runs `helm upgrade
--install`.

The role runs `helm template` with the same values and post-renderer before the
install so rendered manifests can be inspected during troubleshooting. The
submitted Helm release uses `/etc/rancher/k3s/k3s.yaml` on the target host.

FortiAIGate Helm deploys asynchronously by default:

```yaml
fortiaigate_helm_wait: false
fortiaigate_helm_timeout: 20m
```

With the default, Helm returns after it accepts the install or upgrade. Use
`status_fortiaigate.yml` and `validate_faig.yml` for readiness. Set
`fortiaigate_helm_wait: true` only when you want Helm to block until Kubernetes
reports readiness or the timeout expires.

The demo application layer also uses Helm charts:

- LiteLLM proxy and Admin UI
- MCP demo tools
- custom chatbot
- demo home page
- Open WebUI when `openwebui_enabled=true`
- HTTPS gateway

## FortiAIGate Post-Renderer

FortiAIGate uses
`k8s-overlays/bin/post_render_fortiaigate.py` as a Helm post-renderer. This
keeps the vendor chart outside the repo and applies lab-specific Kubernetes
transforms to rendered YAML at deploy time.

Current post-render transforms:

- FortiAIGate storage PVC uses `ReadWriteOnce` and `local-path`.
- nginx Ingress gets `nginx.ingress.kubernetes.io/proxy-ssl-verify: "off"`.
- `triton-server` Deployment uses `strategy.type: Recreate`.
- `triton-server` pod uses `runtimeClassName: nvidia`.
- Triton model-loader image is rewritten to the repo ECR `triton-models` tag.
- Triton container image is rewritten to the repo ECR `custom-triton` tag.
- Triton gets `NVIDIA_VISIBLE_DEVICES=all` and
  `NVIDIA_DRIVER_CAPABILITIES=compute,utility`.
- Triton GPU/CPU/memory requests and limits are raised for the default
  `g4dn.4xlarge` lab profile.
- Triton liveness/readiness probe delay and failure threshold are tunable with
  Ansible variables and passed to the post-renderer as environment variables.
- Triton `/dev/shm` memory volume is raised to `8Gi`.

The deploy role passes these post-render environment variables:

```text
FORTIAIGATE_IMAGE_REPOSITORY
FORTIAIGATE_TRITON_MODEL_IMAGE_TAG
FORTIAIGATE_TRITON_IMAGE_TAG
FORTIAIGATE_TRITON_PROBE_INITIAL_DELAY_SECONDS
FORTIAIGATE_TRITON_PROBE_FAILURE_THRESHOLD
```

The post-renderer depends on Python YAML support on the k3s host. The bootstrap
role installs the required package as part of the Kubernetes foundation.

## Status

The bootstrap playbook runs the same foundation validation as
`validate_k3s.yml` before it finishes. The standalone validation playbook is
useful after rebuilds, network changes, or manual troubleshooting.

Useful status entry points:

- `ansible/playbooks/validate_k3s.yml`
- `ansible/playbooks/status_fortiaigate.yml`
- `ansible/playbooks/validate_faig.yml`
- `ansible/playbooks/status_litellm.yml`
- `ansible/playbooks/status_chatbots.yml`
- `ansible/playbooks/status_mcp.yml`
- `ansible/playbooks/test_mcp.yml`
- `ansible/playbooks/status_demo_home.yml`

Open WebUI is optional and disabled by default; use
`ansible/playbooks/status_openwebui.yml` only when `openwebui_enabled=true`.

See [AWS k3s Foundation](aws-k3s-foundation.md),
[k8s-overlays FortiAIGate README](../k8s-overlays/fortiaigate/README.md), and
[Deployment Runbook](deployment-runbook.md) for the full workflow.
