import logging
import os
import json
from typing import Any, Iterable

import httpx
import streamlit as st
from openai import OpenAI


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_csv(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name, "")
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or default


def env_json_list(name: str) -> list[dict[str, Any]]:
    value = os.getenv(name, "").strip()
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{name} is not valid JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise RuntimeError(f"{name} must be a JSON list")
    routes = []
    for item in parsed:
        if not isinstance(item, dict):
            raise RuntimeError(f"{name} entries must be JSON objects")
        route_name = str(item.get("name", "")).strip()
        if not route_name:
            raise RuntimeError(f"{name} entries require a non-empty name")
        routes.append(item)
    return routes


def join_base_path(base_url: str, base_path: str) -> str:
    clean_base = base_url.rstrip("/")
    clean_path = (base_path or "/v1").strip()
    return f"{clean_base}/{clean_path.lstrip('/')}"


def build_faig_routes(
    default_route: str,
    routes_json: list[dict[str, Any]],
    default_base_path: str,
) -> list[dict[str, Any]]:
    routes = routes_json or [{"name": default_route, "base_path": default_base_path, "model": default_route}]
    normalized_routes = []
    for route in routes:
        normalized_route = dict(route)
        name = str(normalized_route.get("name", "")).strip()
        if not name:
            raise RuntimeError("FortiAIGate routes require a non-empty name")
        normalized_route["name"] = name
        normalized_route["label"] = str(normalized_route.get("label") or name).strip()
        normalized_route["model"] = str(normalized_route.get("model") or name).strip()
        normalized_route["base_path"] = str(normalized_route.get("base_path") or default_base_path).strip()
        normalized_routes.append(normalized_route)

    route_names = [route["name"] for route in normalized_routes]
    if default_route and default_route not in route_names:
        normalized_routes.insert(
            0,
            {
                "name": default_route,
                "label": default_route,
                "base_path": default_base_path,
                "model": default_route,
            },
        )
    return normalized_routes


def route_headers(route: dict[str, Any]) -> dict[str, str]:
    raw_headers = route.get("headers") or {}
    if not isinstance(raw_headers, dict):
        raise RuntimeError("FortiAIGate route headers must be a JSON object")
    return {str(key): str(value) for key, value in raw_headers.items()}


def apply_faig_static_route(base_url: str, route: dict[str, Any]) -> tuple[str, str, dict[str, str]]:
    routed_base_url = join_base_path(base_url, str(route.get("base_path") or "/v1/default"))
    routed_model = str(route.get("model") or route.get("name") or "auto").strip()
    return routed_base_url, routed_model, route_headers(route)


def apply_faig_header_route(
    base_url: str,
    route: dict[str, Any],
    header_name: str,
) -> tuple[str, str, dict[str, str]]:
    routed_base_url = join_base_path(base_url, str(route.get("base_path") or "/v1/intelligent"))
    routed_model = str(route.get("model") or route.get("name") or "auto").strip()
    headers = route_headers(route)

    if header_name:
        if "header_value" in route:
            header_value = str(route.get("header_value") or "").strip()
        else:
            header_value = routed_model
        if header_value:
            headers[header_name] = header_value
    return routed_base_url, routed_model, headers


def stream_response(
    base_url: str,
    api_key: str,
    model: str,
    system_instruction: str | None,
    user_input: str,
    temperature: float,
    max_tokens: int,
    verify_tls: bool,
    extra_headers: dict[str, str] | None = None,
) -> Iterable[str]:
    http_client = httpx.Client(verify=verify_tls)
    client = OpenAI(
        api_key=api_key or "not-used",
        base_url=base_url,
        http_client=http_client,
        default_headers=extra_headers or None,
    )
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": user_input})
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )

    for chunk in response:
        content = chunk.choices[0].delta.content
        if content:
            yield content


def single_response(
    base_url: str,
    api_key: str,
    model: str,
    system_instruction: str | None,
    user_input: str,
    temperature: float,
    max_tokens: int,
    verify_tls: bool,
    extra_headers: dict[str, str] | None = None,
) -> str:
    http_client = httpx.Client(verify=verify_tls)
    client = OpenAI(
        api_key=api_key or "not-used",
        base_url=base_url,
        http_client=http_client,
        default_headers=extra_headers or None,
    )
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": user_input})
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


