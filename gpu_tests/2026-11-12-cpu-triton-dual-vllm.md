# CPU Triton with vLLM on two physical GPUs — November 12, 2026

This is an unsupported, single-node experiment. Fortinet's 8.0.2 guide says
DLP and Natural Language detectors require a GPU. The deployment uses a lab
post-renderer and modifies GPU metering; neither change belongs to the normal
operational workflow.

## Configuration

On the g7.12xlarge, each physical RTX PRO 4500 exposes one 1g.16gb MIG slice.
Helm revision 5 used `vllm.gpuAttach: dedicated` with two MIG resources,
tensor parallel size 2, `gpuMemoryUtilization: 0.80`, 16,384-token context,
and 64 max sequences. The [values](artifacts/2026-11-12-cpu-triton-values.yaml)
and [post-renderer](artifacts/2026-11-12-cpu-triton-post-render.py) are
controller-side experiment artifacts. The post-renderer imports the regular
host post-renderer to preserve
the k3s runtime and local PVC changes; it removes NVIDIA resources and the
NVIDIA runtime from `triton-server`, and sets NVIDIA_VISIBLE_DEVICES=void and
CUDA_VISIBLE_DEVICES=-1. Helm invoked it from `/root` on the host.

After reviewing the overrides, stage both files on the host at
`/root/faig-cpu-triton-values.yaml` and `/root/faig-cpu-triton-post-render.py`
with root-only permissions, making the post-renderer executable. The latter
expects the normal bootstrap's `/home/ubuntu/tmp/fortiaigate-post-render.py`;
adjust that lab path if the SSH user or staging location differs. With the
existing chart copy and release, the test upgrade used:

```bash
sudo helm --kubeconfig /etc/rancher/k3s/k3s.yaml -n fortiaigate upgrade \
  fortiaigate /home/ubuntu/tmp/fortiaigate-chart-802 --reuse-values \
  -f /root/faig-cpu-triton-values.yaml \
  --post-renderer /root/faig-cpu-triton-post-render.py
```

Both slices must already exist and be schedulable; review the proposed chart
render and Helm revision first. This change interrupts scanning. The operator
must separately verify Triton has no GPU devices and the vLLM reporter covers
every physical GPU before considering the experimental metering override below.

Triton logged `sensitive_model_0_0 (CPU device 0)` and reported the model
ready. No NVIDIA device nodes were visible in the Triton container. vLLM's
two workers were the only GPU processes: each used 13,392 MiB at the recorded
snapshot, with 13,464/16,032 MiB total used per slice, about 2,568 MiB free.
vLLM logged 7.12 GiB model weights per worker, 3.24 GiB KV cache per worker,
and 225,054 total cache tokens. `kubectl top` showed CPU Triton at 3,482 MiB
and 1.612 CPU cores at one instant; these are not peak measurements.

## Metering and safety limitation

The stock CPU-only Triton GPU reporter returned 503 `ERROR_LIBRARY_NOT_FOUND`
because no NVIDIA library was present. After independently confirming the
Triton pod had no GPU devices and the vLLM reporter mapped both MIG UUIDs to
the two physical GPUs, this lab temporarily set the guardrail metrics endpoint
to empty, its reporter list to `vllm-server-metering:9110`, and its service
pair list to `vllm-server=vllm-server-metering`. License manager then reported
two GPUs, two valid licenses and zero unreadable sources; the restarted
gateway logged scanning enabled.

After those checks the live lab override was:

```bash
kubectl -n fortiaigate set env deployment/guardrail \
  GUARDRAIL_METERING_METRICS_ENDPOINTS= \
  GUARDRAIL_METERING_ENDPOINTS=vllm-server-metering:9110 \
  GUARDRAIL_METERING_SERVICE_PAIRS=vllm-server=vllm-server-metering
```

Wait for a fresh inventory poll, then verify the license manager and gateway;
the experiment restarted the gateway and scanner deployments to refresh their
connections. Recheck actual policy and DLP behavior rather than assuming that
the license verdict alone proves inspection.

This intentionally excludes the CPU Triton reporter and Triton service-pair
check. It reduces inventory and service coverage and must not be treated as a
supported or production-ready licensing configuration. It is valid evidence for
this disposable test only, with the separate verified CPU-only pod and vLLM
reporter. A fresh Helm upgrade may overwrite the live metering override.

## Functional checks

Through the existing virtual key and policy, a benign request returned the
requested text in 6.71 s; a fictional email request returned HTTP 200 in 2.99 s
and guardrail logs recorded DLP `ERASE/COMPLETED`; the client saw the original
email, consistent with prior observed rehydration. A Palo Alto ordering request
was denied by the configured natural-language policy in 1.00 s; a neutral
factual request passed in 4.80 s. These are individual end-to-end timings, not
a benchmark. Input and output scans ran on the policy and DLP stack; the tests
do not prove broad DLP equivalence, long-input behavior, throughput or
concurrent stability. The previous GPU-backed baseline had lower latency on
individual requests.

The lab is intentionally left in this configuration for user testing. To
restore the last known working GPU-Triton configuration, roll back to the
previous shared release and reapply the documented MIG metering workaround
after independently verifying both reporters. A Helm rollback or upgrade may
restart models and interrupt inspection. ECR is not changed by these steps.
