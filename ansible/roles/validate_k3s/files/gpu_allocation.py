#!/usr/bin/env python3
"""Decide whether the foundation GPU validation pod can run (Change 2026-11-20, revised 2026-11-23).

Prints JSON: {allocatable, used, holders: [{pod, phase, node, ready, gpus}], decision, reason}.

decision:
  run   a GPU is free (or the node has none, so the GPU pod fails as before): run the real check
  skip  every GPU is held by pods that are Running, bound to a node and fully Ready: an
        occupied-device RESUME check only. It shows the device is allocated to a healthy-looking
        workload; it does NOT prove CUDA health. Report the GPU workload check as skipped.
  fail  every GPU is held, but some holder is not Running, not bound or not Ready: inspect first
"""
from __future__ import annotations

import json
import subprocess
import sys


def _gpus(pod: dict) -> int:
    total = 0
    for container in pod.get("spec", {}).get("containers", []) or []:
        resources = container.get("resources") or {}
        limits = resources.get("limits") or {}
        requests = resources.get("requests") or {}
        total += int(limits.get("nvidia.com/gpu") or requests.get("nvidia.com/gpu") or 0)
    return total


def _ready(pod: dict) -> bool:
    statuses = pod.get("status", {}).get("containerStatuses") or []
    containers = pod.get("spec", {}).get("containers") or []
    return bool(statuses) and len(statuses) == len(containers) and all(s.get("ready") is True for s in statuses)


def summarize(nodes: dict, pods: dict) -> dict:
    allocatable = sum(int(((n.get("status") or {}).get("allocatable") or {}).get("nvidia.com/gpu") or 0)
                      for n in nodes.get("items", []))
    used, holders = 0, []
    for pod in pods.get("items", []):
        phase = (pod.get("status") or {}).get("phase", "")
        if phase in ("Succeeded", "Failed"):
            continue
        gpus = _gpus(pod)
        if not gpus:
            continue
        used += gpus
        meta = pod.get("metadata") or {}
        holders.append({"pod": f"{meta.get('namespace', '')}/{meta.get('name', '')}", "phase": phase,
                        "node": (pod.get("spec") or {}).get("nodeName") or "", "ready": _ready(pod), "gpus": gpus})
    if allocatable == 0:
        decision, reason = "run", "no allocatable GPU reported; the GPU validation pod will show the failure"
    elif used < allocatable:
        decision, reason = "run", f"{allocatable - used} of {allocatable} GPU(s) free"
    else:
        unhealthy = [h for h in holders if h["phase"] != "Running" or not h["node"] or not h["ready"]]
        if unhealthy:
            decision = "fail"
            reason = "every GPU is allocated but these holders are not Running, bound and Ready: " + ", ".join(
                f"{h['pod']} (phase {h['phase'] or '?'}, node {h['node'] or 'none'}, ready {h['ready']})" for h in unhealthy)
        else:
            decision = "skip"
            reason = ("GPU workload check SKIPPED (occupied-device resume check, not a CUDA health check): "
                      + ", ".join(f"{h['pod']} holds {h['gpus']} GPU(s), Running and Ready on {h['node']}" for h in holders))
    return {"allocatable": allocatable, "used": used, "holders": holders, "decision": decision, "reason": reason}


def main(argv: list[str]) -> int:
    kubeconfig = argv[1] if len(argv) > 1 else "/etc/rancher/k3s/k3s.yaml"
    kubectl = ["/usr/local/bin/kubectl", "--kubeconfig", kubeconfig]
    nodes = json.loads(subprocess.run(kubectl + ["get", "nodes", "-o", "json"], check=True, capture_output=True, text=True).stdout)
    pods = json.loads(subprocess.run(kubectl + ["get", "pods", "-A", "-o", "json"], check=True, capture_output=True, text=True).stdout)
    print(json.dumps(summarize(nodes, pods)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