def fetch_mcp_tools(
    base_url: str,
    timeout_seconds: int,
    verify_tls: bool,
) -> list[dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/tools"
    with httpx.Client(verify=verify_tls, timeout=timeout_seconds) as client:
        response = client.get(url)
        response.raise_for_status()
        data = response.json()
    tools = data.get("tools", [])
    if not isinstance(tools, list):
        raise RuntimeError("MCP tools endpoint did not return a tools list")
    return tools


def call_mcp_tool(
    base_url: str,
    tool_name: str,
    arguments: dict[str, Any],
    timeout_seconds: int,
    verify_tls: bool,
) -> dict:
    url = f"{base_url.rstrip('/')}/mcp"
    payload = {"tool": tool_name, "arguments": arguments}
    with httpx.Client(verify=verify_tls, timeout=timeout_seconds) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("result", {}).get("error", "MCP tool returned ok=false"))
    return data.get("result", {})


def tool_call_to_message(tool_call: Any) -> dict[str, Any]:
    return {
        "id": tool_call.id,
        "type": "function",
        "function": {
            "name": tool_call.function.name,
            "arguments": tool_call.function.arguments or "{}",
        },
    }


def parse_tool_arguments(raw_arguments: str) -> dict[str, Any]:
    if not raw_arguments:
        return {}
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM returned invalid tool arguments JSON: {exc}") from exc
    if not isinstance(arguments, dict):
        raise RuntimeError("LLM returned tool arguments that were not a JSON object")
    return arguments


def agent_response(
    base_url: str,
    api_key: str,
    model: str,
    system_instruction: str | None,
    user_input: str,
    temperature: float,
    max_tokens: int,
    verify_tls: bool,
    mcp_base_url: str,
    mcp_timeout_seconds: int,
    mcp_verify_tls: bool,
    max_tool_rounds: int,
    extra_headers: dict[str, str] | None = None,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    tools = fetch_mcp_tools(mcp_base_url, mcp_timeout_seconds, mcp_verify_tls)
    tool_names = [
        tool.get("function", {}).get("name", "unknown")
        for tool in tools
        if isinstance(tool, dict)
    ]

    http_client = httpx.Client(verify=verify_tls)
    client = OpenAI(
        api_key=api_key or "not-used",
        base_url=base_url,
        http_client=http_client,
        default_headers=extra_headers or None,
    )

    messages: list[dict[str, Any]] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": user_input})

    tool_events: list[dict[str, Any]] = []
    for _round in range(max_tool_rounds):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=temperature,
            max_tokens=max_tokens,
        )
        message = response.choices[0].message
        tool_calls = message.tool_calls or []
        if not tool_calls:
            return message.content or "", tool_events, tools

        messages.append(
            {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [tool_call_to_message(tool_call) for tool_call in tool_calls],
            }
        )

        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            arguments = parse_tool_arguments(tool_call.function.arguments or "{}")
            result = call_mcp_tool(mcp_base_url, tool_name, arguments, mcp_timeout_seconds, mcp_verify_tls)
            tool_events.append({"tool": tool_name, "arguments": arguments, "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, sort_keys=True),
                }
            )

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    final_content = response.choices[0].message.content or ""
    if not final_content:
        final_content = (
            "The model reached the configured MCP tool round limit "
            f"({max_tool_rounds}) without returning a final answer."
        )
    logger.info("MCP tools made available to model: %s", ", ".join(tool_names))
    return final_content, tool_events, tools


