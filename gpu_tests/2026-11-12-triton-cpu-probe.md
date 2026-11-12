# Isolated Triton CPU probe — November 12, 2026

This was an isolated pod, not selected by FAIG's live Triton service. It used
the same custom Triton image, encrypted `sensitive_model` image and model
configuration as the GPU-backed deployment. It requested no NVIDIA resource,
had no NVIDIA runtime class, and set `NVIDIA_VISIBLE_DEVICES=void` and
`CUDA_VISIBLE_DEVICES=-1`. The model configuration used `KIND_AUTO`.

Triton logged `sensitive_model_0_0 (CPU device 0)` and successfully loaded
`sensitive_model`; the pod became ready. A synthetic 8-token tensor inference
returned logits shaped `[1, 8, 16, 55]` without a GPU. The same input to the
live GPU model returned the same tensor shape. On one request each, CPU took
2.033 s and GPU 0.012 s; these are not a controlled benchmark. Across 7,040
logits, maximum absolute CPU/GPU difference was about 0.310 and mean absolute
difference about 0.0195. The CPU pod showed about 3,468 MiB in `kubectl top`
when idle; this is not a peak measurement.

This establishes model-level CPU execution only. It does not establish that
FAIG's DLP scanner, licensing, governance or production configuration works
on CPU, or that logits lead to equivalent DLP decisions. Fortinet's guide says
DLP and Natural Language detectors require a GPU and are unavailable in a
non-GPU deployment. The chart helper describes this Triton CPU fallback but
says the packaged vLLM CUDA image has no CPU fallback.
