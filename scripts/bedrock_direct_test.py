#!/usr/bin/env python3
"""Send a signed AWS Bedrock Converse test request.

The script signs the request with AWS SigV4 using exported AWS credentials.
If credentials are missing and stdin is interactive, it prompts for them.
"""

from __future__ import annotations

import argparse
import datetime
import getpass
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path


DEFAULT_MESSAGE = "Hello, is this thing on? Reply in one short sentence and include the name of the model answering."
DEFAULT_MODEL_ID = "openai.gpt-oss-20b-1:0"
DEFAULT_TERRAFORM_PREP_PATH = (
    Path(__file__).resolve().parents[1] / "terraform" / "aws-prep"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a signed direct Bedrock Converse test request."
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", "us-east-1"),
        help="AWS region for the Bedrock runtime endpoint.",
    )
    parser.add_argument(
        "--model-id",
        default=os.environ.get("BEDROCK_MODEL")
        or os.environ.get("BEDROCK_MODEL_ID"),
        help=(
            "Bedrock model ID. Defaults to BEDROCK_MODEL, then BEDROCK_MODEL_ID, "
            "then an interactive selection from terraform/aws-prep outputs."
        ),
    )
    parser.add_argument(
        "--terraform-bedrock-path",
        "--terraform-prep-path",
        default=os.environ.get(
            "AWS_PREP_TERRAFORM_PATH",
            os.environ.get("BEDROCK_TERRAFORM_PATH", str(DEFAULT_TERRAFORM_PREP_PATH)),
        ),
        help="Path to terraform/aws-prep for permitted model output.",
    )
    parser.add_argument(
        "--prompt",
        "--message",
        dest="message",
        default=os.environ.get("BEDROCK_TEST_MESSAGE", DEFAULT_MESSAGE),
        help="Prompt to send to the model.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=int(os.environ.get("BEDROCK_TEST_MAX_TOKENS", "512")),
        help="Maximum response tokens.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=float(os.environ.get("BEDROCK_TEST_TEMPERATURE", "0.2")),
        help="Model sampling temperature.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.environ.get("BEDROCK_TEST_TIMEOUT", "60")),
        help="curl timeout in seconds.",
    )
    parser.add_argument(
        "--ansible-raw",
        action="store_true",
        help="Print raw response body plus __HTTP_STATUS__ marker for Ansible parsing.",
    )
    return parser.parse_args()


def read_permitted_models(terraform_bedrock_path: str) -> list[str]:
    result = subprocess.run(
        [
            "terraform",
            f"-chdir={terraform_bedrock_path}",
            "output",
            "-json",
            "bedrock_model_ids",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []

    try:
        model_ids = json.loads(result.stdout)
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
        print("Select a Bedrock model:")
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
        entered_model = input(f"BEDROCK_MODEL [{DEFAULT_MODEL_ID}]: ").strip()
        return entered_model or DEFAULT_MODEL_ID

    return DEFAULT_MODEL_ID


def read_credential(env_name: str, prompt: str, secret: bool = False) -> str:
    value = os.environ.get(env_name, "").strip()
    if value:
        return value

    if sys.stdin.isatty():
        if secret:
            return getpass.getpass(prompt).strip()
        return input(prompt).strip()

    print(
        f"Missing {env_name}. Export it before running this script.",
        file=sys.stderr,
    )
    return ""


def sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def build_authorization(
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


def build_payload(message: str, max_tokens: int, temperature: float) -> bytes:
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [{"text": message}],
            }
        ],
        "inferenceConfig": {
            "maxTokens": max_tokens,
            "temperature": temperature,
        },
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def run_curl(
    *,
    url: str,
    timeout: int,
    payload: bytes,
    authorization: str,
    signed_headers: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    args = [
        "curl",
        "-sS",
        "--max-time",
        str(timeout),
        "-w",
        "\n__HTTP_STATUS__:%{http_code}",
        "-X",
        "POST",
        url,
        "-H",
        "Content-Type: application/json",
        "-H",
        f"X-Amz-Date: {signed_headers['x-amz-date']}",
        "-H",
        f"X-Amz-Content-Sha256: {signed_headers['x-amz-content-sha256']}",
        "-H",
        f"Authorization: {authorization}",
    ]
    if "x-amz-security-token" in signed_headers:
        args.extend(["-H", f"X-Amz-Security-Token: {signed_headers['x-amz-security-token']}"])
    args.extend(["--data-binary", payload.decode("utf-8")])

    return subprocess.run(args, capture_output=True, text=True, check=False)


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

    for block in data.get("output", {}).get("message", {}).get("content", []):
        if isinstance(block, dict) and block.get("text"):
            return block["text"]
    return json.dumps(data, indent=2)[:4000]


def main() -> int:
    args = parse_args()
    model_id = select_model(args.model_id, args.terraform_bedrock_path)
    access_key = read_credential("AWS_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID: ")
    secret_key = read_credential(
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SECRET_ACCESS_KEY: ",
        secret=True,
    )
    session_token = os.environ.get("AWS_SESSION_TOKEN", "").strip()

    if not access_key or not secret_key:
        return 2

    url = (
        f"https://bedrock-runtime.{args.region}.amazonaws.com"
        f"/model/{model_id}/converse"
    )
    payload = build_payload(args.message, args.max_tokens, args.temperature)
    authorization, signed_headers = build_authorization(
        method="POST",
        service="bedrock",
        region=args.region,
        url=url,
        payload=payload,
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
    )

    try:
        result = run_curl(
            url=url,
            timeout=args.timeout,
            payload=payload,
            authorization=authorization,
            signed_headers=signed_headers,
        )
    except FileNotFoundError:
        print("curl is required but was not found in PATH.", file=sys.stderr)
        return 127

    body, status = split_response(result.stdout)
    if args.ansible_raw:
        sys.stdout.write(body)
        sys.stdout.write(f"\n__HTTP_STATUS__:{status}")
        sys.stderr.write(result.stderr)
        return result.returncode

    print("Direct Bedrock model test")
    print(f"Region: {args.region}")
    print(f"Model: {model_id}")
    print(f"URL: {url}")
    print(f"HTTP status: {status}")
    print(f"curl exit code: {result.returncode}")
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
