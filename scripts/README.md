# Scripts

Operational helper and smoke-test scripts used by the Ansible playbooks and
manual troubleshooting.

Current scripts:

- `bedrock_direct_test.py`: sends a direct signed Bedrock Converse request
- `fortiaigate_chat_test.py`: sends an OpenAI-compatible chat request through FortiAIGate

FortiAIGate image publishing is handled by the Ansible playbook `ansible/playbooks/publish_images.yml`.
