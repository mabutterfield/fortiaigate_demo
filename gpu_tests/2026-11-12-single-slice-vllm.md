# Isolated single-16 GB-slice vLLM experiment — November 12, 2026

Question: can FAIG 8.0.2 PolicyGuard vLLM execute on one nominal 16 GB GPU?
This tests the vendor container on one RTX PRO 4500 `1g.16gb` MIG slice, not
the full detector stack or a consumer card. Slice capacity: 16,032 MiB.

The existing shared Triton/vLLM deployment was temporarily patched: one MIG
resource and probe expectation, TP=1, Triton replaced by a sleeping process,
max context 1,024 tokens, max concurrent sequences 1, and `--enforce-eager`.
The host-local undo patch restores the original deployment fields. GPU
resources and Triton must be restored before any end-to-end security testing.

- `--gpu-memory-utilization=0.97`: 13.8 GiB model weights and 1.08 GiB
  available KV cache; startup failed during attention warmup with an attempt
  to allocate 413,138,944 bytes when roughly 305–315 MB was free.
- `--gpu-memory-utilization=0.93`: 13.8 GiB model weights and 0.46 GiB
  available KV cache. The server became healthy, but a direct inference request
  returned HTTP 500 and the engine died: an attention workspace allocation of
  413,138,944 bytes failed with roughly 156–158 MB free.
- `--gpu-memory-utilization=0.91`: 13.8 GiB model weights and 0.14 GiB
  available KV cache, reported 3,119 cache tokens; the configured max number
  of simultaneous sequences was one. A direct short chat completion returned
  HTTP 200 in 1.37 seconds, producing 24 tokens with finish reason `length`.
  At the subsequent `nvidia-smi`, the slice used 15,966 / 16,032 MiB and the
  `VLLM::EngineCore` process accounted for 15,894 MiB.

This is a narrow positive result: one tiny direct request passed with only
about 66 MiB slice headroom, no Triton workload, shortened context, eager
execution and limited concurrency. It does not establish full FAIG scanning,
DLP/NLP, sustained or varied requests, production suitability, or an absolute
minimum across GPUs, backends and vLLM versions. No CPU offload or model
changes were used. More testing is required to see whether a second GPU can
host Triton while vLLM uses one 16 GB card.

After the test, the original two-slice deployment fields were restored. The
two-container pod returned to 2/2 ready, direct vLLM inference returned HTTP
200, and the restarted gateway logged scanning enabled. The temporary MIG
metering workaround from the two-slice report remains active. No governed
policy request has yet been tested.
