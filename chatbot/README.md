# FortiAIGate Demo Chatbot

Deployable chatbot assets for the FortiAIGate demo.

The original reference app under `FAIG/ChatBot/basic_chatbot_tool` is treated as
read-only. This directory contains the Kubernetes-ready implementation used by
the Ansible roles in `fortiaigate_demo`.

The Phase 11 deployment is driven by the installed scenario matrix. Simplified
mode presents scenario-owned demo profiles. Advanced mode exposes the generated
LiteLLM aliases, FAIG static routes, MCP tool profiles and paths, and named
frontend instruction profiles. The UI does not synthesize `demo-a` or `demo-b`
options in matrix mode.

Frontend instruction templates are installed with each local scenario and may
be selected independently. The tracked examples remain read-only; edit the
ignored copy under `chatbot/scenarios/local/` and redeploy the chatbot to apply
local changes.
