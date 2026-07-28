# Ollama

Ollama is an alternate provider path. The default AWS demo does not deploy an
Ollama server and does not configure an Ollama FortiAIGate provider
automatically; the default working model path is LiteLLM to Amazon Bedrock.

AWS LiteLLM defaults do not expose a raw Ollama alias. Local deployments can
enable Ollama explicitly and use `gpt-oss:20b` as the default local model.

These values are intentionally not active in the default profile. Advanced
manual testing can set the relevant Ansible overrides in
`ansible/group_vars/user.yml` or with `-e`:

- `ollama_base_url`
- `ollama_model`
- `direct_model_provider`
- `direct_model_ollama_base_url`
- `direct_model_ollama_model`

Use `test_model_direct.yml` for a direct provider smoke test after setting the
provider variables and making an external Ollama endpoint reachable.
FortiAIGate forwarding validation remains disabled by default; enable it only
after the corresponding FortiAIGate provider/guard is configured.

Common model preference examples:

```yaml
# Bedrock gpt-oss 20B
# direct_model_bedrock_model: openai.gpt-oss-20b-1:0

# Ollama gpt-oss 20B
# ollama_base_url: http://<ollama-host>:11434/v1
# ollama_model: gpt-oss:20b
```
