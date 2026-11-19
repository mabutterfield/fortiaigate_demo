"""FortiAIGate 8.0.2 student lab chatbot (Streamlit).

One shared app behind the lab login gateway. The gateway signs the visitor's
identity into X-Lab-* headers; this app verifies them, then chats with the
student's own per-scenario, per-action FortiAIGate virtual key at
`/ai/openai/v1` (the key selects the policy). "Direct" sends the same turn
straight to LiteLLM with the shared lab key, bypassing FortiAIGate, for
comparison. MCP tools come from the standards endpoint through the shared
agent loop (faig_agent.py). Super admins can act as any student.

Chat history lives only in the browser session.
"""
from __future__ import annotations

import json
import os
from typing import Any

import streamlit as st

import faig_agent
import lab_support as ls

CFG = {
    "signing_key_file": os.environ.get("LAB_SIGNING_KEY_FILE", "/etc/lab-chatbot/signing/hmac-key"),
    "faig_url": os.environ.get("LAB_FAIG_URL", "http://ingress-nginx-controller.ingress-nginx.svc.cluster.local/ai/openai/v1"),
    "direct_url": os.environ.get("LAB_DIRECT_URL", "http://litellm.litellm.svc.cluster.local:4000/v1"),
    "direct_key_file": os.environ.get("LAB_DIRECT_KEY_FILE", "/etc/lab-chatbot/direct/api-key"),
    "mcp_url": os.environ.get("LAB_MCP_URL", "http://mcp-demo.mcp.svc.cluster.local:8001/mcp"),
    "auth_url": os.environ.get("LAB_AUTH_URL", "http://demo-https-gateway-auth.demo-https-gateway.svc.cluster.local:8090"),
    "pack_file": os.environ.get("LAB_PACK_FILE", "/app/scenario-pack.json"),
    "namespace": os.environ.get("LAB_NAMESPACE", "lab-chatbot"),
    "secret_prefix": os.environ.get("LAB_KEY_SECRET_PREFIX", "lab-keys-"),
    "students": [s for s in os.environ.get("LAB_STUDENTS", "").split(",") if s],
    "max_tokens": int(os.environ.get("LAB_MAX_TOKENS", "2048")),
    "temperature": float(os.environ.get("LAB_TEMPERATURE", "0.0")),
    "title": os.environ.get("LAB_TITLE", "FortiAIGate Lab Chatbot"),
}
PATH_FAIG, PATH_DIRECT = "FortiAIGate (your key)", "Direct to LiteLLM (no FortiAIGate)"


@st.cache_resource
def signing_key() -> bytes:
    return ls.load_signing_key(CFG["signing_key_file"])


@st.cache_resource
def scenario_pack() -> dict[str, Any]:
    with open(CFG["pack_file"], encoding="utf-8") as handle:
        return json.load(handle)


@st.cache_resource
def secret_store() -> ls.SecretStore:
    return ls.SecretStore(CFG["namespace"], CFG["secret_prefix"])


