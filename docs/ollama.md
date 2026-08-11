# Ollama

Ollama is the supported local-model path for local Ubuntu hardware mode. The
default AWS demo does not deploy Ollama; AWS defaults remain LiteLLM to Amazon
Bedrock.

Local quickstart deploys Ollama in k3s, points LiteLLM at the in-cluster Ollama
service, and exposes a plain HTTP NodePort for trusted-lab validation. The
default local Ollama NodePort is `30085`. Do not expose that NodePort to
untrusted networks because stock Ollama does not provide built-in API
authentication.

## Local Quickstart

Generate local inventory and variables first:

```bash
python3 scripts/local_setup.py
```

Then run the local quickstart:

```bash
python3 scripts/automated_quickstart.py --local
```

For manual local validation, select the local inventory; it supplies the
deployment target:

```bash
ansible-playbook -i local \
  ansible/playbooks/status_ollama.yml

ansible-playbook -i local \
  ansible/playbooks/validate_ollama.yml
```

`deploy_ollama.yml` pulls or prepares the configured model and validates that
the Ollama pod can serve the OpenAI-compatible chat API. Local setup records GPU
UUID selections when available so FortiAIGate and Ollama can avoid competing for
the same GPU on mixed local hosts.

## AWS Behavior

AWS LiteLLM defaults do not expose a raw Ollama alias and the AWS quickstart
does not deploy Ollama. Use AWS Bedrock through LiteLLM for the supported AWS
path. Treat AWS Ollama experiments as advanced local overrides, not v1.0
defaults.

## Variables

Common variables:

- `ollama_enabled`
- `ollama_namespace`
- `ollama_release_name`
- `ollama_model`
- `ollama_base_url`
- `ollama_node_port`
- `ollama_gpu_enabled`
- `ollama_gpu_count`
- `ollama_gpu_uuids`
- `ollama_storage_size`
- `ollama_keep_alive`
- `ollama_context_length`
- `direct_model_provider`
- `direct_model_ollama_base_url`
- `direct_model_ollama_model`

Use `ansible/group_vars/user.yml` for operator-owned overrides. Generated local
defaults from `local_setup.py` live in environment-owned generated local files
excluded from Git.

## Validation Boundary

Use `validate_ollama.yml` and `test_model_direct.yml` for direct provider smoke
tests. When `test_model_direct.yml` runs with the local inventory, it uses the
configured Ollama endpoint and skips Bedrock credential checks. FortiAIGate
forwarding validation remains disabled by
default until the corresponding FortiAIGate provider, guard, and flow are
configured manually in the GUI.

Model/tool-calling behavior varies by local model. Small local models are useful
for repeatable lab traffic and basic scenario rehearsals, but they may not call
tools as consistently as the AWS Bedrock GPT-OSS profiles. When scenario
validation depends on MCP tool selection, validate the exact local model and
tool profile before recording.

Common model preference examples:

```yaml
# Bedrock gpt-oss 20B
# direct_model_bedrock_model: openai.gpt-oss-20b-1:0

# Ollama gpt-oss 20B
# ollama_base_url: http://<ollama-host>:11434/v1
# ollama_model: gpt-oss:20b
# ollama_keep_alive: 60m
# ollama_context_length: 32768
```

`ollama_keep_alive` controls how long a loaded model remains in memory after a
request. Local deployments default to `60m` so demo runs do not unload the model
between short scenario tests.

`gpt-oss:20b` advertises a 131072 token context length in Ollama, but local
deployments default `ollama_context_length` to `32768` to avoid exhausting
16GB-class GPU memory during demos. Increase it only after checking `ollama ps`
and GPU memory headroom on the local host.
