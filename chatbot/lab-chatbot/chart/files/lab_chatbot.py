"""FortiAIGate 8.0.2 student lab chatbot (Streamlit).

Change 2026-11-19 (catalog switch; previous app kept in chatbot/lab-chatbot/legacy/):
- Scenarios, actions, prompts and tests come from the catalog student view
  (catalog-student.json, ConfigMap lab-catalog), not scenario-pack.json.
- Keys come from the gateway's key endpoints (lab_auth, lab-data/lab-keys),
  called with this app's caller token and the visitor's session handle. The
  app no longer reads or writes Kubernetes Secrets itself.
- Keys tab: refresh from FAIG, map each key to a scenario and action, paste a
  key value (checked against the key ID), hello-world, rotate.
- Tests are graded by the shared catalog evaluator from collected evidence and
  marker-matched Traffic Log rows (PASS / FAIL / KNOWN FAIL / INCOMPLETE).
- "Direct to LiteLLM" is a debug option: off by default and needs a
  confirmation; it bypasses FortiAIGate.
- The Admin tab keeps password resets and links to Lab Management (/manage/);
  the old seed comparison/restore is retired (seeded keys live in lab-keys).

The gateway signs the visitor's identity into X-Lab-* headers (display and
the Traffic Log/admin calls) and passes an opaque session handle (X-Lab-Session)
that authorizes key operations. Chat history lives only in the browser session.
"""
from __future__ import annotations

import os
from typing import Any

import streamlit as st

import faig_agent
import lab_catalog_chat as lc
import lab_support as ls
from catalog802.result_contract import evaluate
from catalog802.vocabulary import EVIDENCE, OUTCOMES, VERDICTS
from result_contract import contains_sensitive

CFG = {
    "signing_key_file": os.environ.get("LAB_SIGNING_KEY_FILE", "/etc/lab-chatbot/signing/hmac-key"),
    "caller_token_file": os.environ.get("LAB_CALLER_TOKEN_FILE", "/etc/lab-chatbot/caller/token"),
    "catalog_file": os.environ.get("LAB_CATALOG_FILE", "/catalog/catalog-student.json"),
    "faig_url": os.environ.get("LAB_FAIG_URL", "http://ingress-nginx-controller.ingress-nginx.svc.cluster.local/ai/openai/v1"),
    "direct_url": os.environ.get("LAB_DIRECT_URL", "http://litellm.litellm.svc.cluster.local:4000/v1"),
    "direct_key_file": os.environ.get("LAB_DIRECT_KEY_FILE", "/etc/lab-chatbot/direct/api-key"),
    "mcp_url": os.environ.get("LAB_MCP_URL", "http://mcp-demo.mcp.svc.cluster.local:8001/mcp"),
    "auth_url": os.environ.get("LAB_AUTH_URL", "http://demo-https-gateway-auth.demo-https-gateway.svc.cluster.local:8090"),
    "block_message": os.environ.get("LAB_BLOCK_MESSAGE",
                                    "This request was blocked by FortiAIGate as it triggered our safety systems."),
    "max_tokens": int(os.environ.get("LAB_MAX_TOKENS", "2048")),
    "temperature": float(os.environ.get("LAB_TEMPERATURE", "0.0")),
    "title": os.environ.get("LAB_TITLE", "FortiAIGate Lab Chatbot"),
}
PASSTHROUGH = "passthrough"


# ------------------------------------------------------------------ resources

@st.cache_resource
def signing_key() -> bytes:
    return ls.load_signing_key(CFG["signing_key_file"])


@st.cache_resource
def catalog() -> tuple[dict[str, Any], dict[str, Any], str | None]:
    return lc.load_view(CFG["catalog_file"])