def direct_key() -> str:
    try:
        with open(CFG["direct_key_file"], encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def current_identity() -> dict[str, str] | None:
    """Verify the gateway headers once per browser session and keep the result."""
    if "identity" not in st.session_state:
        headers = {k.lower(): v for k, v in st.context.headers.items()}
        st.session_state.identity = ls.verify_identity(headers, signing_key())
    return st.session_state.identity


def load_keys(student: str, force: bool = False) -> list[dict[str, Any]]:
    cache = st.session_state.setdefault("keys", {})
    if force or student not in cache:
        cache[student] = secret_store().load(student)
    return cache[student]


def reset_chat() -> None:
    st.session_state.messages = []


def render_turn(turn: dict[str, Any]) -> None:
    result = turn["result"]
    if result.get("error") == "http_error":
        status = result.get("http_status")
        body = (result.get("detail") or {}).get("error_body", "")
        # FortiAIGate blocks arrive as normal replies; an HTTP error is a key, budget, or upstream problem.
        st.error(f"HTTP {status}: request failed")
        if body:
            st.code(body[:1500], language="json")
    elif result.get("error"):
        st.error(f"{result['error']}: {result.get('detail')}")
    else:
        st.markdown(result.get("reply") or "_(empty reply)_")
    events = result.get("tool_events") or []
    caption = f"{turn['path']} · key `{turn['key_name']}` · model `{turn['model']}`"
    st.caption(caption + (f" · {len(events)} tool call(s)" if events else ""))
    if events:
        with st.expander("MCP tool calls"):
            for event in events:
                st.markdown(f"**{event['tool']}** {'(error)' if event.get('is_error') else ''}")
                st.json({"arguments": event.get("arguments"), "result": event.get("result")}, expanded=False)


def run_chat_turn(prompt: str, ctx: dict[str, Any]) -> None:
    history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
    st.session_state.messages.append({"role": "user", "content": prompt})
    spec = {"base_url": ctx["base_url"], "api_key": ctx["api_key"], "model": ctx["model"], "prompt": prompt,
            "system_prompt": ctx["system_prompt"], "history": history, "mcp_url": CFG["mcp_url"],
            "tools": ctx["tools"], "max_rounds": ctx["max_rounds"], "max_tokens": CFG["max_tokens"],
            "temperature": CFG["temperature"]}
    with st.spinner("Waiting for the model..."):
        try:
            result = faig_agent.run_turn_sync(spec)
        except Exception as exc:  # network or MCP transport failure; never echo the key
            result = {"error": "agent_failed", "detail": type(exc).__name__, "reply": "", "tool_events": []}
    turn = {"path": ctx["path"], "key_name": ctx["key_name"], "model": ctx["model"], "result": result}
    content = result.get("reply") or ""
    st.session_state.messages.append({"role": "assistant", "content": content, "turn": turn})


def chat_tab(ctx: dict[str, Any] | None, entry: dict[str, Any] | None) -> None:
    if ctx is None:
        st.info("No scenario keys are available for this student yet. Ask the instructor to seed them.")
        return
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if "turn" in message:
                render_turn(message["turn"])
            else:
                st.markdown(message["content"])
    samples = entry.get("sample_prompts", {}) if entry else {}
    choices = [("Attack", p) for p in samples.get("attack", [])] + [("Clean", p) for p in samples.get("clean", [])]
    if choices:
        with st.expander("Sample prompts"):
            for index, (kind, text) in enumerate(choices):
                if st.button(f"{kind}: {text[:110]}", key=f"sample-{index}", use_container_width=True):
                    st.session_state.pending_prompt = text
                    st.rerun()
    prompt = st.chat_input("Ask the scenario assistant...") or st.session_state.pop("pending_prompt", None)
    if prompt:
        run_chat_turn(prompt, ctx)
        st.rerun()


def keys_tab(identity: dict[str, str], student: str, keys: list[dict[str, Any]]) -> None:
    st.write("These are your FortiAIGate virtual keys, one per scenario action. The instructor seeds them; if you "
             "regenerate a key in FortiAIGate, paste the new value here. Changes stay in the lab chatbot and are "
             "not copied back to the instructor.")
    if not keys:
        st.info("No keys stored for this student.")
        return
    st.dataframe(ls.public_keys(keys), hide_index=True, use_container_width=True)
    if st.button("Check all keys against FortiAIGate"):
        for key in keys:
            ok, message = ls.check_key(CFG["faig_url"], key.get("secretKey", ""), key.get("model", ""))
            (st.success if ok else st.error)(f"{key.get('keyName')}: {message}")
    with st.form("replace-key", clear_on_submit=True):
        st.markdown("**Replace a key**")
        name = st.selectbox("Key", [k["keyName"] for k in keys])
        secret = st.text_input("New key value", type="password")
        if st.form_submit_button("Check and save"):
            target = next(k for k in keys if k["keyName"] == name)
            ok, message = ls.check_key(CFG["faig_url"], secret.strip(), target.get("model", ""))
            if not ok:
                st.error(message + " Not saved.")
            else:
                try:
                    updated = ls.replace_secret(keys, name, secret, identity["user"])
                    secret_store().save(student, updated)
                    load_keys(student, force=True)
                    st.success(message + " Saved.")
                except Exception as exc:  # RBAC or API failure
                    st.error(f"Could not save the key: {type(exc).__name__}")


def main() -> None:
    st.set_page_config(page_title=CFG["title"], page_icon=":shield:", layout="wide")
    identity = current_identity()
    if not identity:
        st.error("Your lab session could not be verified. Open the chatbot through the lab URL and sign in again.")
        st.markdown("[Sign in](/_lab/login)")
        return
    st.session_state.setdefault("messages", [])
    pack = scenario_pack()

    with st.sidebar:
        st.markdown(f"**{identity['user']}**  \n{identity['role']}"
                    + (f" · {identity['student']}" if identity["student"] else ""))
        if identity["role"] == "admin":
            if not CFG["students"]:
                st.warning("No students are configured.")
                return
            student = st.selectbox("Act as student", CFG["students"], on_change=reset_chat)
        else:
            student = identity["student"]
        keys = load_keys(student)
        options = ls.available(keys, pack)
        ctx, entry = None, None
        if options:
            scenario = st.selectbox("Scenario", list(options), on_change=reset_chat,
                                    format_func=lambda s: pack["scenarios"][s].get("title", s))
            action = st.selectbox("Action", options[scenario], on_change=reset_chat)
            path = st.radio("Send through", [PATH_FAIG, PATH_DIRECT], on_change=reset_chat)
            entry = pack["scenarios"][scenario]
            spec = entry["actions"][action]
            key = ls.key_for(keys, scenario, action)
            direct = path == PATH_DIRECT
            ctx = {"path": path, "model": spec["model"], "system_prompt": spec.get("system_prompt", ""),
                   "tools": spec.get("tools", []), "max_rounds": spec.get("max_rounds", 3),
                   "base_url": CFG["direct_url"] if direct else CFG["faig_url"],
                   "api_key": direct_key() if direct else key.get("secretKey", ""),
                   "key_name": "shared LiteLLM lab key" if direct else key["keyName"]}
            if entry.get("description"):
                st.caption(entry["description"])
            st.caption(f"Key: `{ctx['key_name']}`" + ("" if direct else f" ({ls.mask(ctx['api_key'])})"))
            if ctx["tools"]:
                st.caption("MCP tools: " + ", ".join(ctx["tools"]))
            if direct and not ctx["api_key"]:
                st.warning("The shared LiteLLM key is not mounted; Direct mode is unavailable.")
        if st.button("Clear chat"):
            reset_chat()
            st.rerun()
        if st.button("Reload keys"):
            load_keys(student, force=True)
            st.rerun()
        st.markdown("[Sign out](/_lab/logout)")

    st.title(CFG["title"])
    chat, my_keys = st.tabs(["Chat", "Keys"])
    with chat:
        chat_tab(ctx, entry)
    with my_keys:
        keys_tab(identity, student, keys)


main()
