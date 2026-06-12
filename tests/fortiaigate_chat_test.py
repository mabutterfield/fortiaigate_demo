#!/usr/bin/env python3
"""Send a FortiAIGate OpenAI-compatible chat completion smoke test."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_ENDPOINT_PATH = "/v1/chat/completions"
DEFAULT_MODEL_ID = "openai.gpt-oss-20b-1:0"
DEFAULT_PROMPT = "hello, this is a test. Reply in one short sentence and include the name of the model answering."
DEFAULT_TERRAFORM_BEDROCK_PATH = (
    Path(__file__).resolve().parents[1] / "terraform" / "aws-bedrock"
)
DEFAULT_TERRAFORM_EC2_PATH = (
    Path(__file__).resolve().parents[1] / "terraform" / "aws-ec2-k3s"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a FortiAIGate chat completion test request."
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("FORTIAIGATE_URL", ""),
        help="Full FortiAIGate chat URL. Overrides --host/--path.",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("FORTIAIGATE_HOST", ""),
        help="FortiAIGate host or public IP. Defaults to terraform/aws-ec2-k3s public_ip.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("FORTIAIGATE_PORT", "443")),
        help="FortiAIGate HTTPS port.",
    )
    parser.add_argument(
        "--path",
        default=os.environ.get("FORTIAIGATE_ENDPOINT_PATH", DEFAULT_ENDPOINT_PATH),
        help="Chat completion endpoint path.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("FORTIAIGATE_MODEL")
        or os.environ.get("BEDROCK_MODEL")
        or os.environ.get("BEDROCK_MODEL_ID"),
        help="Model name to send in the OpenAI-compatible request.",
    )
    parser.add_argument(
        "--prompt",
        "--message",
        dest="message",
        default=os.environ.get("FORTIAIGATE_TEST_MESSAGE", DEFAULT_PROMPT),
        help="Prompt to send through FortiAIGate.",
    )
    parser.add_argument(
        "--apikey",
        "--api-key",
        dest="api_key",
        default=os.environ.get("FAIG_API_KEY")
        or os.environ.get("FORTIAIGATE_API_KEY")
        or os.environ.get("FORTIAIGATE_TEST_API_KEY", ""),
        help="Optional API key. No API key header is sent when empty.",
    )
    parser.add_argument(
        "--auth-header",
        "--api-key-header",
        dest="api_key_header",
        default=os.environ.get("AIG_HEADER")
        or os.environ.get("FORTIAIGATE_API_KEY_HEADER", "Authorization"),
        help="Header name used for the API key. Defaults to AIG_HEADER, then Authorization.",
    )
    parser.add_argument(
        "--api-key-prefix",
        default=os.environ.get("FAIG_API_KEY_PREFIX", ""),
        help="Optional API key value prefix, for example Bearer.",
    )
    parser.add_argument(
        "--jwt",
        action="store_true",
        help="Send the API key as a JWT bearer token. Equivalent to --api-key-prefix Bearer.",
    )
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        metavar="NAME: VALUE",
        help="Additional header to send. Repeat for multiple headers.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.environ.get("FORTIAIGATE_TEST_TIMEOUT", "60")),
        help="curl timeout in seconds.",
    )
    parser.add_argument(
        "--terraform-bedrock-path",
        default=os.environ.get(
            "BEDROCK_TERRAFORM_PATH",
            str(DEFAULT_TERRAFORM_BEDROCK_PATH),
        ),
        help="Path to terraform/aws-bedrock for permitted model output.",
    )
    parser.add_argument(
        "--terraform-ec2-path",
        default=os.environ.get(
            "FAIG_EC2_TERRAFORM_PATH",
            str(DEFAULT_TERRAFORM_EC2_PATH),
        ),
        help="Path to terraform/aws-ec2-k3s for public_ip output.",
    )
    parser.add_argument(
        "--verify-tls",
        action="store_true",
        help="Verify TLS certificates. By default the test uses curl -k.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print the effective curl command before running it. API key values are redacted.",
    )
    parser.add_argument(
        "--debug-show-secrets",
        action="store_true",
        help="With --debug, print API key values instead of redacting them.",
    )
    parser.add_argument(
        "--ansible-raw",
        action="store_true",
        help="Print raw response body plus __HTTP_STATUS__ marker for Ansible parsing.",
    )
    return parser.parse_args()


def terraform_output(terraform_path: str, output_name: str, json_output: bool = False) -> str:
    args = [
        "terraform",
        f"-chdir={terraform_path}",
        "output",
        "-json" if json_output else "-raw",
        output_name,
    ]
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def read_permitted_models(terraform_bedrock_path: str) -> list[str]:
    output = terraform_output(terraform_bedrock_path, "bedrock_model_ids", json_output=True)
    if not output:
        return []
    try:
        model_ids = json.loads(output)
    except json.JSONDecodeError:
        return []
    if not isinstance(model_ids, list):
        return []
    return [str(model_id).strip() for model_id in model_ids if str(model_id).strip()]


def model_label(model_id: str) -> str:
    match = re.search(r"gpt[-_.]?oss[-_.]?(\d+)b", model_id, re.IGNORECASE)
    if match:
        return f"gpt-oss:{match.group(1)}b ({model_id})"
    return model_id


def select_model(model_id: str | None, terraform_bedrock_path: str) -> str:
    if model_id and model_id.strip():
        return model_id.strip()

    permitted_models = read_permitted_models(terraform_bedrock_path)
    if permitted_models and sys.stdin.isatty():
        print("Select a FortiAIGate model:")
        for index, permitted_model in enumerate(permitted_models, start=1):
            print(f"{index}. {model_label(permitted_model)}")

        while True:
            selection = input("Model number: ").strip()
            if selection.isdigit():
                selected_index = int(selection)
                if 1 <= selected_index <= len(permitted_models):
                    return permitted_models[selected_index - 1]
            print(f"Enter a number from 1 to {len(permitted_models)}.")

    if permitted_models:
        return permitted_models[0]

    if sys.stdin.isatty():
        entered_model = input(f"FORTIAIGATE_MODEL [{DEFAULT_MODEL_ID}]: ").strip()
        return entered_model or DEFAULT_MODEL_ID

    return DEFAULT_MODEL_ID


def resolve_host(host: str, terraform_ec2_path: str) -> str:
    if host.strip():
        return host.strip()

    public_ip = terraform_output(terraform_ec2_path, "public_ip")
    if public_ip:
        return public_ip

    if sys.stdin.isatty():
        return input("FortiAIGate host or public IP: ").strip()

    return ""


def build_url(args: argparse.Namespace, host: str) -> str:
    if args.url.strip():
        parsed = urlparse(args.url.strip())
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("--url must be a full URL such as https://1.2.3.4:443/v1/chat/completions")
        return args.url.strip()

    if not host:
        raise ValueError("FortiAIGate host is required. Set --host, FORTIAIGATE_HOST, or terraform/aws-ec2-k3s public_ip.")

    path = args.path if args.path.startswith("/") else f"/{args.path}"
    return f"https://{host}:{args.port}{path}"


def build_payload(model: str, message: str) -> bytes:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": message,
            }
        ],
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def parse_header(header: str) -> tuple[str, str]:
    if ":" not in header:
        raise ValueError(f"Header must be formatted as 'Name: value': {header}")
    name, value = header.split(":", 1)
    name = name.strip()
    value = value.strip()
    if not name:
        raise ValueError(f"Header name cannot be empty: {header}")
    return name, value


def header_value(api_key: str, prefix: str, jwt: bool) -> str:
    api_key = api_key.strip()
    prefix = "Bearer" if jwt and not prefix.strip() else prefix.strip()
    if not prefix:
        return api_key
    return f"{prefix} {api_key}"


def build_headers(args: argparse.Namespace) -> list[tuple[str, str]]:
    headers = [("Content-Type", "application/json")]
    if args.api_key.strip():
        headers.append(
            (
                args.api_key_header.strip() or "Authorization",
                header_value(args.api_key, args.api_key_prefix, args.jwt),
            )
        )
    for header in args.header:
        headers.append(parse_header(header))
    return headers


def build_curl_args(
    *,
    url: str,
    timeout: int,
    payload: bytes,
    headers: list[tuple[str, str]],
    verify_tls: bool,
) -> list[str]:
    args = [
        "curl",
        "-sS",
        "--max-time",
        str(timeout),
        "-w",
        "\\n__HTTP_STATUS__:%{http_code}",
        "-X",
        "POST",
        url,
    ]
    if not verify_tls:
        args.insert(1, "-k")
    for name, value in headers:
        args.extend(["-H", f"{name}: {value}"])
    args.extend(["--data-binary", payload.decode("utf-8")])
    return args


def render_curl_args(args: list[str], redacted_headers: set[str]) -> str:
    rendered_args = []
    index = 0
    while index < len(args):
        rendered_args.append(args[index])
        if args[index] == "-H" and index + 1 < len(args):
            header = args[index + 1]
            name, separator, value = header.partition(":")
            if separator and name.strip().lower() in redacted_headers:
                stripped_value = value.strip()
                if stripped_value.lower().startswith("bearer "):
                    rendered_args.append(f"{name}: Bearer <redacted>")
                else:
                    rendered_args.append(f"{name}: <redacted>")
            else:
                rendered_args.append(header)
            index += 2
            continue
        index += 1
    return " ".join(shlex.quote(arg) for arg in rendered_args)


def run_curl(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def looks_like_jwt(value: str) -> bool:
    parts = value.strip().split(".")
    if len(parts) != 3:
        return False
    return all(re.fullmatch(r"[A-Za-z0-9_-]+", part or "") for part in parts)


def auth_hint(args: argparse.Namespace, status: str) -> str:
    if status != "401":
        return ""
    if not args.api_key.strip():
        return "HTTP 401: FortiAIGate requires authentication. Set FAIG_API_KEY or pass --apikey."

    header_name = args.api_key_header.strip() or "Authorization"
    prefix = "Bearer" if args.jwt and not args.api_key_prefix.strip() else args.api_key_prefix.strip()
    if header_name.lower() == "authorization" and looks_like_jwt(args.api_key) and prefix.lower() != "bearer":
        return (
            "HTTP 401: token looks like a JWT sent in Authorization without Bearer. "
            "Try --jwt or --api-key-prefix Bearer."
        )
    if header_name.lower() != "authorization":
        return (
            f"HTTP 401: custom auth header '{header_name}' was sent. Confirm the GUI Custom "
            "Authentication Header exactly matches this name; FortiAIGate ignores default API key "
            "headers when a custom header is configured."
        )
    if prefix.lower() == "bearer":
        return (
            "HTTP 401: Authorization: Bearer <token> was sent but rejected. Confirm the JWT is "
            "current, copied fully, and belongs to the configured AI Flow/guard."
        )
    return (
        "HTTP 401: authentication header was sent but rejected. If this is JWT auth, try --jwt. "
        "Also confirm the token is current and belongs to the configured AI Flow/guard."
    )


def split_response(stdout: str) -> tuple[str, str]:
    marker = "\n__HTTP_STATUS__:"
    if marker not in stdout:
        return stdout, "000"
    body, status = stdout.rsplit(marker, 1)
    return body, status.strip() or "000"


def summarize_response(body: str) -> str:
    if not body.strip():
        return "<empty response body>"
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return body[:4000]

    choices = data.get("choices") if isinstance(data, dict) else None
    if choices:
        first = choices[0]
        message = first.get("message") if isinstance(first, dict) else None
        if isinstance(message, dict) and message.get("content"):
            return str(message["content"])
        if isinstance(first, dict) and first.get("text"):
            return str(first["text"])
    return json.dumps(data, indent=2)[:4000]


def main() -> int:
    args = parse_args()
    model = select_model(args.model, args.terraform_bedrock_path)
    host = resolve_host(args.host, args.terraform_ec2_path)

    try:
        url = build_url(args, host)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    payload = build_payload(model, args.message)
    try:
        headers = build_headers(args)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    curl_args = build_curl_args(
        url=url,
        timeout=args.timeout,
        payload=payload,
        headers=headers,
        verify_tls=args.verify_tls,
    )

    if args.debug:
        redacted_headers = set()
        if args.api_key.strip() and not args.debug_show_secrets:
            redacted_headers.add((args.api_key_header.strip() or "Authorization").lower())
        print("Effective curl command:")
        print(render_curl_args(curl_args, redacted_headers))

    try:
        result = run_curl(curl_args)
    except FileNotFoundError:
        print("curl is required but was not found in PATH.", file=sys.stderr)
        return 127

    body, status = split_response(result.stdout)
    if args.ansible_raw:
        sys.stdout.write(body)
        sys.stdout.write(f"\n__HTTP_STATUS__:{status}")
        sys.stderr.write(result.stderr)
        return result.returncode

    print("FortiAIGate chat completion test")
    print(f"URL: {url}")
    print(f"Model: {model}")
    print(
        "API key header: "
        + (
            f"{args.api_key_header.strip() or 'Authorization'} enabled"
            if args.api_key.strip()
            else "disabled"
        )
    )
    print(f"Additional headers: {len(args.header)}")
    print(f"HTTP status: {status}")
    print(f"curl exit code: {result.returncode}")
    hint = auth_hint(args, status)
    if hint:
        print(f"Auth hint: {hint}")
    if result.stderr:
        print("curl stderr:")
        print(result.stderr.rstrip())
    print("Response:")
    print(summarize_response(body))

    if result.returncode != 0:
        return result.returncode
    status_code = int(status) if status.isdigit() else 0
    if status_code < 200 or status_code >= 300:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