def main() -> None:
    direct_base_url = os.getenv("CHATBOT_DIRECT_BASE_URL", "").strip()
    direct_api_key = os.getenv("CHATBOT_DIRECT_API_KEY", "not-used")
    faig_base_url = os.getenv("CHATBOT_FAIG_BASE_URL", "").strip()
    faig_api_key = os.getenv("CHATBOT_FAIG_API_KEY", "not-used")
    model = os.getenv("CHATBOT_MODEL", "auto")
    model_options = env_csv("CHATBOT_MODEL_OPTIONS", [model])
    if model not in model_options:
        model_options.insert(0, model)
    page_title = os.getenv("CHATBOT_PAGE_TITLE", "AI Chatbot")
    header_title = os.getenv("CHATBOT_HEADER_TITLE", page_title)
    frontend_system_prompt = os.getenv("CHATBOT_FRONTEND_SYSTEM_PROMPT", "").strip()
    temperature = env_float("CHATBOT_TEMPERATURE", 0.0)
    max_tokens = env_int("CHATBOT_MAX_TOKENS", 4096)
    streaming = env_bool("CHATBOT_STREAMING", False)
    verify_tls = env_bool("CHATBOT_VERIFY_TLS", False)
    mcp_enabled_default = env_bool("CHATBOT_MCP_ENABLED", False)
    mcp_direct_base_url = os.getenv("CHATBOT_MCP_DIRECT_BASE_URL", "").strip()
    mcp_fortiweb_base_url = os.getenv("CHATBOT_MCP_FORTIWEB_BASE_URL", "").strip()
    mcp_default_path = os.getenv("CHATBOT_MCP_DEFAULT_PATH", "direct").strip().lower()
    if mcp_default_path not in {"direct", "fortiweb"}:
        logger.warning("Invalid CHATBOT_MCP_DEFAULT_PATH=%s; using direct", mcp_default_path)
        mcp_default_path = "direct"
    if mcp_default_path == "fortiweb" and not mcp_fortiweb_base_url:
        logger.warning("CHATBOT_MCP_DEFAULT_PATH=fortiweb but CHATBOT_MCP_FORTIWEB_BASE_URL is empty; using direct")
        mcp_default_path = "direct"
    mcp_timeout_seconds = env_int("CHATBOT_MCP_TIMEOUT_SECONDS", 10)
    mcp_verify_tls = env_bool("CHATBOT_MCP_VERIFY_TLS", False)
    mcp_max_tool_rounds = env_int("CHATBOT_MCP_MAX_TOOL_ROUNDS", 3)
    faig_static_default_route = os.getenv("CHATBOT_FAIG_STATIC_ROUTE", "demo-a").strip() or "demo-a"
    faig_static_routes = build_faig_routes(
        faig_static_default_route,
        env_json_list("CHATBOT_FAIG_STATIC_ROUTES_JSON"),
        f"/v1/{faig_static_default_route}",
    )
    faig_header_default_route = os.getenv("CHATBOT_FAIG_HEADER_ROUTE", "demo-a").strip() or "demo-a"
    faig_header_routes = build_faig_routes(
        faig_header_default_route,
        env_json_list("CHATBOT_FAIG_HEADER_ROUTES_JSON"),
        "/v1/intelligent",
    )
    faig_model_route_header_name = os.getenv("CHATBOT_FAIG_MODEL_ROUTE_HEADER_NAME", "X-FAIG-Model-Route").strip()

    st.set_page_config(page_title=page_title, layout="centered")
    st.title(header_title)

    with st.sidebar:
        st.subheader("Backend")
        provider_path = st.radio(
            "Path",
            ["Direct LiteLLM", "FAIG Static Route", "FAIG Intelligent Route"],
            index=0,
            help="Direct sends to LiteLLM. FAIG static uses URI paths. FAIG intelligent uses one URI plus a routing header.",
        )
        route_headers: dict[str, str] = {}
        if provider_path == "Direct LiteLLM":
            base_url = direct_base_url
            api_key = direct_api_key
            selected_model = st.selectbox(
                "LLM profile",
                model_options,
                index=model_options.index(model),
                help="Select an LLM instruction profile. Different profiles can inject different backend instructions.",
            )
            st.write("Backend instructions: LiteLLM profile")
        elif provider_path == "FAIG Static Route":
            route_names = [route["name"] for route in faig_static_routes]
            route_labels = {route["name"]: route["label"] for route in faig_static_routes}
            route_index = route_names.index(faig_static_default_route) if faig_static_default_route in route_names else 0
            selected_route_name = st.selectbox(
                "LLM profile",
                route_names,
                index=route_index,
                format_func=lambda route_name: route_labels.get(route_name, route_name),
                help="Select an LLM instruction profile. FAIG static routing uses the selected profile to construct the route-specific URI path.",
            )
            selected_route = next(route for route in faig_static_routes if route["name"] == selected_route_name)
            base_url, selected_model, route_headers = apply_faig_static_route(faig_base_url, selected_route)
            api_key = faig_api_key
            st.write("Backend routing: FAIG URI path")
            st.write(f"Selected LLM profile: `{selected_model}`")
            st.write(f"Route endpoint: `{base_url}`")
        else:
            route_names = [route["name"] for route in faig_header_routes]
            route_labels = {route["name"]: route["label"] for route in faig_header_routes}
            route_index = route_names.index(faig_header_default_route) if faig_header_default_route in route_names else 0
            selected_route_name = st.selectbox(
                "LLM profile",
                route_names,
                index=route_index,
                format_func=lambda route_name: route_labels.get(route_name, route_name),
                help="Select an LLM instruction profile. FAIG intelligent routing sends the selected profile as route metadata.",
            )
            selected_route = next(route for route in faig_header_routes if route["name"] == selected_route_name)
            base_url, selected_model, route_headers = apply_faig_header_route(
                faig_base_url,
                selected_route,
                faig_model_route_header_name,
            )
            api_key = faig_api_key
            st.write("Backend routing: FAIG intelligent")
            st.write(f"Selected LLM profile: `{selected_model}`")
            st.write(f"Route endpoint: `{base_url}`")
            if route_headers:
                st.write(
                    "Route header: "
                    + ", ".join([f"`{key}: {value}`" for key, value in route_headers.items()])
                )
            else:
                st.write("Route header: none")
        st.write(f"Streaming: {'on' if streaming else 'off'}")
        st.subheader("MCP Tools")
        mcp_enabled = st.checkbox("Use MCP tools", value=mcp_enabled_default)
        mcp_path_options = ["Direct MCP"]
        if mcp_fortiweb_base_url:
            mcp_path_options.append("FortiWeb MCP")
        mcp_path_index = 0
        if mcp_default_path == "fortiweb" and "FortiWeb MCP" in mcp_path_options:
            mcp_path_index = 1
        mcp_path = st.radio("MCP path", mcp_path_options, index=mcp_path_index, disabled=not mcp_enabled)
        mcp_base_url = mcp_direct_base_url if mcp_path == "Direct MCP" else mcp_fortiweb_base_url
        mcp_max_tool_rounds = st.number_input(
            "Max tool rounds",
            min_value=1,
            max_value=8,
            value=mcp_max_tool_rounds,
            step=1,
            disabled=not mcp_enabled,
        )
        if mcp_enabled:
            st.write(f"MCP endpoint: `{mcp_base_url or 'not configured'}`")
            st.write("Tool choice: model-selected")
            if streaming:
                st.write("Streaming: off while MCP tools are enabled")

    if not base_url:
        st.error(f"{provider_path} base URL is not configured.")
        return
    if mcp_enabled and not mcp_base_url:
        st.error(f"{mcp_path} base URL is not configured.")
        return

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"], unsafe_allow_html=True)

    left, right = st.columns([6, 1])
    with right:
        if st.button("Clear"):
            st.session_state.messages = []
            st.rerun()

    user_input = st.chat_input("Say something...")
    if not user_input:
        return

    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input, unsafe_allow_html=True)

    with st.chat_message("assistant"):
        try:
            if mcp_enabled:
                reply, tool_events, tools = agent_response(
                    base_url,
                    api_key,
                    selected_model,
                    frontend_system_prompt or None,
                    user_input,
                    temperature,
                    max_tokens,
                    verify_tls,
                    mcp_base_url,
                    mcp_timeout_seconds,
                    mcp_verify_tls,
                    mcp_max_tool_rounds,
                    route_headers,
                )
                tool_names = [
                    tool.get("function", {}).get("name", "unknown")
                    for tool in tools
                    if isinstance(tool, dict)
                ]
                with st.expander("MCP tool loop", expanded=bool(tool_events)):
                    st.write(f"Path: {mcp_path}")
                    st.write(f"Available tools: {', '.join(tool_names)}")
                    if tool_events:
                        for index, event in enumerate(tool_events, start=1):
                            st.write(f"Tool call {index}: `{event['tool']}`")
                            st.write("Arguments")
                            st.json(event["arguments"])
                            st.write("Result")
                            st.json(event["result"])
                    else:
                        st.write("The model did not request a tool call for this message.")
                st.markdown(reply, unsafe_allow_html=True)
            elif streaming:
                reply = st.write_stream(
                    stream_response(
                        base_url,
                        api_key,
                        selected_model,
                        frontend_system_prompt or None,
                        user_input,
                        temperature,
                        max_tokens,
                        verify_tls,
                        route_headers,
                    )
                )
            else:
                reply = single_response(
                    base_url,
                    api_key,
                    selected_model,
                    frontend_system_prompt or None,
                    user_input,
                    temperature,
                    max_tokens,
                    verify_tls,
                    route_headers,
                )
                st.markdown(reply, unsafe_allow_html=True)
        except Exception as error:
            reply = f"Request failed: {error}"
            st.error(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    main()
