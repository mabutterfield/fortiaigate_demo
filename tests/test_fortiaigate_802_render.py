"""Ensure the 8.0.2 runtime patch does not alter vendor model settings."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("faig802", ROOT / "k8s-overlays/bin/post_render_fortiaigate_802.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RuntimePatchTests(unittest.TestCase):
    def deployment(self, name, gpu=True):
        resources = {"limits": {"nvidia.com/gpu": 1, "memory": "25Gi"}} if gpu else {}
        return {"kind": "Deployment", "metadata": {"name": name}, "spec": {"template": {"spec": {
            "initContainers": [{"name": "model-loader", "image": "registry/faig-models:0.0.5-s1"}],
            "containers": [{"name": "triton", "image": "registry/custom-triton:new", "resources": resources}],
        }}}}

    def test_shared_and_dedicated_gpu_pods_preserve_vendor_settings(self):
        for name in ("triton-vllm-server", "triton-server", "vllm-server"):
            with self.subTest(name=name):
                doc = self.deployment(name)
                expected = copy.deepcopy(doc)
                expected["spec"]["template"]["spec"]["runtimeClassName"] = "nvidia"
                MODULE.patch_gpu_runtime(doc)
                self.assertEqual(doc, expected)

    def test_only_local_path_claim_is_converted_to_single_node_access(self):
        doc = {"kind": "PersistentVolumeClaim", "metadata": {"name": "fortiaigate-storage"},
               "spec": {"storageClassName": "local-path", "accessModes": ["ReadWriteMany"]}}
        MODULE.patch_local_storage(doc)
        self.assertEqual(doc["spec"]["accessModes"], ["ReadWriteOnce"])
        doc["spec"].update(storageClassName="shared-nfs", accessModes=["ReadWriteMany"])
        expected = copy.deepcopy(doc)
        MODULE.patch_local_storage(doc)
        self.assertEqual(doc, expected)

    def test_cpu_or_unrelated_workload_is_unchanged(self):
        for doc in (self.deployment("triton-server", gpu=False), self.deployment("other")):
            expected = copy.deepcopy(doc)
            MODULE.patch_gpu_runtime(doc)
            self.assertEqual(doc, expected)


if __name__ == "__main__":
    unittest.main()
