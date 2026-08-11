#!/usr/bin/env python3
"""Touch AI application endpoints for FortiGate application-control testing.

The default path sends direct traffic with no proxy. Use --proxy-url only when
testing a FortiGate explicit proxy. The script is intentionally scoped to one
execution and ignores proxy-related environment variables unless
--honor-proxy-env is set.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import hmac
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path


DEFAULT_APPS: dict[str, str] = {
    "OpenAI.ChatGPT": "https://chatgpt.com/",
    "Google.Gemini": "https://gemini.google.com/app",
    "Google.NotebookLM": "https://notebooklm.google.com/",
    "Google.Vertex.AI": "https://cloud.google.com/vertex-ai",
    "Claude": "https://claude.ai/chats",
    "Microsoft.Copilot": "https://copilot.microsoft.com/chats",
    "Microsoft.Azure.OpenAI": "https://ai.azure.com/",
    "Hugging.Face": "https://huggingface.co/",
    "DeepSeek": "https://chat.deepseek.com/",
    "Mistral.AI.API": "https://api.mistral.ai/v1/models",
    "OpenRouter": "https://openrouter.ai/api/v1/models",
    "Groq": "https://api.groq.com/openai/v1/models",
    "Meta.AI": "https://www.meta.ai/",
    "Replicate": "https://replicate.com/",
    "Protocol.A2A.Tasks": "https://api.dev.runwayml.com/v1/tasks",
}

DEFAULT_MCP_TARGETS: dict[str, str] = {
    "GitHub.MCP": "https://api.githubcopilot.com/mcp/",
    "GitLab.MCP": "https://gitlab.com/api/v4/mcp",
    "AWS.MCP": "https://aws-mcp.us-east-1.api.aws/mcp",
}

DEFAULT_BEDROCK_MODEL_ID = "openai.gpt-oss-20b-1:0"
DEFAULT_BEDROCK_PROMPT = (
    "FORTIGATE_BEDROCK_TEST: Reply in one short sentence and identify this as "
    "a Bedrock Runtime traffic classification test."
)
DEFAULT_BEDROCK_MAX_TOKENS = 256
DEFAULT_MCP_READ_BYTES = 1048576


@dataclass(frozen=True)
class Target:
    name: str
    url: str
    workflow: str = "ai-apps"


@dataclass
class Result:
    name: str
    url: str
    method: str
    status: int | None
    outcome: str
    elapsed_ms: int
    bytes_read: int
    error: str | None = None
    response_text: str | None = None
    response_metadata: dict[str, object] | None = None
    response_note: str | None = None


@dataclass
class HttpStepResult:
    method: str
    status: int | None
    body: bytes
    headers: dict[str, str]
    elapsed_ms: int
    error: str | None = None
    truncated: bool = False


def redact_proxy_url(proxy_url: str) -> str:
    parsed = urllib.parse.urlsplit(proxy_url)
    if not parsed.username and not parsed.password:
        return proxy_url
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urllib.parse.urlunsplit(
        (parsed.scheme, f"<redacted>@{host}", parsed.path, parsed.query, parsed.fragment)
    )


def parse_named_targets(
    target_args: list[str],
    include_defaults: bool,
    default_targets: dict[str, str],
    workflow: str,
    target_type: str,
) -> list[Target]:
    targets: list[Target] = []
    if include_defaults or not target_args:
        targets.extend(Target(name, url, workflow) for name, url in default_targets.items())

    for raw_arg in target_args:
        for item in [part.strip() for part in raw_arg.split(",") if part.strip()]:
            if item in default_targets:
                targets.append(Target(item, default_targets[item], workflow))
                continue
            if "=" in item:
                name, url = item.split("=", 1)
                targets.append(Target(name.strip(), url.strip(), workflow))
                continue
            if item.startswith("http://") or item.startswith("https://"):
                parsed = urllib.parse.urlsplit(item)
                targets.append(Target(parsed.netloc or "custom", item, workflow))
                continue
            raise SystemExit(
                f"Unknown {target_type} target '{item}'. Use --list-targets, a URL, or name=url."
            )

    seen: set[tuple[str, str]] = set()
    unique_targets: list[Target] = []
    for target in targets:
        key = (target.name, target.url)
        if key not in seen:
            unique_targets.append(target)
            seen.add(key)
    return unique_targets


def parse_targets(args: argparse.Namespace) -> list[Target]:
    target_sets = args.target_set or ["ai-apps"]
    targets: list[Target] = []
    include_defaults = args.all_defaults
    if "ai-apps" in target_sets:
        targets.extend(
            parse_named_targets(
                args.app,
                include_defaults or not args.app,
                DEFAULT_APPS,
                "ai-apps",
                "app",
            )
        )
    if "mcp" in target_sets:
        targets.extend(
            parse_named_targets(
                args.mcp_target,
                include_defaults or not args.mcp_target,
                DEFAULT_MCP_TARGETS,
                "mcp",
                "MCP",
            )
        )
    if "bedrock" in target_sets:
        region = args.aws_region
        model_id = args.bedrock_model_id
        targets.append(
            Target(
                "AWS.Bedrock.Runtime",
                f"https://bedrock-runtime.{region}.amazonaws.com/model/{model_id}/converse",
                "bedrock",
            )
        )

    seen: set[tuple[str, str, str]] = set()
    unique_targets: list[Target] = []
    for target in targets:
        key = (target.workflow, target.name, target.url)
        if key not in seen:
            unique_targets.append(target)
            seen.add(key)
    return unique_targets


def validate_proxy_url(proxy_url: str) -> None:
    parsed = urllib.parse.urlsplit(proxy_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemExit(
            "Proxy URL must include scheme and host, for example "
            "http://192.168.249.1:8080"
        )


def build_opener(proxy_url: str | None, insecure: bool) -> urllib.request.OpenerDirector:
    proxy_map = {"http": proxy_url, "https": proxy_url} if proxy_url else {}
    handlers: list[urllib.request.BaseHandler] = [urllib.request.ProxyHandler(proxy_map)]
    if insecure:
        context = ssl._create_unverified_context()
        handlers.append(urllib.request.HTTPSHandler(context=context))
    return urllib.request.build_opener(*handlers)


def sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def build_aws_authorization(
    *,
    method: str,
    service: str,
    region: str,
    url: str,
    payload: bytes,
    access_key: str,
    secret_key: str,
    session_token: str,
) -> tuple[str, dict[str, str]]:
    parsed = urllib.parse.urlparse(url)
    now = datetime.datetime.now(datetime.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(payload).hexdigest()

    headers = {
        "content-type": "application/json",
        "host": parsed.netloc,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if session_token:
        headers["x-amz-security-token"] = session_token

    canonical_uri = urllib.parse.quote(parsed.path, safe="/-_.~")
    canonical_headers = "".join(f"{key}:{headers[key]}\n" for key in sorted(headers))
    signed_headers = ";".join(sorted(headers))
    canonical_request = "\n".join(
        [
            method,
            canonical_uri,
            parsed.query,
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )

    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )

    signing_key = sign(
        sign(
            sign(
                sign(("AWS4" + secret_key).encode("utf-8"), date_stamp),
                region,
            ),
            service,
        ),
        "aws4_request",
    )
    signature = hmac.new(
        signing_key,
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    authorization = (
        "AWS4-HMAC-SHA256 "
        f"Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )
    return authorization, headers


def mcp_initialize_payload() -> bytes:
    payload = {
        "jsonrpc": "2.0",
        "id": "faig-mcp-probe-1",
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {
                "name": "FAIG FortiGate MCP probe",
                "version": "1.0",
            },
        },
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def mcp_initialized_payload() -> bytes:
    payload = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def mcp_tools_list_payload() -> bytes:
    payload = {
        "jsonrpc": "2.0",
        "id": "faig-mcp-probe-tools-list",
        "method": "tools/list",
        "params": {},
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def mcp_tool_call_payload(tool_name: str, arguments: dict[str, object]) -> bytes:
    payload = {
        "jsonrpc": "2.0",
        "id": "faig-mcp-probe-tool-call",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def bedrock_converse_payload(prompt: str, max_tokens: int, temperature: float) -> bytes:
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [{"text": prompt}],
            }
        ],
        "inferenceConfig": {
            "maxTokens": max_tokens,
            "temperature": temperature,
        },
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def load_json_or_sse(body: bytes) -> object | None:
    if not body:
        return None
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    events: list[str] = []
    current_event: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            if current_event:
                events.append("\n".join(current_event))
                current_event = []
            continue
        if line.startswith("data:"):
            value = line.removeprefix("data:").strip()
            if value and value != "[DONE]":
                current_event.append(value)
    if current_event:
        events.append("\n".join(current_event))
    for event in events:
        try:
            return json.loads(event)
        except json.JSONDecodeError:
            continue
    if not events:
        return None
    return {"_unparsed_sse_events": len(events)}


def extract_mcp_response(body: bytes) -> tuple[str | None, dict[str, object] | None, str | None]:
    payload = load_json_or_sse(body)
    if not isinstance(payload, dict):
        return None, None, "MCP response body was not JSON or SSE JSON"
    if "_unparsed_sse_events" in payload:
        return (
            None,
            {"unparsed_sse_events": payload["_unparsed_sse_events"]},
            "MCP response had SSE data events that were not JSON objects",
        )
    if "error" in payload:
        error = payload.get("error")
        return None, {"jsonrpc_error": error}, "MCP JSON-RPC error returned"

    result = payload.get("result")
    if not isinstance(result, dict):
        return None, None, "MCP response did not include a JSON-RPC result object"

    tools = result.get("tools")
    if isinstance(tools, list):
        names = [
            tool.get("name")
            for tool in tools
            if isinstance(tool, dict) and isinstance(tool.get("name"), str)
        ]
        summary = ", ".join(names[:25])
        if len(names) > 25:
            summary = f"{summary}, ... (+{len(names) - 25} more)"
        return (
            f"tools/list returned {len(names)} tool(s): {summary}",
            {"tool_count": len(names), "tool_names": names},
            None,
        )

    content = result.get("content")
    if isinstance(content, list):
        text_parts = [
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        response_text = "\n".join(text_parts).strip()
        metadata = {
            "content_item_count": len(content),
            "is_error": result.get("isError", False),
        }
        if response_text:
            return response_text, metadata, None
        return None, metadata, "MCP tools/call returned content without text"

    server_info = result.get("serverInfo")
    if isinstance(server_info, dict):
        name = server_info.get("name", "unknown")
        version = server_info.get("version", "unknown")
        return (
            f"initialize returned serverInfo name={name}, version={version}",
            {"serverInfo": server_info},
            None,
        )

    return None, {"result_keys": sorted(result.keys())}, "MCP response parsed without tool list"


def extract_bedrock_response(
    body: bytes,
) -> tuple[str | None, dict[str, object] | None, str | None]:
    if not body:
        return None, None, None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, None, "response body was not valid UTF-8 JSON"

    content = (
        payload.get("output", {})
        .get("message", {})
        .get("content", [])
    )
    text_parts = [
        item.get("text", "")
        for item in content
        if isinstance(item, dict) and item.get("text")
    ]
    response_text = "\n".join(text_parts).strip() or None

    metadata: dict[str, object] = {}
    for key in ["stopReason", "usage", "metrics"]:
        if key in payload:
            metadata[key] = payload[key]

    note = None
    if not response_text:
        content_keys = sorted(
            {
                key
                for item in content
                if isinstance(item, dict)
                for key in item
            }
        )
        stop_reason = payload.get("stopReason")
        if stop_reason == "max_tokens":
            note = (
                "no visible assistant text; the model hit max_tokens before "
                "returning a text content block"
            )
        elif content_keys:
            note = f"no visible assistant text; content block keys: {', '.join(content_keys)}"
        else:
            note = "no visible assistant text in Bedrock Converse response"

    return response_text, metadata or None, note


def parse_mcp_arguments_json(raw_arguments: str) -> dict[str, object]:
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--mcp-arguments-json is not valid JSON: {exc}") from exc
    if not isinstance(arguments, dict):
        raise SystemExit("--mcp-arguments-json must decode to a JSON object")
    return arguments


def http_post_step(
    opener: urllib.request.OpenerDirector,
    url: str,
    payload: bytes,
    headers: dict[str, str],
    *,
    timeout: float,
    read_bytes: int,
) -> HttpStepResult:
    start = time.monotonic()
    request = urllib.request.Request(
        url,
        method="POST",
        data=payload,
        headers=headers,
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(read_bytes + 1) if read_bytes > 0 else b""
            truncated = read_bytes > 0 and len(body) > read_bytes
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return HttpStepResult(
                method="POST",
                status=response.status,
                body=body[:read_bytes],
                headers=dict(response.headers.items()),
                elapsed_ms=elapsed_ms,
                truncated=truncated,
            )
    except urllib.error.HTTPError as exc:
        body = exc.read(read_bytes + 1) if read_bytes > 0 else b""
        truncated = read_bytes > 0 and len(body) > read_bytes
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return HttpStepResult(
            method="POST",
            status=exc.code,
            body=body[:read_bytes],
            headers=dict(exc.headers.items()),
            elapsed_ms=elapsed_ms,
            error=str(exc.reason),
            truncated=truncated,
        )


def disable_proxy_env() -> dict[str, str]:
    """Remove proxy variables from this process only.

    urllib can read proxy and proxy-bypass variables from the environment. This
    script should be deterministic: direct by default, or through --proxy-url
    only when that option is supplied.
    """
    removed: dict[str, str] = {}
    for name in [
        "http_proxy",
        "HTTP_PROXY",
        "https_proxy",
        "HTTPS_PROXY",
        "all_proxy",
        "ALL_PROXY",
        "no_proxy",
        "NO_PROXY",
    ]:
        value = os.environ.pop(name, None)
        if value is not None:
            removed[name] = value
    return removed


def touch_target(
    opener: urllib.request.OpenerDirector,
    target: Target,
    *,
    args: argparse.Namespace,
    timeout: float,
    user_agent: str,
    read_bytes: int,
    range_request: bool,
) -> Result:
    start = time.monotonic()
    method = args.method
    data = None
    headers = {
        "User-Agent": user_agent,
        "Accept": "*/*",
    }
    if target.workflow == "mcp":
        token = os.environ.get(args.mcp_token_env, "").strip() if args.mcp_token_env else ""
        if args.mcp_token_env and not token:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return Result(
                name=target.name,
                url=target.url,
                method="POST",
                status=None,
                outcome="failed",
                elapsed_ms=elapsed_ms,
                bytes_read=0,
                error=f"missing environment variable: {args.mcp_token_env}",
            )
        mcp_headers = {
            "User-Agent": user_agent,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
        }
        if token:
            mcp_headers["Authorization"] = "Bearer " + token

        initialize_result = http_post_step(
            opener,
            target.url,
            mcp_initialize_payload(),
            mcp_headers,
            timeout=timeout,
            read_bytes=args.mcp_read_bytes,
        )
        session_id = (
            initialize_result.headers.get("Mcp-Session-Id")
            or initialize_result.headers.get("mcp-session-id")
        )
        final_result = initialize_result
        response_text, response_metadata, response_note = extract_mcp_response(
            initialize_result.body
        )
        mcp_response_truncated = initialize_result.truncated
        if args.mcp_mode in {"tools-list", "tool-call"} and initialize_result.status in {200, 202}:
            tool_headers = dict(mcp_headers)
            if session_id:
                tool_headers["Mcp-Session-Id"] = session_id
            initialized_result = http_post_step(
                opener,
                target.url,
                mcp_initialized_payload(),
                tool_headers,
                timeout=timeout,
                read_bytes=args.mcp_read_bytes,
            )
            if args.mcp_mode == "tools-list":
                action_payload = mcp_tools_list_payload()
            else:
                action_payload = mcp_tool_call_payload(
                    args.mcp_tool,
                    parse_mcp_arguments_json(args.mcp_arguments_json),
                )
            final_result = http_post_step(
                opener,
                target.url,
                action_payload,
                tool_headers,
                timeout=timeout,
                read_bytes=args.mcp_read_bytes,
            )
            response_text, response_metadata, response_note = extract_mcp_response(
                final_result.body
            )
            mcp_response_truncated = final_result.truncated
            if response_metadata is None:
                response_metadata = {}
            response_metadata["initialize_status"] = initialize_result.status
            response_metadata["initialized_status"] = initialized_result.status
            response_metadata["mcp_action"] = args.mcp_mode
            if args.mcp_mode == "tool-call":
                response_metadata["mcp_tool"] = args.mcp_tool
            response_metadata["session_id_returned"] = bool(session_id)
            response_metadata["mcp_response_truncated"] = mcp_response_truncated

        elapsed_ms = int((time.monotonic() - start) * 1000)
        outcome = "reached" if final_result.status and final_result.status < 400 else "http-error-reached"
        return Result(
            name=target.name,
            url=target.url,
            method="POST",
            status=final_result.status,
            outcome=outcome,
            elapsed_ms=elapsed_ms,
            bytes_read=len(final_result.body),
            error=final_result.error,
            response_text=response_text,
            response_metadata=response_metadata,
            response_note=response_note,
        )
    elif target.workflow == "bedrock":
        method = "POST"
        access_key = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
        secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()
        session_token = os.environ.get("AWS_SESSION_TOKEN", "").strip()
        if not access_key or not secret_key:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            missing = [
                name
                for name, value in [
                    ("AWS_ACCESS_KEY_ID", access_key),
                    ("AWS_SECRET_ACCESS_KEY", secret_key),
                ]
                if not value
            ]
            return Result(
                name=target.name,
                url=target.url,
                method=method,
                status=None,
                outcome="failed",
                elapsed_ms=elapsed_ms,
                bytes_read=0,
                error=f"missing environment variable(s): {', '.join(missing)}",
            )
        data = bedrock_converse_payload(
            args.bedrock_prompt,
            args.bedrock_max_tokens,
            args.bedrock_temperature,
        )
        authorization, signed_headers = build_aws_authorization(
            method=method,
            service="bedrock",
            region=args.aws_region,
            url=target.url,
            payload=data,
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
        )
        headers.update(
            {
                "Content-Type": "application/json",
                "X-Amz-Date": signed_headers["x-amz-date"],
                "X-Amz-Content-Sha256": signed_headers["x-amz-content-sha256"],
                "Authorization": authorization,
            }
        )
        if "x-amz-security-token" in signed_headers:
            headers["X-Amz-Security-Token"] = signed_headers["x-amz-security-token"]

    request = urllib.request.Request(
        target.url,
        method=method,
        data=data,
        headers=headers,
    )
    if target.workflow == "ai-apps" and method == "GET" and read_bytes > 0 and range_request:
        request.add_header("Range", f"bytes=0-{read_bytes - 1}")

    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(read_bytes) if read_bytes > 0 else b""
            response_text, response_metadata, response_note = (
                extract_bedrock_response(body)
                if target.workflow == "bedrock"
                else (None, None, None)
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return Result(
                name=target.name,
                url=target.url,
                method=method,
                status=response.status,
                outcome="reached",
                elapsed_ms=elapsed_ms,
                bytes_read=len(body),
                response_text=response_text,
                response_metadata=response_metadata,
                response_note=response_note,
            )
    except urllib.error.HTTPError as exc:
        body = exc.read(read_bytes) if read_bytes > 0 else b""
        response_text, response_metadata, response_note = (
            extract_bedrock_response(body)
            if target.workflow == "bedrock"
            else (None, None, None)
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return Result(
            name=target.name,
            url=target.url,
            method=method,
            status=exc.code,
            outcome="http-error-reached",
            elapsed_ms=elapsed_ms,
            bytes_read=len(body),
            error=str(exc.reason),
            response_text=response_text,
            response_metadata=response_metadata,
            response_note=response_note,
        )
    except Exception as exc:  # noqa: BLE001 - operator-facing diagnostics
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return Result(
            name=target.name,
            url=target.url,
            method=method,
            status=None,
            outcome="failed",
            elapsed_ms=elapsed_ms,
            bytes_read=0,
            error=str(exc),
        )


def print_target_plan(targets: list[Target], proxy_url: str | None, args: argparse.Namespace) -> None:
    print("FortiGate AI application touch")
    print(f"Mode: {'execute' if args.execute else 'dry-run'}")
    print(f"Traffic path: {redact_proxy_url(proxy_url) if proxy_url else 'direct/no proxy'}")
    print(f"Target sets: {', '.join(args.target_set or ['ai-apps'])}")
    if any(target.workflow == "ai-apps" for target in targets):
        print(f"AI app method: {args.method}")
    if any(target.workflow == "mcp" for target in targets):
        print(f"MCP mode: {args.mcp_mode}")
        print(f"MCP token env: {args.mcp_token_env or 'none'}")
        if args.mcp_token_env:
            print(
                "MCP token env status: "
                f"{'present' if os.environ.get(args.mcp_token_env) else 'missing'}"
            )
    if any(target.workflow == "bedrock" for target in targets):
        print("Bedrock method: POST Converse")
    print(f"Timeout: {args.timeout}s")
    print(f"Read bytes: {args.read_bytes}")
    print(f"Range request: {'yes' if args.range_request else 'no'}")
    print(f"User-Agent: {args.user_agent}")
    print(f"Proxy environment: {'honored' if args.honor_proxy_env else 'ignored for this process'}")
    if any(target.workflow == "bedrock" for target in targets):
        print(f"Bedrock region: {args.aws_region}")
        print(f"Bedrock model: {args.bedrock_model_id}")
        print(f"AWS access key env: {'present' if os.environ.get('AWS_ACCESS_KEY_ID') else 'missing'}")
        print(f"AWS secret key env: {'present' if os.environ.get('AWS_SECRET_ACCESS_KEY') else 'missing'}")
        print(f"AWS session token env: {'present' if os.environ.get('AWS_SESSION_TOKEN') else 'not set'}")
    print("")
    print("Targets:")
    for target in targets:
        print(f"- {target.name} [{target.workflow}]: {target.url}")


def print_results(results: list[Result]) -> None:
    print("")
    print("Results:")
    for result in results:
        status = result.status if result.status is not None else "-"
        error = f" ({result.error})" if result.error else ""
        print(
            f"- {result.name}: {result.outcome}, status={status}, "
            f"elapsed_ms={result.elapsed_ms}, bytes={result.bytes_read}{error}"
        )
        if result.response_text:
            print(f"  response: {result.response_text}")
        if result.response_note:
            print(f"  response_note: {result.response_note}")
        if result.response_metadata:
            print(f"  metadata: {json.dumps(result.response_metadata, sort_keys=True)}")


def write_json(path: Path, proxy_url: str | None, results: list[Result]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "traffic_path": redact_proxy_url(proxy_url) if proxy_url else "direct/no proxy",
        "results": [asdict(result) for result in results],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote JSON results: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Touch AI application, MCP, and Bedrock endpoints to generate real "
            "FortiGate application-control evidence."
        )
    )
    parser.add_argument(
        "--target-set",
        action="append",
        choices=["ai-apps", "mcp", "bedrock"],
        help=(
            "Target workflow to run. Repeat to combine sets. Defaults to "
            "ai-apps. Bedrock sends a signed Converse request and requires AWS "
            "credential environment variables."
        ),
    )
    parser.add_argument(
        "--proxy-url",
        help=(
            "Optional explicit proxy URL for this run only, for example "
            "http://192.168.249.1:8080. Omit for direct/no-proxy traffic."
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Send the requests. Without this flag the script only prints the target plan.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Do not ask for final confirmation when --execute is used.",
    )
    parser.add_argument(
        "--app",
        action="append",
        default=[],
        help=(
            "Target app name, comma-separated names, URL, or name=url. "
            "Repeat as needed. Used with --target-set ai-apps."
        ),
    )
    parser.add_argument(
        "--mcp-target",
        action="append",
        default=[],
        help=(
            "MCP target name, comma-separated names, URL, or name=url. "
            "Repeat as needed. Used with --target-set mcp."
        ),
    )
    parser.add_argument(
        "--mcp-mode",
        choices=["initialize", "tools-list", "tool-call"],
        default="initialize",
        help=(
            "MCP workflow to send. initialize sends one JSON-RPC initialize "
            "request. tools-list initializes the session, sends initialized, "
            "then sends tools/list. tool-call initializes the session, sends "
            "initialized, then sends tools/call. Default: initialize."
        ),
    )
    parser.add_argument(
        "--mcp-tool",
        help="MCP tool name for --mcp-mode tool-call.",
    )
    parser.add_argument(
        "--mcp-arguments-json",
        default="{}",
        help="JSON object of MCP tool arguments for --mcp-mode tool-call.",
    )
    parser.add_argument(
        "--mcp-token-env",
        help=(
            "Environment variable containing an MCP bearer token. The value is "
            "used in Authorization and is never printed."
        ),
    )
    parser.add_argument(
        "--mcp-read-bytes",
        type=int,
        default=DEFAULT_MCP_READ_BYTES,
        help=f"Maximum bytes to read from MCP responses. Default: {DEFAULT_MCP_READ_BYTES}.",
    )
    parser.add_argument(
        "--all-defaults",
        action="store_true",
        help=(
            "Include all default targets for selected target sets even when "
            "custom --app or --mcp-target values are supplied."
        ),
    )
    parser.add_argument(
        "--list-targets",
        "--list-apps",
        dest="list_targets",
        action="store_true",
        help="Print built-in app and MCP targets and exit.",
    )
    parser.add_argument(
        "--method",
        choices=["HEAD", "GET"],
        default="HEAD",
        help="HTTP method to send. Default: HEAD.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Per-target timeout in seconds. Default: 10.",
    )
    parser.add_argument(
        "--read-bytes",
        type=int,
        default=1024,
        help=(
            "Maximum bytes to read from GET responses without requesting a "
            "partial response. Default: 1024."
        ),
    )
    parser.add_argument(
        "--range-request",
        action="store_true",
        help=(
            "Send a Range header for GET requests. Disabled by default because "
            "partial requests can change FortiGate application classification."
        ),
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS certificate validation for intercepted HTTPS sessions.",
    )
    parser.add_argument(
        "--user-agent",
        default="FAIG-Phase10E-FortiGate-AppTouch/1.0",
        help="User-Agent label used for correlation in proxy logs.",
    )
    parser.add_argument(
        "--honor-proxy-env",
        action="store_true",
        help=(
            "Honor proxy-related environment variables. By default these are "
            "cleared inside this process so traffic is direct unless --proxy-url "
            "is supplied."
        ),
    )
    parser.add_argument(
        "--aws-region",
        default=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1",
        help="AWS region for Bedrock Runtime. Default: AWS_REGION, AWS_DEFAULT_REGION, then us-east-1.",
    )
    parser.add_argument(
        "--bedrock-model-id",
        default=os.environ.get("BEDROCK_MODEL") or os.environ.get("BEDROCK_MODEL_ID") or DEFAULT_BEDROCK_MODEL_ID,
        help="Bedrock model ID for --target-set bedrock.",
    )
    parser.add_argument(
        "--bedrock-prompt",
        default=os.environ.get("BEDROCK_TEST_MESSAGE", DEFAULT_BEDROCK_PROMPT),
        help="Prompt sent by the Bedrock probe.",
    )
    parser.add_argument(
        "--bedrock-max-tokens",
        type=int,
        default=int(os.environ.get("BEDROCK_TEST_MAX_TOKENS", str(DEFAULT_BEDROCK_MAX_TOKENS))),
        help=f"Maximum Bedrock response tokens. Default: {DEFAULT_BEDROCK_MAX_TOKENS}.",
    )
    parser.add_argument(
        "--bedrock-temperature",
        type=float,
        default=float(os.environ.get("BEDROCK_TEST_TEMPERATURE", "0.0")),
        help="Bedrock sampling temperature. Default: 0.0.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Optional JSON result path, preferably under ignored docs/raw-output/.",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    target_sets = args.target_set or ["ai-apps"]
    if "mcp" not in target_sets:
        return
    if args.mcp_mode != "tool-call":
        return
    if not args.mcp_tool:
        raise SystemExit("--mcp-mode tool-call requires --mcp-tool")
    parse_mcp_arguments_json(args.mcp_arguments_json)


def main() -> int:
    args = parse_args()
    if args.list_targets:
        print("AI app targets:")
        for name, url in DEFAULT_APPS.items():
            print(f"{name}: {url}")
        print("")
        print("MCP targets:")
        for name, url in DEFAULT_MCP_TARGETS.items():
            print(f"{name}: {url}")
        print("")
        print("Bedrock target:")
        print("AWS.Bedrock.Runtime: https://bedrock-runtime.<region>.amazonaws.com/model/<model-id>/converse")
        return 0
    validate_args(args)

    targets = parse_targets(args)
    proxy_url = args.proxy_url
    print_target_plan(targets, proxy_url, args)

    if not args.execute:
        print("")
        print("Dry run only. Add --execute to send requests.")
        return 0

    if proxy_url:
        validate_proxy_url(proxy_url)

    if not args.yes:
        route = redact_proxy_url(proxy_url) if proxy_url else "direct/no proxy"
        answer = input(
            f"Send {len(targets)} request(s) using {route}? [y/N] "
        ).strip()
        if answer.lower() not in {"y", "yes"}:
            print("Cancelled.")
            return 1

    removed_proxy_env = {} if args.honor_proxy_env else disable_proxy_env()
    if removed_proxy_env:
        removed_names = ", ".join(sorted(removed_proxy_env))
        print(f"Ignoring proxy environment for this run: {removed_names}")

    opener = build_opener(proxy_url, args.insecure)
    results = [
        touch_target(
            opener,
            target,
            args=args,
            timeout=args.timeout,
            user_agent=args.user_agent,
            read_bytes=args.read_bytes,
            range_request=args.range_request,
        )
        for target in targets
    ]
    print_results(results)

    if args.json_output:
        write_json(args.json_output, proxy_url, results)

    failures = [result for result in results if result.outcome == "failed"]
    return 2 if failures and len(failures) == len(results) else 0


if __name__ == "__main__":
    sys.exit(main())
