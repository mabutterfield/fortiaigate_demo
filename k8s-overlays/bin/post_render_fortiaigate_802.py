#!/usr/bin/env python3
"""Add the k3s NVIDIA runtime to FortiAIGate 8.0.2 GPU workloads.

The 8.0.2 chart owns image tags, GPU resources, and model configuration. Do not
apply the 8.0.1 post-renderer's Triton/model-image overrides to this release.
"""

import sys

try:
    import yaml
except ImportError as exc:
    raise SystemExit("python3-yaml is required for the FortiAIGate post-renderer") from exc

GPU_WORKLOADS = {"triton-server", "triton-vllm-server", "vllm-server"}


def patch_gpu_runtime(document):
    if document.get("kind") != "Deployment" or document.get("metadata", {}).get("name") not in GPU_WORKLOADS:
        return
    pod = document.get("spec", {}).get("template", {}).get("spec", {})
    containers = pod.get("initContainers", []) + pod.get("containers", [])
    uses_gpu = any(
        any(name.startswith("nvidia.com/") for name in container.get("resources", {}).get("limits", {}))
        for container in containers
    )
    if uses_gpu:
        pod["runtimeClassName"] = "nvidia"


def patch_local_storage(document):
    # The vendor chart hardcodes RWX; single-node k3s local-path supports RWO.
    if (document.get("kind") == "PersistentVolumeClaim"
            and document.get("metadata", {}).get("name") == "fortiaigate-storage"
            and document.get("spec", {}).get("storageClassName") == "local-path"):
        document["spec"]["accessModes"] = ["ReadWriteOnce"]


def patch_https_redirect(document):
    # Vendor default force-ssl-redirect=false serves HTTP when a client uses
    # an IP that does not match the chart's wildcard TLS host. Require nginx
    # to redirect HTTP for this ingress while preserving all other annotations.
    if (document.get("kind") == "Ingress"
            and document.get("metadata", {}).get("name") == "fortiaigate-ingress"
            and document.get("spec", {}).get("ingressClassName") == "nginx"
            and document.get("spec", {}).get("tls")):
        annotations = document.setdefault("metadata", {}).setdefault("annotations", {})
        annotations["nginx.ingress.kubernetes.io/ssl-redirect"] = "true"
        annotations["nginx.ingress.kubernetes.io/force-ssl-redirect"] = "true"


def main():
    documents = [doc for doc in yaml.safe_load_all(sys.stdin) if doc]
    for doc in documents:
        patch_gpu_runtime(doc)
        patch_local_storage(doc)
        patch_https_redirect(doc)
    yaml.safe_dump_all(documents, sys.stdout, explicit_start=True, sort_keys=False)


if __name__ == "__main__":
    main()
