import logging
import os
from typing import Iterable

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


def stream_response(
    base_url: str,
    api_key: str,
    model: str,
    system_instruction: str | None,
    user_input: str,
    temperature: float,
    max_tokens: int,
    verify_tls: bool,
) -> Iterable[str]:
    http_client = httpx.Client(verify=verify_tls)
    client = OpenAI(api_key=api_key or "not-used", base_url=base_url, http_client=http_client)
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
) -> str:
    http_client = httpx.Client(verify=verify_tls)
    client = OpenAI(api_key=api_key or "not-used", base_url=base_url, http_client=http_client)
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


def main() -> None:
    direct_base_url = os.getenv("CHATBOT_DIRECT_BASE_URL", "").strip()
    direct_api_key = os.getenv("CHATBOT_DIRECT_API_KEY", "not-used")
    faig_base_url = os.getenv("CHATBOT_FAIG_BASE_URL", "").strip()
    faig_api_key = os.getenv("CHATBOT_FAIG_API_KEY", "not-used")
    model = os.getenv("CHATBOT_MODEL", "auto")
    page_title = os.getenv("CHATBOT_PAGE_TITLE", "AI Chatbot")
    header_title = os.getenv("CHATBOT_HEADER_TITLE", page_title)
    frontend_system_prompt = os.getenv("CHATBOT_FRONTEND_SYSTEM_PROMPT", "").strip()
    temperature = env_float("CHATBOT_TEMPERATURE", 0.0)
    max_tokens = env_int("CHATBOT_MAX_TOKENS", 4096)
    streaming = env_bool("CHATBOT_STREAMING", False)
    verify_tls = env_bool("CHATBOT_VERIFY_TLS", False)

    st.set_page_config(page_title=page_title, layout="centered")
    st.title(header_title)

    with st.sidebar:
        st.subheader("Backend")
        provider_path = st.radio(
            "Path",
            ["Direct LiteLLM", "FortiAIGate"],
            index=0,
            help="Direct sends to LiteLLM. FortiAIGate sends to FAIG, which should be configured to forward to LiteLLM.",
        )
        base_url = direct_base_url if provider_path == "Direct LiteLLM" else faig_base_url
        api_key = direct_api_key if provider_path == "Direct LiteLLM" else faig_api_key
        st.write(f"Model: `{model}`")
        st.write(f"Streaming: {'on' if streaming else 'off'}")
        st.write("Backend instructions: LiteLLM profile")

    if not base_url:
        st.error(f"{provider_path} base URL is not configured.")
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
            if streaming:
                reply = st.write_stream(
                    stream_response(
                        base_url,
                        api_key,
                        model,
                        frontend_system_prompt or None,
                        user_input,
                        temperature,
                        max_tokens,
                        verify_tls,
                    )
                )
            else:
                reply = single_response(
                    base_url,
                    api_key,
                    model,
                    frontend_system_prompt or None,
                    user_input,
                    temperature,
                    max_tokens,
                    verify_tls,
                )
                st.markdown(reply, unsafe_allow_html=True)
        except Exception as error:
            reply = f"Request failed: {error}"
            st.error(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    main()
