import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


DATA_PATH = os.environ.get("MCP_DATA_PATH", "/app/data/tools.json")
PORT = int(os.environ.get("MCP_LISTEN_PORT", "8000"))


def load_data():
    with open(DATA_PATH, "r", encoding="utf-8") as data_file:
        return json.load(data_file)


def json_response(handler, status, payload):
    body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def lookup(collection, key_name, arguments):
    key_value = arguments.get(key_name)
    if not key_value:
        return False, {"error": f"missing required argument: {key_name}"}

    data = load_data().get(collection, {})
    item = data.get(key_value)
    if not item:
        return False, {"error": f"{collection} entry not found", key_name: key_value}

    return True, item


def normalized(value):
    return str(value or "").strip().lower()


def matches_filters(item, filters):
    for key, expected in filters.items():
        if expected in ("", None):
            continue
        if normalized(item.get(key)) != normalized(expected):
            return False
    return True


def search_collection(collection, filters):
    records = load_data().get(collection, {})
    items = [item for item in records.values() if matches_filters(item, filters)]
    return True, {"count": len(items), "items": items}


def policy_search(arguments):
    query = normalized(arguments.get("query"))
    policies = load_data().get("policies", {})
    if not query:
        return True, {"count": len(policies), "items": list(policies.values())}

    items = []
    for policy in policies.values():
        haystack = " ".join(str(value) for value in policy.values()).lower()
        if query in haystack:
            items.append(policy)
    return True, {"count": len(items), "items": items}


def customer_ticket_summary(arguments):
    data = load_data()
    ticket_filters = {
        "status": arguments.get("ticket_status", arguments.get("status", "")),
        "severity": arguments.get("severity", ""),
        "customer_id": arguments.get("customer_id", ""),
    }
    tickets = [
        ticket
        for ticket in data.get("tickets", {}).values()
        if matches_filters(ticket, ticket_filters)
    ]

    customers = data.get("customers", {})
    summary = []
    for ticket in tickets:
        customer = customers.get(ticket.get("customer_id"), {})
        summary.append({"customer": customer, "ticket": ticket})

    return True, {"count": len(summary), "items": summary}


def run_tool(tool_name, arguments):
    if tool_name == "echo":
        return True, {"echo": arguments}
    if tool_name == "customer_lookup":
        return lookup("customers", "customer_id", arguments)
    if tool_name == "ticket_lookup":
        return lookup("tickets", "ticket_id", arguments)
    if tool_name == "policy_lookup":
        return lookup("policies", "policy_id", arguments)
    if tool_name == "customer_search":
        return search_collection(
            "customers",
            {
                "customer_id": arguments.get("customer_id", ""),
                "status": arguments.get("status", ""),
                "tier": arguments.get("tier", ""),
                "region": arguments.get("region", ""),
            },
        )
    if tool_name == "ticket_search":
        return search_collection(
            "tickets",
            {
                "ticket_id": arguments.get("ticket_id", ""),
                "customer_id": arguments.get("customer_id", ""),
                "status": arguments.get("status", ""),
                "severity": arguments.get("severity", ""),
            },
        )
    if tool_name == "policy_search":
        return policy_search(arguments)
    if tool_name == "customer_ticket_summary":
        return customer_ticket_summary(arguments)
    return False, {"error": "unknown tool", "tool": tool_name}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "customer_lookup",
            "description": "Return deterministic demo customer metadata by customer_id.",
            "parameters": {
                "type": "object",
                "properties": {"customer_id": {"type": "string", "description": "Customer ID such as CUST-1001."}},
                "required": ["customer_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ticket_lookup",
            "description": "Return deterministic demo support ticket metadata by ticket_id.",
            "parameters": {
                "type": "object",
                "properties": {"ticket_id": {"type": "string", "description": "Ticket ID such as TCK-2001."}},
                "required": ["ticket_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "policy_lookup",
            "description": "Return deterministic demo policy/document metadata by policy_id.",
            "parameters": {
                "type": "object",
                "properties": {"policy_id": {"type": "string", "description": "Policy ID such as POL-3001."}},
                "required": ["policy_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "customer_search",
            "description": "Search demo customers by optional customer_id, status, tier, or region filters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string"},
                    "status": {"type": "string", "description": "Customer status such as active."},
                    "tier": {"type": "string", "description": "Customer tier such as enterprise or standard."},
                    "region": {"type": "string", "description": "Customer region such as us-east or us-west."},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ticket_search",
            "description": "Search demo support tickets by optional ticket_id, customer_id, status, or severity filters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                    "customer_id": {"type": "string"},
                    "status": {"type": "string", "description": "Ticket status such as open, waiting, or closed."},
                    "severity": {"type": "string", "description": "Ticket severity such as high, medium, or low."},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "policy_search",
            "description": "Search demo policy documents. Use an empty query to list all policies.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Text to search in policy titles and summaries."}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "customer_ticket_summary",
            "description": "Return customers joined with matching support tickets. Useful for questions like all customers with open tickets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_status": {"type": "string", "description": "Ticket status filter, for example open."},
                    "severity": {"type": "string", "description": "Ticket severity filter."},
                    "customer_id": {"type": "string", "description": "Optional customer ID filter."},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "echo",
            "description": "Return the submitted arguments for connectivity testing.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": True},
        },
    },
]


class McpDemoHandler(BaseHTTPRequestHandler):
    server_version = "mcp-demo/0.1.0"

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

    def do_GET(self):
        parsed = urlparse(self.path)
        query = {key: values[0] for key, values in parse_qs(parsed.query).items()}

        if parsed.path == "/health":
            json_response(self, 200, {"status": "ok"})
            return

        if parsed.path == "/tools":
            json_response(self, 200, {"tools": TOOLS})
            return

        get_routes = {
            "/tools/customer": ("customer_lookup", query),
            "/tools/ticket": ("ticket_lookup", query),
            "/tools/policy": ("policy_lookup", query),
            "/tools/echo": ("echo", query)
        }
        if parsed.path in get_routes:
            tool_name, arguments = get_routes[parsed.path]
            ok, result = run_tool(tool_name, arguments)
            json_response(self, 200 if ok else 400, {"ok": ok, "tool": tool_name, "result": result})
            return

        json_response(self, 404, {"error": "not found", "path": parsed.path})

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b"{}"

        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            json_response(self, 400, {"error": "invalid json", "detail": str(exc)})
            return

        if parsed.path == "/mcp":
            tool_name = payload.get("tool")
            arguments = payload.get("arguments", {})
        elif parsed.path.startswith("/tools/"):
            tool_name = parsed.path.rsplit("/", 1)[-1]
            arguments = payload.get("arguments", payload)
        else:
            json_response(self, 404, {"error": "not found", "path": parsed.path})
            return

        ok, result = run_tool(tool_name, arguments)
        json_response(self, 200 if ok else 400, {"ok": ok, "tool": tool_name, "result": result})


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), McpDemoHandler)
    print(f"MCP demo server listening on port {PORT}", flush=True)
    server.serve_forever()