def read_file(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def current_identity() -> dict[str, str] | None:
    """Verify the gateway headers once per browser session; keep the session handle."""
    if "identity" not in st.session_state:
        headers = {k.lower(): v for k, v in st.context.headers.items()}
        st.session_state.identity = ls.verify_identity(headers, signing_key())
        st.session_state.handle = headers.get("x-lab-session", "")
    return st.session_state.identity


def broker(path: str, body: dict | None = None, timeout: int = 60) -> tuple[int, Any]:
    return lc.broker(CFG["auth_url"], read_file(CFG["caller_token_file"]), st.session_state.get("handle", ""),
                     path, body, timeout)


def load_keys(student: str, force: bool = False) -> tuple[list[dict[str, Any]], str]:
    cache = st.session_state.setdefault("keys", {})
    if force or student not in cache:
        query = "" if st.session_state.identity["role"] == "student" else "?student=" + student
        status, data = broker("/_lab/internal/keys" + query)
        cache[student] = (data.get("keys", []), "") if status == 200 else ([], data.get("error", f"HTTP {status}"))
    return cache[student]


def student_list(identity: dict[str, str]) -> list[str]:
    if "students" not in st.session_state:
        status, data = ls.admin_call(CFG["auth_url"], identity, signing_key(), "GET", "/_lab/internal/admin/students")
        st.session_state.students = sorted({r["student"] for r in data.get("items", [])}) if status == 200 else []
    return st.session_state.students


def reset_chat() -> None:
    st.session_state.messages = []


def agent(spec: dict[str, Any]) -> dict[str, Any]:
    try:
        return faig_agent.run_turn_sync(spec)
    except Exception as exc:  # network or MCP transport failure; never echo the key
        return {"error": "agent_failed", "detail": type(exc).__name__, "reply": "", "tool_events": []}


# ------------------------------------------------------------------ chat

def render_turn(turn: dict[str, Any]) -> None:
    result = turn["result"]
    if result.get("error") == "http_error":
        body = (result.get("detail") or {}).get("error_body", "")
        st.error(f"HTTP {result.get('http_status')}: request failed (key, budget or upstream problem)")
        if body:
            st.code(body[:1500], language="json")
    elif result.get("error"):
        st.error(f"{result['error']}: {result.get('detail')}")
    else:
        st.markdown(result.get("reply") or "_(empty reply)_")
    events = result.get("tool_events") or []
    st.caption(f"{turn['path']} · key `{turn['key_name']}` · model `{turn['model']}`"
               + (f" · {len(events)} tool call(s)" if events else ""))
    if events:
        with st.expander("MCP tool calls"):
            for event in events:
                st.markdown(f"**{event['tool']}** {'(error)' if event.get('is_error') else ''}")
                st.json({"arguments": event.get("arguments"), "result": event.get("result")}, expanded=False)


def chat_tab(ctx: dict[str, Any] | None, scenario: dict[str, Any] | None) -> None:
    if scenario is None:
        st.info("No scenarios are available.")
        return
    if ctx is None:
        st.info("No key is mapped to this scenario and action yet. Open the **Keys** tab: refresh, then map a key "
                "you created in FortiAIGate and paste its value.")
        return
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if "turn" in message:
                render_turn(message["turn"])
            else:
                st.markdown(message["content"])
    prompts = scenario.get("prompts") or {}
    choices = [("Attack", p["text"]) for p in prompts.get("attack", [])] + \
              [("Clean", p["text"]) for p in prompts.get("clean", [])]
    if choices:
        with st.expander("Sample prompts"):
            for index, (kind, text) in enumerate(choices):
                if st.button(f"{kind}: {text[:110]}", key=f"sample-{index}", use_container_width=True):
                    st.session_state.pending_prompt = text
                    st.rerun()
    prompt = st.chat_input("Ask the scenario assistant...") or st.session_state.pop("pending_prompt", None)
    if prompt:
        history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
        st.session_state.messages.append({"role": "user", "content": prompt})
        spec = {"base_url": ctx["base_url"], "api_key": ctx["api_key"], "model": ctx["model"], "prompt": prompt,
                "system_prompt": ctx["system_prompt"], "history": history, "mcp_url": CFG["mcp_url"],
                "tools": ctx["tools"], "max_rounds": ctx["max_rounds"], "max_tokens": CFG["max_tokens"],
                "temperature": CFG["temperature"]}
        with st.spinner("Waiting for the model..."):
            result = agent(spec)
        turn = {"path": ctx["path"], "key_name": ctx["key_name"], "model": ctx["model"], "result": result}
        st.session_state.messages.append({"role": "assistant", "content": result.get("reply") or "", "turn": turn})
        st.rerun()


# ------------------------------------------------------------------ tests

def fetch_logs(identity: dict[str, str]):
    def fetch(**query: Any) -> tuple[int, Any]:
        return ls.internal_logs(CFG["auth_url"], identity, signing_key(), **query)
    return fetch


def run_test(identity: dict[str, str], scenario: dict[str, Any], test: dict[str, Any], key: dict[str, Any],
             plan: dict[str, Any] | None = None, grade=evaluate) -> dict[str, Any]:
    return lc.run_case(agent=agent, fetch_logs=fetch_logs(identity), evaluate=grade,
                       contains_sensitive=contains_sensitive, test=test, plan=plan or lc.plan_test(scenario, test),
                       key=key, faig_url=CFG["faig_url"], mcp_url=CFG["mcp_url"],
                       scenario_version=scenario.get("scenario_version", ""), block_message=CFG["block_message"],
                       max_tokens=CFG["max_tokens"], temperature=CFG["temperature"])


def render_result(result: dict[str, Any]) -> None:
    outcome = result["outcome"]
    verdict = f"FortiAIGate verdict: {VERDICTS.get(result['verdict'], result['verdict'])}"
    if outcome == "observed":  # ungraded prompt probe (Change 2026-11-19)
        st.info(f"{verdict} · {result.get('requests_sent') or 0} request(s) · not graded")
    else:
        show = {"pass": st.success, "fail": st.error, "known-fail": st.warning, "incomplete": st.info}[outcome]
        show(f"{OUTCOMES.get(outcome, outcome)} · {verdict} · {result.get('requests_sent') or 0} request(s)")
    if result.get("reply"):
        st.markdown("**Reply:** " + result["reply"][:2000])
    if result["evidence"]:
        st.write("Evidence: " + ", ".join(EVIDENCE.get(e, e) for e in result["evidence"]))
    for reason in result["reasons"]:
        st.write("- " + reason)
    if result.get("log_error"):
        st.caption(f"Traffic Log not available here ({result['log_error']}); student sign-ins can read their own "
                   "workspace log. Missing log rows make a test INCOMPLETE, never PASS.")
    exchanges, entries = result.get("exchanges", []), result.get("log_entries", [])
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
            # A bare conditional expression is echoed by Streamlit "magic"; use a statement.
            if index < len(entries):
                st.json(entries[index], expanded=2)
            else:
                st.caption("No matched entry.")


def try_prompt(identity: dict[str, str], scenario: dict[str, Any], action: str, key: dict[str, Any] | None) -> None:
    """Send any catalog prompt (or a typed one) through the action's key and show what FortiAIGate did.

    Change 2026-11-19: ungraded probe; shows the matching catalog test's expectation when there is one."""
    st.subheader("Try a prompt")
    if key is None:
        st.info("Map a key to this scenario and action in the Keys tab to send prompts through it.")
        return
    sid = scenario["id"]
    choices = lc.prompt_choices(scenario)
    source = st.radio("Prompt", ["catalog", "own"] if choices else ["own"], horizontal=True, key=f"probe-src-{sid}",
                      format_func=lambda s: "Catalog prompt" if s == "catalog" else "Write my own")
    prompt_id = None
    if source == "catalog":
        by_id = {c["id"]: c for c in choices}
        prompt_id = st.selectbox("Catalog prompt", list(by_id), key=f"probe-prompt-{sid}",
                                 format_func=lambda i: f"{by_id[i]['group'].title()} · {by_id[i]['text'][:100]}")
        text = by_id[prompt_id]["text"]
        st.caption(text)
    else:
        text = st.text_area("Your prompt", key=f"probe-text-{sid}", height=100)
    compromised = bool(scenario.get("frontend_instruction")) and st.checkbox(
        scenario.get("frontend_instruction_label") or "Simulate compromised frontend", key=f"probe-comp-{sid}",
        help=scenario.get("frontend_instruction_description") or "")
    related = lc.related_tests(scenario, action, prompt_id, compromised)
    if related:
        expect = related[0]["expect"]["verdict"]
        st.caption(f"Catalog test **{related[0]['id']}** sends this prompt with this key and expects "
                   f"**{VERDICTS.get(expect, expect)}**. Use Run one test above for a graded run.")
    else:
        st.caption(f"No catalog test sends this prompt for {lc.action_label(scenario, action)}; the result is "
                   "shown but not graded.")
    st.caption(f"Key: `{key['key_name']}`")
    if st.button("Send prompt", disabled=not text.strip()):
        stub, plan = lc.probe_plan(scenario, action, text.strip(), compromised, prompt_id)
        with st.spinner("Sending the prompt and waiting for the Traffic Log..."):
            result = run_test(identity, scenario, stub, key, plan, grade=lc.observe)
        st.session_state.probe = {"where": (sid, action, key["key_name"]), "result": result}
    last = st.session_state.get("probe")
    if last and last["where"] == (sid, action, key["key_name"]):
        render_result(last["result"])


def tests_tab(identity: dict[str, str], scenarios: dict[str, Any], keys: list[dict[str, Any]],
              scenario: dict[str, Any] | None, action: str) -> None:
    if scenario is None:
        return
    key = lc.mapped_key(keys, scenario["id"], action)
    tests = lc.tests_for(scenario, action)
    st.subheader("Run one test")
    if key is None:
        st.info("Map a key to this scenario and action in the Keys tab to run its tests.")
    elif not tests:
        st.info("This action has no catalog tests.")
    else:
        labels = {t["id"]: t["id"] + (" (compromised frontend)" if t.get("frontend_instruction") == "compromised" else "")
                  for t in tests}
        # Change 2026-11-19: the sidebar already picks scenario/action; only offer a choice when the action
        # has more than one test.
        if len(tests) == 1:
            test_id = tests[0]["id"]
            st.markdown(f"Test: **{labels[test_id]}**")
        else:
            test_id = st.radio("Test", list(labels), format_func=labels.get, horizontal=True,
                               key=f"test-{scenario['id']}-{action}")
        test = next(t for t in tests if t["id"] == test_id)
        plan = lc.plan_test(scenario, test)
        expect = test["expect"]
        st.markdown(f"- Key: `{key['key_name']}`\n- Prompt: _{plan['prompt']}_\n"
                    f"- Expected verdict: **{VERDICTS.get(expect['verdict'], expect['verdict'])}**"
                    + (f"\n- Must show: {', '.join(EVIDENCE[e] for e in expect['evidence_present'])}"
                       if expect["evidence_present"] else "")
                    + (f"\n- Must not show: {', '.join(EVIDENCE[e] for e in expect['evidence_absent'])}"
                       if expect["evidence_absent"] else ""))
        if st.button("Run this test", type="primary"):
            with st.spinner("Running the test and waiting for the Traffic Log..."):
                st.session_state.single_test = run_test(identity, scenario, test, key, plan)
        last = st.session_state.get("single_test")
        if last and last.get("test") == test_id and last.get("key_name") == key["key_name"]:
            render_result(last)

    st.divider()
    try_prompt(identity, scenario, action, key)

    st.divider()
    st.subheader("Run all tests")
    # Change 2026-11-19: default to the scenario selected in the sidebar.
    scope = st.radio("Scope", ["selected", "all"], horizontal=True, key="run-all-scope",
                     format_func=lambda s: f"{scenario['display_name']} (all actions)" if s == "selected"
                     else "All scenarios")
    st.write("Runs every catalog test for each action in scope that has a mapped key. A failed test is retried once "
             "(model answers vary).")
    if st.button("Run all tests"):
        chosen = {scenario["id"]: scenario} if scope == "selected" else scenarios
        plan = [(s, t, lc.mapped_key(keys, sid, t["action"])) for sid, s in chosen.items()
                for t in s.get("tests", []) if lc.mapped_key(keys, sid, t["action"])]
        progress, rows = st.progress(0.0, text="Starting..."), []
        for index, (s, test, key) in enumerate(plan):
            progress.progress(index / max(len(plan), 1), text=f"{s['display_name']} / {test['id']}")
            for _attempt in range(2):
                result = run_test(identity, s, test, key)
                if result["outcome"] in ("pass", "known-fail"):
                    break
            rows.append({"Scenario": s["display_name"], "Action": lc.action_label(s, test["action"]),
                         "Test": test["id"], "Result": OUTCOMES.get(result["outcome"], result["outcome"]),
                         "Verdict": VERDICTS.get(result["verdict"], result["verdict"]),
                         "Notes": "; ".join(result["reasons"])})
        progress.progress(1.0, text="Done")
        st.session_state.all_tests = rows
    rows = st.session_state.get("all_tests")
    if rows:
        passed = sum(r["Result"] in ("PASS", "KNOWN FAIL") for r in rows)
        (st.success if passed == len(rows) else st.warning)(f"{passed} of {len(rows)} passed or known.")
        st.dataframe(rows, hide_index=True, use_container_width=True)
    elif rows == []:
        st.info("No mapped keys with tests yet.")


# ------------------------------------------------------------------ keys

def keys_tab(identity: dict[str, str], student: str, scenarios: dict[str, Any], platform: dict[str, Any],
             keys: list[dict[str, Any]], error: str) -> None:
    own = identity["role"] == "student"
    st.write("Create keys in the FortiAIGate portal, then **Refresh** here. Map each key to the scenario and action "
             "its policy is for, and paste its value (FortiAIGate shows it only once). The lab expects one key → one "
             "policy → one model.")
    if error:
        st.error(f"Keys unavailable: {error}")
    if own and st.button("Refresh from FortiAIGate"):
        status, data = broker("/_lab/internal/keys/refresh", {})
        if status == 200:
            load_keys(student, force=True)
            st.rerun()
        st.error(f"Refresh failed: {data.get('error', status)}")
    if not own:
        st.caption(f"Read-only view of {student}'s keys (Act as student).")
    if not keys:
        st.info("No keys yet.")
        return
    st.dataframe(lc.public_rows(keys), hide_index=True, use_container_width=True)
    if not own:
        return
    by_name = {k.get("key_name") or k["faig_key_id"]: k for k in keys if k.get("status") != "missing"}

    st.markdown("**Map a key**")
    scenario_ids = list(scenarios) + [PASSTHROUGH]
    name = st.selectbox("Key", list(by_name), key="map-key-name")
    sid = st.selectbox("Scenario", scenario_ids, key="map-scenario",
                       format_func=lambda s: "Passthrough (no policy)" if s == PASSTHROUGH else scenarios[s]["display_name"])
    actions = [PASSTHROUGH] if sid == PASSTHROUGH else [a["id"] for a in scenarios[sid]["actions"]]
    action = st.selectbox("Action", actions, key="map-action",
                          format_func=lambda a: a if sid == PASSTHROUGH else lc.action_label(scenarios[sid], a))
    value = st.text_input("Key value (optional; paste it when you create or rotate the key)", type="password",
                          key="map-value")
    if st.button("Save mapping"):
        expected = (platform.get("passthrough_model") or {}).get("backend_alias", "") if sid == PASSTHROUGH \
            else lc.model_for(scenarios[sid], action).get("backend_alias", "")
        body = {"faig_key_id": by_name[name]["faig_key_id"], "scenario_id": sid, "action": action,
                "expected_model": expected}
        if value.strip():
            body["secret"] = value.strip()
        status, data = broker("/_lab/internal/keys/map", body)
        body = value = None
        if status == 200:
            load_keys(student, force=True)
            st.success("Saved.")
            for warning in data.get("warnings", []):
                st.warning(warning)
        else:
            st.error(f"Not saved: {data.get('error', status)}")

    st.markdown("**Hello-world**")
    st.caption("Sends a harmless prompt through the key's own policy and model. A pass means the key works and "
               "FortiAIGate logged it with a Log verdict (no false positive).")
    ready = {n: k for n, k in by_name.items() if k.get("secret")}
    if ready:
        target = st.selectbox("Key to check", list(ready), key="hello-key")
        if st.button("Run hello-world"):
            key = ready[target]
            hello = platform.get("hello_world") or {}
            plan = {"prompt": hello.get("prompt", "Reply with exactly: Hello."), "system_prompt": "", "tools": [],
                    "max_rounds": 0, "model": key.get("model", "")}
            with st.spinner("Checking the key..."):
                result = lc.run_case(agent=agent, fetch_logs=fetch_logs(identity), evaluate=evaluate,
                                     contains_sensitive=contains_sensitive, test=lc.hello_world_test(platform),
                                     plan=plan, key=key, faig_url=CFG["faig_url"], mcp_url=CFG["mcp_url"],
                                     scenario_version="", block_message=CFG["block_message"],
                                     max_tokens=CFG["max_tokens"], temperature=CFG["temperature"])
            broker("/_lab/internal/keys/status", {"faig_key_id": key["faig_key_id"], "status": lc.key_status_for(result)})
            load_keys(student, force=True)
            render_result(result)
            st.write("Reply: " + (result.get("reply") or "_(empty)_"))
    else:
        st.caption("No key has a stored value yet.")

    st.markdown("**Rotate a key**")
    st.caption("Creates a new value in FortiAIGate and stores it here. The old value stops working within about a "
               "minute.")
    with st.form("rotate-key"):
        target = st.selectbox("Key to rotate", list(by_name), key="rotate-key-name")
        sure = st.checkbox("I understand the current value will stop working")
        if st.form_submit_button("Rotate") and sure:
            status, data = broker("/_lab/internal/keys/rotate", {"faig_key_id": by_name[target]["faig_key_id"]},
                                  timeout=90)
            load_keys(student, force=True)
            if status == 200 and data.get("saved"):
                st.success("Rotated and stored.")
            elif status == 200:
                st.warning("Rotated, but the new value could not be stored. Copy it now; it is shown only once, "
                           "then paste it with Map a key:")
                st.code(data.get("secret_once", ""), language=None)
            else:
                st.error(f"Rotation: {data.get('error', status)}")


# ------------------------------------------------------------------ admin

def admin_tab(identity: dict[str, str]) -> None:
    st.markdown("Students, scenarios, prepopulation and the share page are in "
                "**[Lab Management](/manage/)**.")

    def call(method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
        return ls.admin_call(CFG["auth_url"], identity, signing_key(), method, path, body)

    st.subheader("Set a student's password")
    st.write("Sets the password in FortiAIGate and the matching fallback sign-in hash.")
    with st.form("set-password", clear_on_submit=True):
        target = st.selectbox("Student", student_list(identity))
        typed = st.text_input("New password (leave empty to generate one)", type="password")
        if st.form_submit_button("Set password") and target:
            password = typed or ls.generate_password()
            status, result = call("POST", "/_lab/internal/admin/password", {"student": target, "password": password})
            if status == 200:
                st.success(f"{result['email']}: FortiAIGate password reset; fallback {result['fallback']}.")
                if not typed:
                    st.write("Generated password (shown once):")
                    st.code(password, language=None)
                st.info("Lab Management's share page still shows the previous stored password until it is "
                        "re-imported; update it there.")
            elif status == 422:
                st.error(f"{result['error']}: add {', '.join(result.get('missing', [])) or 'complexity'}.")
            else:
                st.error(f"Password not changed: {result.get('error', status)}")
            password = typed = None


# ------------------------------------------------------------------ page

def main() -> None:
    st.set_page_config(page_title=CFG["title"], page_icon=":shield:", layout="wide")
    identity = current_identity()
    if not identity:
        st.error("Your lab session could not be verified. Open the chatbot through the lab URL and sign in again.")
        st.markdown("[Sign in](/_lab/login)")
        return
    st.session_state.setdefault("messages", [])
    scenarios, platform, catalog_error = catalog()

    with st.sidebar:
        st.markdown(f"**{identity['user']}**  \n{identity['role']}"
                    + (f" · {identity['student']}" if identity["student"] else ""))
        if identity["role"] == "admin":
            students = student_list(identity)
            if not students:
                st.warning("No students yet. Create them in [Lab Management](/manage/).")
                return
            student = st.selectbox("Act as student", students, on_change=reset_chat)
        else:
            student = identity["student"]
        keys, key_error = load_keys(student)
        if catalog_error:
            st.error(catalog_error)
            return
        sid = st.selectbox("Scenario", list(scenarios), on_change=reset_chat,
                           format_func=lambda s: scenarios[s]["display_name"])
        scenario = scenarios[sid]
        action = st.selectbox("Action", [a["id"] for a in scenario["actions"]], on_change=reset_chat,
                              format_func=lambda a: lc.action_label(scenario, a))
        for block in scenario.get("learning", []):
            if block.get("type") == "text":
                st.caption(block.get("content", ""))
        key = lc.mapped_key(keys, sid, action)
        model = lc.model_for(scenario, action).get("public_name", "")

        with st.expander("Debug options"):
            direct = st.checkbox("Send directly to LiteLLM (bypasses FortiAIGate)", on_change=reset_chat)
            confirmed = direct and st.checkbox("I understand nothing is inspected or logged by FortiAIGate",
                                               on_change=reset_chat)
            compromised = False
            if scenario.get("frontend_instruction"):
                compromised = st.checkbox(scenario.get("frontend_instruction_label") or "Simulate compromised frontend",
                                          help=scenario.get("frontend_instruction_description") or "",
                                          on_change=reset_chat)
        use_direct = bool(direct and confirmed)
        ctx = None
        if use_direct or key:
            ctx = {"path": "Direct to LiteLLM (debug)" if use_direct else "FortiAIGate", "model": model,
                   "system_prompt": scenario.get("frontend_instruction", "") if compromised else "",
                   "tools": list(scenario.get("tools", [])), "max_rounds": scenario.get("max_rounds", 3),
                   "base_url": CFG["direct_url"] if use_direct else CFG["faig_url"],
                   "api_key": read_file(CFG["direct_key_file"]) if use_direct else key["secret"],
                   "key_name": "shared LiteLLM lab key" if use_direct else key["key_name"]}
            if use_direct and not ctx["api_key"]:
                st.warning("The shared LiteLLM key is not mounted; Direct mode is unavailable.")
                ctx = None
        if ctx:
            st.caption(f"Key: `{ctx['key_name']}`" + ("" if use_direct else f" ({ls.mask(ctx['api_key'])})"))
        elif key_error:
            st.warning(f"Keys unavailable: {key_error}")
        if scenario.get("tools"):
            st.caption("MCP tools: " + ", ".join(scenario["tools"]))
        if st.button("Clear chat"):
            reset_chat()
            st.rerun()
        if st.button("Reload keys"):
            load_keys(student, force=True)
            st.rerun()
        if identity["role"] == "admin":
            st.markdown("[Lab Management](/manage/)")
        st.markdown("[Sign out](/_lab/logout)")

    st.title(CFG["title"])
    names = ["Chat", "Tests", "Keys"] + (["Admin"] if identity["role"] == "admin" else [])
    tabs = st.tabs(names)
    with tabs[0]:
        chat_tab(ctx, scenario)
    with tabs[1]:
        tests_tab(identity, scenarios, keys, scenario, action)
    with tabs[2]:
        keys_tab(identity, student, scenarios, platform, keys, key_error)
    if identity["role"] == "admin":
        with tabs[3]:
            admin_tab(identity)


main()
