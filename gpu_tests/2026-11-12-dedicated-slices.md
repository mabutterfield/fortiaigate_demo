# Dedicated Triton and vLLM on separate 16 GB MIG slices

On November 12, 2026, Helm revision 3 used the [lab values file](artifacts/2026-11-12-dedicated-16gb-values.yaml) to
switch the stock 8.0.2 chart to `vllm.gpuAttach: dedicated`. Triton and vLLM
each requested one `nvidia.com/mig-1g.16gb` resource. This changed the shared
pod into separate deployments without editing the vendor chart.

Both pods became healthy. The dedicated reporters and `nvidia-smi` confirmed
that vLLM used GPU 0 and Triton used GPU 1, each under a different physical
GPU UUID. At one snapshot vLLM used 15,500 MiB on its slice and Triton used
2,410 MiB on the other. Both 16,032 MiB slices were independently allocated.
The native Triton metrics MIG issue recurred after Helm upgrade; only after
checking both separate reporters was the previously documented temporary
metering workaround reapplied. License manager then reported two GPUs, two
licenses and zero unreadable sources, and the gateway reported scanning on.

The initial vLLM settings matched the narrow standalone test: eager mode,
0.91 memory utilization, max context 1,024 and one sequence. Both pods were
ready, but five actual governed requests returned HTTP 503 fail-closed. The
policy-guard logs reported that the General AI Safety Guard and OWASP rule
definitions did not fit the 1,024-token model context. The gateway did not
send these requests upstream.

A host-only patch raised max context to 3,072; at 0.91 utilization vLLM
failed to start because the estimated available KV cache was only 0.04 GiB.
At 0.92 utilization vLLM started with about 0.19 GiB KV cache and 4,189 cache
tokens, but the first governed request triggered GPU out-of-memory during a
413,138,944-byte attention workspace allocation. The gateway again returned
503 without forwarding the request. This is not a successful full-policy
split deployment, even though the engines could be independently scheduled.

After the test Helm revision 2 was restored to return to the previous working
shared two-slice deployment. Host-only patches are not included in normal
deployment automation. The two 16 GB slices have not demonstrated practical
full-policy operation with one dedicated to vLLM; a 20 GB physical card may
provide more headroom but has not been tested. See the adjacent CPU Triton
probe for a separate unsupported model-level CPU inference experiment.

Following rollback the dedicated metering reporters were checked again, the
MIG metrics workaround was reapplied, and the gateway and scanner deployments
were restarted to refresh their service connections. A governed benign request
returned the expected answer and the Palo Alto ordering request was blocked
by the restored policy.
