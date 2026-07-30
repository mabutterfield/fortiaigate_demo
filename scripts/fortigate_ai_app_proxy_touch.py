#!/usr/bin/env python3
"""Touch AI application endpoints for FortiGate application-control testing.

The default path sends direct traffic with no proxy. Use --proxy-url only when
testing a FortiGate explicit proxy. The script is intentionally scoped to one
execution and ignores proxy-related environment variables unless
--honor-proxy-env is set.
"""

from __future__ import annotations

import argparse
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


@dataclass(frozen=True)
class Target:
    name: str
    url: str


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


def parse_targets(app_args: list[str], include_defaults: bool) -> list[Target]:
    targets: list[Target] = []
    if include_defaults or not app_args:
        targets.extend(Target(name, url) for name, url in DEFAULT_APPS.items())

    for raw_arg in app_args:
        for item in [part.strip() for part in raw_arg.split(",") if part.strip()]:
            if item in DEFAULT_APPS:
                targets.append(Target(item, DEFAULT_APPS[item]))
                continue
            if "=" in item:
                name, url = item.split("=", 1)
                targets.append(Target(name.strip(), url.strip()))
                continue
            if item.startswith("http://") or item.startswith("https://"):
                parsed = urllib.parse.urlsplit(item)
                targets.append(Target(parsed.netloc or "custom", item))
                continue
            raise SystemExit(
                f"Unknown app target '{item}'. Use --list-apps, a URL, or name=url."
            )

    seen: set[tuple[str, str]] = set()
    unique_targets: list[Target] = []
    for target in targets:
        key = (target.name, target.url)
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
    method: str,
    timeout: float,
    user_agent: str,
    read_bytes: int,
    range_request: bool,
) -> Result:
    start = time.monotonic()
    request = urllib.request.Request(
        target.url,
        method=method,
        headers={
            "User-Agent": user_agent,
            "Accept": "*/*",
        },
    )
    if method == "GET" and read_bytes > 0 and range_request:
        request.add_header("Range", f"bytes=0-{read_bytes - 1}")

    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(read_bytes) if method == "GET" and read_bytes > 0 else b""
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return Result(
                name=target.name,
                url=target.url,
                method=method,
                status=response.status,
                outcome="reached",
                elapsed_ms=elapsed_ms,
                bytes_read=len(body),
            )
    except urllib.error.HTTPError as exc:
        body = exc.read(read_bytes) if method == "GET" and read_bytes > 0 else b""
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
    print(f"Method: {args.method}")
    print(f"Timeout: {args.timeout}s")
    print(f"Read bytes: {args.read_bytes if args.method == 'GET' else 0}")
    print(f"Range request: {'yes' if args.range_request else 'no'}")
    print(f"User-Agent: {args.user_agent}")
    print(f"Proxy environment: {'honored' if args.honor_proxy_env else 'ignored for this process'}")
    print("")
    print("Targets:")
    for target in targets:
        print(f"- {target.name}: {target.url}")


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
            "Touch well-known AI application hosts to generate real FortiGate "
            "application-control evidence."
        )
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
            "Repeat as needed. Defaults are used when no --app is supplied."
        ),
    )
    parser.add_argument(
        "--all-defaults",
        action="store_true",
        help="Include all default app targets even when custom --app values are supplied.",
    )
    parser.add_argument(
        "--list-apps",
        action="store_true",
        help="Print built-in app targets and exit.",
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
        "--json-output",
        type=Path,
        help="Optional JSON result path, preferably under ignored docs/raw-output/.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.list_apps:
        for name, url in DEFAULT_APPS.items():
            print(f"{name}: {url}")
        return 0

    targets = parse_targets(args.app, args.all_defaults)
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
            method=args.method,
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
