"""FortiAIGate 8.0.2 student lab chatbot (Streamlit).

One shared app behind the lab login gateway. The gateway signs the visitor's
identity into X-Lab-* headers; this app verifies them, then chats with the
student's own per-scenario, per-action FortiAIGate virtual key at
`/ai/openai/v1` (the key selects the policy). "Direct" sends the same turn
straight to LiteLLM with the shared lab key, bypassing FortiAIGate, for
comparison. MCP tools come from the standards endpoint through the shared
agent loop (faig_agent.py). Super admins can act as any student.

The Tests tab runs a scenario action's validation case with the student's
key: one test at a time shows the payload sent, the payload returned, and the
matching Traffic Log entry; "Run all tests" reports pass/fail only.

Super admins also get an Admin tab: the lab's students, password resets
(FortiAIGate and the matching fallback hash, through the sign-in service with
the admin's own FAIG session), and a comparison of each student's keys with
the instructor's seed, with restore.

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
    "seed_prefix": os.environ.get("LAB_SEED_SECRET_PREFIX", "lab-seed-"),
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
    return ls.SecretStore(CFG["namespace"], CFG["secret_prefix"], seed_prefix=CFG["seed_prefix"])


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


def run_scenario_test(identity: dict[str, str], scenario: str, action: str, spec: dict[str, Any],
                      key: dict[str, Any], with_details: bool) -> dict[str, Any]:
    def fetch_logs(**query: Any) -> tuple[int, Any]:
        return ls.internal_logs(CFG["auth_url"], identity, signing_key(), **query)

    def agent(agent_spec: dict[str, Any]) -> dict[str, Any]:
        try:
            return faig_agent.run_turn_sync(agent_spec)
        except Exception as exc:  # network or MCP transport failure; never echo the key
            return {"error": "agent_failed", "detail": type(exc).__name__, "reply": "", "tool_events": []}

    return ls.run_test(agent, fetch_logs, scenario=scenario, action=action, spec=spec, key=key,
                       faig_url=CFG["faig_url"], mcp_url=CFG["mcp_url"], max_tokens=CFG["max_tokens"],
                       temperature=CFG["temperature"], with_details=with_details)


def render_single_result(result: dict[str, Any]) -> None:
    (st.success if result["passed"] else st.error)(
        f"{'PASS' if result['passed'] else 'FAIL'}: {result['scenario']} / {result['action']} "
        f"(observed {result['normalized'].get('scenario_verdict')}, Traffic Log "
        f"{', '.join(result['verdicts']) if result['verdicts'] is not None else 'not checked'})")
    for detail in result["details"]:
        st.write("- " + detail)
    exchanges, entries = result["exchanges"], result["log_entries"]
    if result["log_error"]:
        st.info("Traffic Log entries are shown for student sign-ins with an active FortiAIGate session. "
                f"({result['log_error']})")
    elif len(entries) != len(exchanges):
        st.caption(f"{len(exchanges)} request(s) and {len(entries)} Traffic Log entr(ies); entries are matched in "
                   "time order and another chat on the same key during the test can add rows.")
    for index in range(max(len(exchanges), len(entries))):
        st.markdown(f"#### Request {index + 1}")
        sent, returned, logged = st.columns(3)
        exchange = exchanges[index] if index < len(exchanges) else {}
        with sent:
            st.markdown("**Payload sent**")
            st.json(exchange.get("request", {}), expanded=1)
        with returned:
            st.markdown(f"**Payload returned** (HTTP {exchange.get('status', '-')})")
            st.json(exchange.get("response", {}), expanded=2)
        with logged:
            st.markdown("**Traffic Log entry**")
            if index < len(entries):
                st.json(entries[index], expanded=2)
            else:
                st.caption("No matching entry.")
    if result["tool_events"]:
        with st.expander("MCP tool calls"):
            st.json(result["tool_events"], expanded=False)


def tests_tab(identity: dict[str, str], keys: list[dict[str, Any]], pack: dict[str, Any],
              ctx: dict[str, Any] | None) -> None:
    if ctx is None:
        st.info("No scenario keys are available for this student yet.")
        return
    st.subheader("Run one test")
    st.write("Runs the selected scenario action's validation case with your FortiAIGate key and shows what was "
             "sent, what came back, and what FortiAIGate logged. Change the scenario and action in the sidebar.")
    test = ctx["spec"].get("test", {})
    st.markdown(f"**{pack['scenarios'][ctx['scenario']].get('title', ctx['scenario'])} / {ctx['action']}** "
                f"with key `{ctx['key']['keyName']}`")
    st.markdown(f"- Prompt: _{test.get('prompt', '')}_\n"
                f"- Expected result: `{test.get('expected_result', '')}`; Traffic Log verdict: "
                f"`{test.get('expected_log_verdict', '')}`"
                + (f"\n- Required tools: {', '.join(test['required_tools'])}" if test.get("required_tools") else "")
                + (f"\n- Forbidden tools: {', '.join(test['forbidden_tools'])}" if test.get("forbidden_tools") else ""))
    if st.button("Run this test", type="primary"):
        with st.spinner("Running the test and waiting for the Traffic Log..."):
            st.session_state.single_test = run_scenario_test(identity, ctx["scenario"], ctx["action"], ctx["spec"],
                                                             ctx["key"], with_details=True)
    last = st.session_state.get("single_test")
    if last and (last["scenario"], last["action"]) == (ctx["scenario"], ctx["action"]):
        render_single_result(last)

    st.divider()
    st.subheader("Run all tests")
    st.write("Checks every scenario action you have a key for and reports pass or fail. Failed tests are retried "
             "once (model answers vary). Use Run one test to see the details.")
    if st.button("Run all tests"):
        plan = [(s, a) for s, actions in ls.available(keys, pack).items() for a in actions]
        progress = st.progress(0.0, text="Starting...")
        rows = []
        for index, (scenario, action) in enumerate(plan):
            progress.progress(index / len(plan), text=f"{scenario} / {action}")
            spec, key = pack["scenarios"][scenario]["actions"][action], ls.key_for(keys, scenario, action)
            for _attempt in range(2):
                result = run_scenario_test(identity, scenario, action, spec, key, with_details=False)
                if result["passed"]:
                    break
            rows.append({"Scenario": pack["scenarios"][scenario].get("title", scenario), "Action": action,
                         "Result": "PASS" if result["passed"] else "FAIL"})
        progress.progress(1.0, text="Done")
        st.session_state.all_tests = rows
    if st.session_state.get("all_tests"):
        rows = st.session_state.all_tests
        passed = sum(r["Result"] == "PASS" for r in rows)
        (st.success if passed == len(rows) else st.warning)(f"{passed} of {len(rows)} tests passed.")
        st.dataframe(rows, hide_index=True, use_container_width=True)


def admin_tab(identity: dict[str, str], student: str) -> None:
    def call(method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
        return ls.admin_call(CFG["auth_url"], identity, signing_key(), method, path, body)

    st.subheader("Students")
    status, data = call("GET", "/_lab/internal/admin/students")
    rows = data.get("items", []) if status == 200 else []
    if status != 200:
        st.error(f"Could not list students: {data.get('error', status)}")
    else:
        st.dataframe(rows, hide_index=True, use_container_width=True,
                     column_order=["student", "email", "workspace", "active", "keys", "spend"])

    st.subheader("Set a student's password")
    st.write("Sets the password in FortiAIGate and stores the matching fallback sign-in hash, so both sign-in "
             "modes keep working. The student's existing lab sessions stay open until they expire.")
    with st.form("set-password", clear_on_submit=True):
        target = st.selectbox("Student", [r["student"] for r in rows] or CFG["students"])
        typed = st.text_input("New password (leave empty to generate one)", type="password")
        if st.form_submit_button("Set password"):
            password = typed or ls.generate_password()
            status, result = call("POST", "/_lab/internal/admin/password", {"student": target, "password": password})
            if status == 200:
                st.success(f"{result['email']}: FortiAIGate password reset; fallback {result['fallback']}.")
                if not typed:
                    st.write("Generated password (shown once):")
                    st.code(password, language=None)
                st.info(f"Update the instructor copy in .student-credentials/{target}.json; the portal cannot "
                        "write files on the deployment machine.")
            elif status == 422:
                st.error(f"{result['error']}: add {', '.join(result.get('missing', [])) or 'complexity'}.")
            else:
                st.error(f"Password not changed: {result.get('error', status)}")
            password = typed = None

    st.subheader(f"Keys for {student} compared with the instructor's seed")
    st.caption("Pick the student under Act as student in the sidebar.")
    try:
        current, seed = secret_store().load(student), secret_store().load_seed(student)
    except Exception as exc:  # RBAC or API failure
        st.error(f"Could not read key Secrets: {type(exc).__name__}")
        return
    if not seed:
        st.info("No seed is stored for this student. Redeploy the lab chatbot to write the seed Secrets.")
        return
    drift = ls.key_drift(current, seed)
    st.dataframe(drift, hide_index=True, use_container_width=True)
    restorable = [r["key"] for r in drift if r["status"] in ("changed", "missing (seed only)")]
    if not restorable:
        st.success("All keys match the seed.")
        return
    with st.form("restore-keys"):
        chosen = st.multiselect("Keys to restore from the seed", restorable, default=restorable)
        if st.form_submit_button("Restore selected keys") and chosen:
            try:
                secret_store().save(student, ls.restore_keys(current, seed, chosen))
                load_keys(student, force=True)
            except Exception as exc:
                st.error(f"Could not restore keys: {type(exc).__name__}")
            else:
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
            ctx = {"scenario": scenario, "action": action, "spec": spec, "key": key,
                   "path": path, "model": spec["model"], "system_prompt": spec.get("system_prompt", ""),
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
    names = ["Chat", "Tests", "Keys"] + (["Admin"] if identity["role"] == "admin" else [])
    tabs = st.tabs(names)
    with tabs[0]:
        chat_tab(ctx, entry)
    with tabs[1]:
        tests_tab(identity, keys, pack, ctx)
    with tabs[2]:
        keys_tab(identity, student, keys)
    if identity["role"] == "admin":
        with tabs[3]:
            admin_tab(identity, student)


main()
