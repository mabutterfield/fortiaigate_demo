# Ollama

Ollama is supported as an alternate provider/test path where practical, but the
AWS demo flow currently focuses on Bedrock and FortiAIGate.

Relevant Ansible variables live in `ansible/group_vars/all.yml`:

- `ollama_base_url`
- `ollama_model`
- `direct_model_provider`
- `direct_model_ollama_base_url`
- `direct_model_ollama_model`

Use `test_model_direct.yml` for a direct provider smoke test after setting the
provider variables. FortiAIGate forwarding validation remains disabled by
default; enable it only after the corresponding FortiAIGate provider/guard is
configured.
