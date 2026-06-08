#!/usr/bin/env python3
"""Helm post-renderer for the FortiAIGate phase 1 k3s deployment."""

import sys
import os

try:
    import yaml
except ImportError as exc:
    raise SystemExit("python3-yaml is required for the FortiAIGate post-renderer") from exc


def ensure_named_env(container, name, value):
    env = container.setdefault("env", [])
    for item in env:
        if item.get("name") == name:
            item["value"] = value
            return
    env.append({"name": name, "value": value})


def patch_storage_pvc(doc):
    metadata = doc.get("metadata", {})
    name = metadata.get("name", "")
    if doc.get("kind") != "PersistentVolumeClaim" or not name.endswith("-storage"):
        return

    spec = doc.setdefault("spec", {})
    spec["accessModes"] = ["ReadWriteOnce"]
    spec["storageClassName"] = "local-path"


def patch_nginx_ingress(doc):
    if doc.get("kind") != "Ingress":
        return

    spec = doc.get("spec", {})
    if spec.get("ingressClassName") != "nginx":
        return

    metadata = doc.setdefault("metadata", {})
    annotations = metadata.setdefault("annotations", {})
    annotations.setdefault("nginx.ingress.kubernetes.io/proxy-ssl-verify", "off")


def patch_triton_deployment(doc):
    if doc.get("kind") != "Deployment":
        return
    if doc.get("metadata", {}).get("name") != "triton-server":
        return

    spec = doc.setdefault("spec", {})
    spec["strategy"] = {"type": "Recreate"}

    pod_spec = spec.setdefault("template", {}).setdefault("spec", {})
    pod_spec["runtimeClassName"] = "nvidia"

    image_repository = os.environ.get("FORTIAIGATE_IMAGE_REPOSITORY", "").rstrip("/")
    triton_model_image_tag = os.environ.get("FORTIAIGATE_TRITON_MODEL_IMAGE_TAG", "")
    triton_image_tag = os.environ.get("FORTIAIGATE_TRITON_IMAGE_TAG", "")

    for container in pod_spec.get("initContainers", []):
        if container.get("name") == "model-loader" and image_repository and triton_model_image_tag:
            container["image"] = f"{image_repository}/triton-models:{triton_model_image_tag}"

    for container in pod_spec.get("containers", []):
        if container.get("name") != "triton":
            continue

        if image_repository and triton_image_tag:
            container["image"] = f"{image_repository}/custom-triton:{triton_image_tag}"

        ensure_named_env(container, "NVIDIA_VISIBLE_DEVICES", "all")
        ensure_named_env(container, "NVIDIA_DRIVER_CAPABILITIES", "compute,utility")
        container["resources"] = {
            "requests": {
                "cpu": "2",
                "memory": "16Gi",
                "nvidia.com/gpu": "1",
            },
            "limits": {
                "cpu": "8",
                "memory": "48Gi",
                "nvidia.com/gpu": "1",
            },
        }

    for volume in pod_spec.get("volumes", []):
        if volume.get("name") == "shm-memory":
            empty_dir = volume.setdefault("emptyDir", {})
            empty_dir["medium"] = "Memory"
            empty_dir["sizeLimit"] = "8Gi"


def main():
    docs = list(yaml.safe_load_all(sys.stdin))
    patched = []
    for doc in docs:
        if not doc:
            continue
        patch_storage_pvc(doc)
        patch_nginx_ingress(doc)
        patch_triton_deployment(doc)
        patched.append(doc)

    yaml.safe_dump_all(
        patched,
        sys.stdout,
        default_flow_style=False,
        explicit_start=True,
        sort_keys=False,
    )


if __name__ == "__main__":
    main()
