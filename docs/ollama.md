# Ollama

Ollama is an alternate/future provider path. The default AWS demo does not
deploy an Ollama server and does not configure an Ollama FortiAIGate provider
automatically; the default model path is LiteLLM to Amazon Bedrock.

Relevant Ansible variables live in `ansible/group_vars/all.yml`:

- `ollama_base_url`
- `ollama_model`
- `direct_model_provider`
- `direct_model_ollama_base_url`
- `direct_model_ollama_model`

Use `test_model_direct.yml` for a direct provider smoke test after setting the
provider variables and making an external Ollama endpoint reachable.
FortiAIGate forwarding validation remains disabled by default; enable it only
after the corresponding FortiAIGate provider/guard is configured.
