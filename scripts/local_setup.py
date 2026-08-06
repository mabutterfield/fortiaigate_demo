#!/usr/bin/env python3
"""Generate local FortiAIGate deployment inventory and vars."""

from __future__ import annotations

import argparse
import csv
import getpass
import ipaddress
import secrets
import shlex
import socket
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from io import StringIO
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_INVENTORY = REPO_ROOT / "ansible/inventory/local.generated.ini"
LOCAL_VARS = REPO_ROOT / "ansible/group_vars/local.generated.yml"
LOCAL_SECRETS = REPO_ROOT / "ansible/group_vars/local.secrets.yml"
REGISTRY_VARS = REPO_ROOT / "ansible/group_vars/registry.generated.yml"
FORTIGATE_LOCAL_INVENTORY = REPO_ROOT / "ansible/inventory/fortigate.local.generated.ini"
FORTIWEB_LOCAL_INVENTORY = REPO_ROOT / "ansible/inventory/fortiweb.local.generated.ini"

DEFAULT_K3S_CLUSTER_CIDR = "10.60.0.0/16"
DEFAULT_K3S_SERVICE_CIDR = "10.70.0.0/16"
DEFAULT_K3S_CLUSTER_DNS = "10.70.0.10"
DEFAULT_LOCAL_HOST = "linux_host"
DEFAULT_REGISTRY = "docker_repo_host:5000"
DEFAULT_LOCAL_APPLIANCE_ADMIN = "apiadmin"
T4_COMPUTE_CAPABILITY = 7.5
SKIP_SSH_PRIVATE_KEY_NAMES = {
    "authorized_keys",
    "config",
    "environment",
    "known_hosts",
    "known_hosts.old",
}


@dataclass
class SshTarget:
    alias: str
    host: str
    user: str
    key_path: str
    password: str


@dataclass
class Gpu:
    index: str
    uuid: str
    pci_bus_id: str
    name: str
    compute_cap: str
    memory_mb: str

    @property
    def compute_cap_float(self) -> float | None:
        try:
            return float(self.compute_cap)
        except ValueError:
            return None

    @property
    def compatible(self) -> bool:
        value = self.compute_cap_float
        return value is not None and value >= T4_COMPUTE_CAPABILITY


@dataclass
class ApplianceBootstrapResult:
    key: str
    enabled: bool
    generated_vars: dict[str, str]
    secret_content: str
    access_cidrs: list[str]


def print_header(message: str) -> None:
    print(f"\n== {message} ==")


def prompt_text(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value if value else default


def prompt_secret(prompt: str) -> str:
    return getpass.getpass(f"{prompt}: ").strip()


def prompt_yes_no(prompt: str, default: bool = True) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    while True:
        value = input(f"{prompt}{suffix}: ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Answer yes or no.")


def prompt_cidr(prompt: str, default: str) -> str:
    while True:
        value = prompt_text(prompt, default)
        try:
            return str(ipaddress.ip_network(value, strict=False))
        except ValueError as error:
            print(f"Invalid CIDR: {error}")


def prompt_cidr_list(prompt: str, defaults: list[str]) -> list[str]:
    default_text = ", ".join(defaults)
    while True:
        value = prompt_text(prompt, default_text).strip()
        values = [item.strip() for item in value.split(",") if item.strip()]
        if not values:
            print("Enter at least one CIDR.")
            continue
        normalized: list[str] = []
        try:
            for cidr in values:
                network = str(ipaddress.ip_network(cidr, strict=False))
                if network not in normalized:
                    normalized.append(network)
        except ValueError as error:
            print(f"Invalid CIDR: {error}")
            continue
        return normalized


def prompt_ip_or_host(prompt: str, default: str) -> str:
    while True:
        value = prompt_text(prompt, default).strip()
        if value:
            return value
        print("Enter an IP address or DNS name.")


def prompt_optional_ip(prompt: str, default: str = "") -> str:
    while True:
        value = prompt_text(prompt, default).strip()
        if not value:
            return ""
        try:
            ipaddress.ip_address(value)
            return value
        except ValueError as error:
            print(f"Invalid IP address: {error}")


def display_path(path: Path) -> str:
    home = Path.home()
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(home.resolve()))
    except ValueError:
        return str(path)


def list_local_ssh_private_keys() -> list[Path]:
    ssh_dir = Path.home() / ".ssh"
    if not ssh_dir.exists():
        return []

    candidates: list[Path] = []
    for path in ssh_dir.iterdir():
        if not path.is_file():
            continue
        if path.name in SKIP_SSH_PRIVATE_KEY_NAMES:
            continue
        if path.name.endswith(".pub"):
            continue
        if path.name.startswith("known_hosts"):
            continue
        candidates.append(path)
    return sorted(candidates)


def choose_local_ssh_private_key(default_private_key: str, host_alias: str) -> str:
    print_header("Local SSH Private Key")
    candidates = list_local_ssh_private_keys()
    candidate_display = [display_path(path) for path in candidates]
    fallback = default_private_key or ""

    if candidates:
        print("Likely private keys in ~/.ssh:")
        for index, path_text in enumerate(candidate_display, start=1):
            marker = " (current)" if path_text == default_private_key else ""
            print(f"{index}. {path_text}{marker}")
        print("m. Enter a path manually")
        print("s. Use SSH config or ssh-agent")

    while True:
        selected = prompt_text("Local SSH private key number, path, m, or s", fallback or "s").strip()
        if selected.lower() in {"", "s", "skip", "ssh", "agent", "ssh-agent", "config"}:
            return ""
        if selected.lower() == "m":
            manual = prompt_text("Local SSH private key path", fallback or f"~/.ssh/{host_alias}")
            if manual:
                return manual
        if selected.isdigit() and candidates:
            index = int(selected)
            if 1 <= index <= len(candidates):
                return candidate_display[index - 1]
        if selected:
            return selected
        print("Choose a listed number, m, s, or enter a private key path.")


def resolve_host_ip(host: str) -> str:
    try:
        infos = socket.getaddrinfo(host, None, family=socket.AF_INET, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return ""
    for info in infos:
        address = info[4][0]
        if address:
            return address
    return ""


def yaml_unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_generated_yaml(path: Path) -> dict[str, str | list[str]]:
    if not path.exists():
        return {}

    values: dict[str, str | list[str]] = {}
    current_list_key = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#") or raw_line.strip() == "---":
            continue
        if raw_line.startswith(" ") and current_list_key and raw_line.strip().startswith("- "):
            current = values.setdefault(current_list_key, [])
            if isinstance(current, list):
                current.append(yaml_unquote(raw_line.strip()[2:].strip()))
            continue
        current_list_key = ""
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not value:
            values[key] = []
            current_list_key = key
        else:
            values[key] = yaml_unquote(value)
    return values


def load_inventory_defaults(path: Path, group: str) -> tuple[str, dict[str, str]]:
    if not path.exists():
        return "", {}

    host_alias = ""
    values: dict[str, str] = {}
    section = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section == group and not host_alias:
            try:
                parts = shlex.split(line)
            except ValueError:
                parts = line.split()
            if parts:
                host_alias = parts[0]
            for part in parts[1:]:
                if "=" in part:
                    key, value = part.split("=", 1)
                    values[key] = value
            continue
        if section == f"{group}:vars" and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return host_alias, values


def generated_scalar(values: dict[str, str | list[str]], key: str, default: str = "") -> str:
    value = values.get(key, default)
    return value if isinstance(value, str) else default


def generated_list(values: dict[str, str | list[str]], key: str) -> list[str]:
    value = values.get(key, [])
    return value if isinstance(value, list) else []


def validate_no_overlap(named_cidrs: dict[str, str]) -> None:
    networks = {name: ipaddress.ip_network(value, strict=False) for name, value in named_cidrs.items()}
    failures: list[str] = []
    items = list(networks.items())
    for left_index, (left_name, left_net) in enumerate(items):
        for right_name, right_net in items[left_index + 1 :]:
            if left_net.overlaps(right_net):
                failures.append(f"{left_name} {left_net} overlaps {right_name} {right_net}")
    if failures:
        raise SystemExit("CIDR validation failed:\n- " + "\n- ".join(failures))


def run_command(argv: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=str(REPO_ROOT),
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def ssh_argv(target: SshTarget, remote_command: str) -> list[str]:
    argv = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=10",
    ]
    if target.key_path:
        argv.extend(["-i", str(Path(target.key_path).expanduser())])
    argv.append(f"{target.user}@{target.host}")
    argv.append(remote_command)
    return argv


def ssh_output(target: SshTarget, remote_command: str) -> str:
    result = run_command(ssh_argv(target, remote_command))
    if result.returncode != 0:
        output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        print(output)
        return ""
    return (result.stdout or "").strip()


def ssh_available(target: SshTarget) -> bool:
    if target.password:
        print("SSH password was provided. Discovery requires key/agent auth or sshpass; writing inventory without live discovery.")
        return False
    result = run_command(ssh_argv(target, "printf faig-local-ssh-ok"))
    if result.returncode == 0 and "faig-local-ssh-ok" in (result.stdout or ""):
        return True
    print("SSH discovery failed. The generated inventory can still be used after access is fixed.")
    if result.stderr:
        print(result.stderr.strip())
    return False


def shell_report(target: SshTarget) -> dict[str, str]:
    script = r"""
set -u
SERVER_IP="$(printf '%s\n' "${SSH_CONNECTION:-}" | awk '{print $3}')"
INTERFACE_CIDR=""
if [ -n "$SERVER_IP" ]; then
  INTERFACE_CIDR="$(ip -o -f inet addr show 2>/dev/null | awk -v ip="$SERVER_IP" '{split($4,a,"/"); if (a[1] == ip) {print $4; exit}}')"
fi
DEFAULT_ROUTE_INTERFACE="$(ip route show default 2>/dev/null | awk 'NR==1 {for (i=1; i<=NF; i++) if ($i == "dev") print $(i+1)}')"
DEFAULT_ROUTE_IP=""
DEFAULT_ROUTE_CIDR=""
if [ -n "$DEFAULT_ROUTE_INTERFACE" ]; then
  DEFAULT_ROUTE_CIDR="$(ip -o -f inet addr show dev "$DEFAULT_ROUTE_INTERFACE" 2>/dev/null | awk 'NR==1 {print $4}')"
  DEFAULT_ROUTE_IP="$(printf '%s\n' "$DEFAULT_ROUTE_CIDR" | awk -F/ '{print $1}')"
fi
printf 'hostname=%s\n' "$(hostname -f 2>/dev/null || hostname)"
printf 'ssh_server_ip=%s\n' "$SERVER_IP"
printf 'ssh_interface_cidr=%s\n' "$INTERFACE_CIDR"
printf 'default_route_interface=%s\n' "$DEFAULT_ROUTE_INTERFACE"
printf 'default_route_ip=%s\n' "$DEFAULT_ROUTE_IP"
printf 'default_route_cidr=%s\n' "$DEFAULT_ROUTE_CIDR"
printf 'kernel=%s\n' "$(uname -srmo)"
printf 'os=%s\n' "$(PRETTY_NAME=unknown; . /etc/os-release 2>/dev/null; printf '%s' "$PRETTY_NAME")"
printf 'cpu_cores=%s\n' "$(nproc 2>/dev/null || echo unknown)"
printf 'memory_mb=%s\n' "$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo 2>/dev/null || echo unknown)"
printf 'disk_root_available=%s\n' "$(df -h / | awk 'NR==2 {print $4}')"
printf 'docker=%s\n' "$(docker --version 2>/dev/null || echo missing)"
printf 'kubectl=%s\n' "$(kubectl version --client=true 2>/dev/null | head -n1 || echo missing)"
printf 'k3s=%s\n' "$(k3s --version 2>/dev/null | head -n1 || echo missing)"
printf 'nvidia_smi=%s\n' "$(command -v nvidia-smi 2>/dev/null || echo missing)"
"""
    output = ssh_output(target, script)
    facts: dict[str, str] = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            facts[key] = value
    return facts


def cidr_from_interface_address(value: str) -> str:
    if not value:
        return ""
    try:
        interface = ipaddress.ip_interface(value)
    except ValueError:
        return ""
    return str(interface.network)


def local_source_ip_for_target(host: str, port: int = 443) -> str:
    resolved = resolve_host_ip(host) or host
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((resolved, port))
            return sock.getsockname()[0]
    except OSError:
        return ""


def macos_interface_for_target(host: str) -> str:
    result = run_command(["route", "-n", "get", host])
    if result.returncode != 0:
        return ""
    for line in (result.stdout or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("interface:"):
            return stripped.split(":", 1)[1].strip()
    return ""


def macos_cidr_for_interface(interface: str, source_ip: str) -> str:
    if not interface:
        return ""
    result = run_command(["ifconfig", interface])
    if result.returncode != 0:
        return ""
    for line in (result.stdout or "").splitlines():
        parts = line.strip().split()
        if len(parts) >= 4 and parts[0] == "inet" and parts[1] == source_ip and "netmask" in parts:
            netmask_text = parts[parts.index("netmask") + 1]
            try:
                netmask_int = int(netmask_text, 16) if netmask_text.startswith("0x") else int(netmask_text)
                netmask = socket.inet_ntoa(netmask_int.to_bytes(4, "big"))
                return str(ipaddress.ip_network(f"{source_ip}/{netmask}", strict=False))
            except (ValueError, OSError):
                return ""
    return ""


def macos_primary_ipv4_cidr() -> str:
    result = run_command(["ifconfig"])
    if result.returncode != 0:
        return ""

    active = False
    for line in (result.stdout or "").splitlines():
        if line and not line.startswith("\t") and not line.startswith(" "):
            active = "UP" in line and "LOOPBACK" not in line
            continue
        if not active:
            continue
        parts = line.strip().split()
        if len(parts) >= 4 and parts[0] == "inet" and parts[1] != "127.0.0.1" and "netmask" in parts:
            source_ip = parts[1]
            netmask_text = parts[parts.index("netmask") + 1]
            try:
                netmask_int = int(netmask_text, 16) if netmask_text.startswith("0x") else int(netmask_text)
                netmask = socket.inet_ntoa(netmask_int.to_bytes(4, "big"))
                return str(ipaddress.ip_network(f"{source_ip}/{netmask}", strict=False))
            except (ValueError, OSError):
                continue
    return ""


def linux_cidr_for_source_ip(source_ip: str) -> str:
    if not source_ip:
        return ""
    result = run_command(["ip", "-o", "-f", "inet", "addr", "show"])
    if result.returncode != 0:
        return ""
    for line in (result.stdout or "").splitlines():
        fields = line.split()
        if "inet" not in fields:
            continue
        address = fields[fields.index("inet") + 1]
        if address.split("/", 1)[0] == source_ip:
            return cidr_from_interface_address(address)
    return ""


def linux_primary_ipv4_cidr() -> str:
    result = run_command(["ip", "-o", "-f", "inet", "addr", "show", "scope", "global"])
    if result.returncode != 0:
        return ""
    for line in (result.stdout or "").splitlines():
        fields = line.split()
        if "inet" not in fields:
            continue
        cidr = cidr_from_interface_address(fields[fields.index("inet") + 1])
        if cidr:
            return cidr
    return ""


def local_primary_ipv4_cidr() -> str:
    if sys.platform == "darwin":
        return macos_primary_ipv4_cidr()
    return linux_primary_ipv4_cidr()


def fallback_cidr_for_source_ip(source_ip: str) -> str:
    if not source_ip:
        return ""
    try:
        ipaddress.ip_address(source_ip)
    except ValueError:
        return ""
    return str(ipaddress.ip_network(f"{source_ip}/24", strict=False))


def suggested_local_backend_ip(lab_cidr: str, management_host: str, default_host_offset: int) -> str:
    try:
        network = ipaddress.ip_network(lab_cidr, strict=False)
        if network.version != 4:
            return ""
        management_ip = ipaddress.ip_address(resolve_host_ip(management_host) or management_host)
        if management_ip.version != 4:
            return ""
        octets = str(management_ip).split(".")
        host_offset = int(octets[-1]) + 100
        if host_offset <= 0 or host_offset >= network.num_addresses - 1:
            host_offset = default_host_offset
        candidate = network.network_address + host_offset
        if candidate not in network or candidate == network.broadcast_address:
            return ""
        return str(candidate)
    except (ValueError, IndexError):
        return ""


def discover_controller_cidr(target_host: str, target_port: str = "443") -> str:
    try:
        port = int(target_port)
    except ValueError:
        port = 443
    source_ip = local_source_ip_for_target(target_host, port)
    if not source_ip:
        return local_primary_ipv4_cidr()
    if sys.platform == "darwin":
        discovered = macos_cidr_for_interface(macos_interface_for_target(target_host), source_ip)
    else:
        discovered = linux_cidr_for_source_ip(source_ip)
    return discovered or fallback_cidr_for_source_ip(source_ip) or local_primary_ipv4_cidr()


def choose_lab_cidr(args: argparse.Namespace, facts: dict[str, str]) -> str:
    discovered = cidr_from_interface_address(facts.get("default_route_cidr", "")) or cidr_from_interface_address(facts.get("ssh_interface_cidr", ""))
    fallback = args.lab_cidr or discovered or "192.168.1.0/24"
    if args.non_interactive:
        return fallback
    if discovered:
        print_header("Local Routed CIDR")
        if facts.get("default_route_cidr"):
            print(f"Discovered from default-route interface {facts.get('default_route_interface')}: {facts.get('default_route_cidr')} -> {discovered}")
        else:
            print(f"Discovered from SSH-connected host interface: {facts.get('ssh_interface_cidr')} -> {discovered}")
    return prompt_cidr("Local routed CIDR", fallback)


def choose_local_access_cidrs(
    *,
    lab_cidr: str,
    existing_cidrs: list[str],
    appliance_hosts: list[tuple[str, str]],
    non_interactive: bool,
) -> list[str]:
    discovered: list[str] = []
    for host, port in appliance_hosts:
        cidr = discover_controller_cidr(host, port)
        if cidr and cidr not in discovered:
            discovered.append(cidr)

    defaults: list[str] = []
    for cidr in existing_cidrs + [lab_cidr] + discovered:
        if not cidr:
            continue
        try:
            normalized = str(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            continue
        if normalized not in defaults:
            defaults.append(normalized)

    if non_interactive:
        return defaults

    print_header("Local Access CIDRs")
    print("These CIDRs are allowed to reach local NodePorts and local appliance API trusthosts.")
    if discovered:
        print(f"Discovered controller/API source CIDR(s): {', '.join(discovered)}")
    return prompt_cidr_list("Local access CIDRs", defaults)


def discover_gpus(target: SshTarget) -> list[Gpu]:
    command = (
        "if command -v nvidia-smi >/dev/null 2>&1; then "
        "nvidia-smi --query-gpu=index,uuid,pci.bus_id,name,compute_cap,memory.total "
        "--format=csv,noheader,nounits; fi"
    )
    output = ssh_output(target, command)
    if not output:
        return []

    gpus: list[Gpu] = []
    reader = csv.reader(StringIO(output))
    for row in reader:
        values = [item.strip() for item in row]
        if len(values) < 6:
            continue
        gpus.append(Gpu(*values[:6]))
    return gpus


def print_system_report(facts: dict[str, str]) -> None:
    if not facts:
        return
    print_header("Ubuntu Host Facts")
    for key in ["hostname", "ssh_server_ip", "ssh_interface_cidr", "default_route_interface", "default_route_ip", "default_route_cidr", "os", "kernel", "cpu_cores", "memory_mb", "disk_root_available", "docker", "kubectl", "k3s", "nvidia_smi"]:
        print(f"{key}: {facts.get(key, 'unknown')}")


def print_gpu_table(gpus: list[Gpu]) -> None:
    print_header("GPU Inventory")
    if not gpus:
        print("No GPUs were discovered. If this is a fresh host, run local quickstart/bootstrap and rerun local_setup.py.")
        return
    print("Index  Compatible  Compute  Memory MiB  UUID                                  Name")
    for gpu in gpus:
        marker = "yes" if gpu.compatible else "warn"
        print(f"{gpu.index:<6} {marker:<10} {gpu.compute_cap:<8} {gpu.memory_mb:<11} {gpu.uuid:<37} {gpu.name}")
    print("Compatibility heuristic: T4-or-greater means CUDA compute capability >= 7.5.")


def select_gpus(prompt: str, gpus: list[Gpu], unavailable: set[str], default: str = "cpu-only") -> list[str]:
    available = [gpu for gpu in gpus if gpu.uuid not in unavailable]
    if not available:
        print(f"No GPUs remain for {prompt}; using cpu-only.")
        return []

    print_header(prompt)
    for gpu in available:
        marker = "compatible" if gpu.compatible else "older"
        print(f"{gpu.index}. {gpu.uuid} - {gpu.name}, {gpu.memory_mb} MiB, compute {gpu.compute_cap} ({marker})")
    print("Use comma-separated indexes or UUIDs, or cpu-only.")

    while True:
        value = prompt_text(prompt, default).strip()
        if value.lower() in {"", "cpu", "cpu-only", "none", "no"}:
            return []
        selected: list[str] = []
        valid = True
        for token in [item.strip() for item in value.split(",") if item.strip()]:
            match = next((gpu for gpu in available if gpu.index == token or gpu.uuid == token), None)
            if not match:
                print(f"Unknown GPU selection: {token}")
                valid = False
                break
            if match.uuid not in selected:
                selected.append(match.uuid)
        if valid:
            return selected


def gpu_selection_default(gpus: list[Gpu], existing_uuids: list[str], fallback: str) -> str:
    indexes = [gpu.index for gpu in gpus if gpu.uuid in set(existing_uuids)]
    return ",".join(indexes) if indexes else fallback


def yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def yaml_string_list(values: list[str]) -> str:
    if not values:
        return " []"
    return "\n" + "\n".join(f"  - {yaml_quote(value)}" for value in values)


def recommended_nvidia_suffix(selected_gpu_uuids: list[str], gpus: list[Gpu]) -> str:
    if not selected_gpu_uuids:
        return "580-server"
    selected = {uuid for uuid in selected_gpu_uuids}
    selected_gpus = [gpu for gpu in gpus if gpu.uuid in selected]
    if any((gpu.compute_cap_float is not None and gpu.compute_cap_float < T4_COMPUTE_CAPABILITY) for gpu in selected_gpus):
        return "580-server"
    return "595-server"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"wrote: {path.relative_to(REPO_ROOT)}")


def append_local_vars(content: str) -> None:
    with LOCAL_VARS.open("a", encoding="utf-8") as handle:
        handle.write("\n")
        handle.write(content)
        if not content.endswith("\n"):
            handle.write("\n")
    print(f"updated: {LOCAL_VARS.relative_to(REPO_ROOT)}")


def parse_simple_yaml_mapping(content: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def replace_managed_secret_block(secret_content: str) -> None:
    start = "# BEGIN FAIG LOCAL APPLIANCE MANAGED SECRETS"
    end = "# END FAIG LOCAL APPLIANCE MANAGED SECRETS"
    existing = LOCAL_SECRETS.read_text(encoding="utf-8") if LOCAL_SECRETS.exists() else "---\n"
    lines = existing.splitlines()
    output: list[str] = []
    existing_block: list[str] = []
    in_block = False
    for line in lines:
        if line.strip() == start:
            in_block = True
            continue
        if line.strip() == end:
            in_block = False
            continue
        if in_block:
            existing_block.append(line)
        else:
            output.append(line)
    base = "\n".join(output).rstrip()
    merged = parse_simple_yaml_mapping("\n".join(existing_block))
    merged.update(parse_simple_yaml_mapping(secret_content))
    merged_content = "\n".join(f"{key}: {value}" for key, value in merged.items())
    block = f"{start}\n{merged_content}\n{end}"
    content = f"{base}\n\n{block}\n" if base else f"---\n\n{block}\n"
    LOCAL_SECRETS.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_SECRETS.write_text(content, encoding="utf-8")
    LOCAL_SECRETS.chmod(0o600)
    print(f"updated: {LOCAL_SECRETS.relative_to(REPO_ROOT)}")


def generate_password(length: int = 24) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def https_url(host: str, port: str, suffix: str = "") -> str:
    port_part = "" if str(port).strip() == "443" else f":{str(port).strip()}"
    return f"https://{host}{port_part}{suffix}"


def render_local_inventory(target: SshTarget) -> str:
    parts = [
        "[fortiaigate]",
        f"{target.alias} ansible_host={target.host} ansible_user={target.user}",
        "",
        "[fortiaigate:vars]",
        "deployment_target=local",
        "ansible_python_interpreter=/usr/bin/python3",
    ]
    if target.key_path:
        parts.append(f"ansible_ssh_private_key_file={target.key_path}")
    if target.password:
        parts.append(f"ansible_password={target.password}")
        parts.append("ansible_become_password={{ ansible_password }}")
    return "\n".join(parts) + "\n"


def render_fortigate_local_inventory(host: str, port: str, api_admin: str, internal_ip: str = "") -> str:
    return f"""[fortigate]
local-fortigate ansible_host={host}

[fortigate:vars]
deployment_target=local
ansible_connection=httpapi
ansible_network_os=fortinet.fortios.fortios
ansible_httpapi_use_ssl=true
ansible_httpapi_validate_certs=false
ansible_httpapi_port={port}
fortigate_admin_port={port}
fortigate_api_admin={api_admin}
fortigate_public_ip={host}
fortigate_public_private_ip={host}
fortigate_admin_url={https_url(host, port)}
fortigate_api_url={https_url(host, port, "/api/v2")}
fortigate_vdom=root
fortigate_internal_ip={internal_ip}

[fortinet_appliances:children]
fortigate
"""


def render_fortiweb_local_inventory(host: str, port: str, admin_user: str, internal_ip: str = "") -> str:
    return f"""[fortiweb]
local-fortiweb ansible_host={host}

[fortiweb:vars]
deployment_target=local
ansible_connection=httpapi
ansible_network_os=fortinet.fortiweb.fwebos
ansible_httpapi_use_ssl=true
ansible_httpapi_validate_certs=false
ansible_httpapi_port={port}
fortiweb_admin_https_port={port}
fortiweb_admin_http_port=8080
fortiweb_hostname=faig-fortiweb-local
fortiweb_public_ip={host}
fortiweb_public_private_ip={host}
fortiweb_internal_ip={internal_ip}
fortiweb_admin_url={https_url(host, port)}
fortiweb_http_admin_url=http://{host}:8080
fortiweb_api_url={https_url(host, port, "/api/v2.0")}
fortiweb_vdom=root
fortiweb_username={admin_user}

[fortinet_appliances:children]
fortiweb
"""


def render_registry_vars(local_registry: str, repo_prefix: str) -> str:
    return f"""---
registry_type: local
local_registry: {yaml_quote(local_registry)}
local_registry_scheme: http
local_registry_insecure_skip_verify: true
registry: "{{{{ local_registry }}}}"
repo_prefix: {yaml_quote(repo_prefix)}
ecr_repo_prefix: "{{{{ repo_prefix }}}}"
fortiaigate_image_repository: "{{{{ registry }}}}/{{{{ repo_prefix }}}}"
chatbot_image_repository: "{{{{ registry }}}}/{{{{ repo_prefix }}}}/chatbot-basic"
fortiaigate_ecr_token_source: none
fortiaigate_image_pull_secrets: []
chatbot_ecr_token_source: none
chatbot_image_pull_secrets: []
k3s_private_registry_enabled: true
k3s_private_registry_host: "{{{{ local_registry }}}}"
k3s_private_registry_scheme: "{{{{ local_registry_scheme }}}}"
k3s_private_registry_insecure_skip_verify: "{{{{ local_registry_insecure_skip_verify }}}}"
"""


def render_local_vars(
    *,
    lab_name: str,
    ansible_user: str,
    lab_cidr: str,
    local_access_cidrs: list[str],
    k3s_public_ip: str,
    k3s_private_ip: str,
    k3s_cluster_cidr: str,
    k3s_service_cidr: str,
    k3s_cluster_dns: str,
    faig_gpus: list[str],
    ollama_gpus: list[str],
    nvidia_driver_suffix: str,
    gpu_inventory_captured: bool,
) -> str:
    expected_gpus = list(dict.fromkeys(faig_gpus + ollama_gpus))
    return f"""---
deployment_target: local
lab_name: {yaml_quote(lab_name)}
ansible_user: {yaml_quote(ansible_user)}
lab_routed_cidr: {yaml_quote(lab_cidr)}
local_access_cidrs:{yaml_string_list(local_access_cidrs)}
lab_static_ip_mode: true
lab_public_access_mode: local_lan

k3s_public_ip: {yaml_quote(k3s_public_ip)}
k3s_private_ip: {yaml_quote(k3s_private_ip)}
k3s_node_ip: {yaml_quote(k3s_private_ip)}
k3s_use_instance_store: false
k3s_cluster_cidr: {yaml_quote(k3s_cluster_cidr)}
k3s_service_cidr: {yaml_quote(k3s_service_cidr)}
k3s_cluster_dns: {yaml_quote(k3s_cluster_dns)}

# Compatibility aliases for Ansible roles that still use AWS-shaped network facts.
aws_vpc_cidr: "{{{{ lab_routed_cidr }}}}"
aws_public_subnet_cidr: "{{{{ lab_routed_cidr }}}}"
aws_private_subnet_cidr: "{{{{ lab_routed_cidr }}}}"
aws_fortiweb_internal_subnet_cidr: "{{{{ lab_routed_cidr }}}}"

local_gpu_inventory_captured: {str(gpu_inventory_captured).lower()}
local_faig_gpu_uuids:{yaml_string_list(faig_gpus)}
local_ollama_gpu_uuids:{yaml_string_list(ollama_gpus)}
nvidia_driver_package: nvidia-driver-{nvidia_driver_suffix}
nvidia_utils_package: nvidia-utils-{nvidia_driver_suffix}
nvidia_driver_expected_gpu_uuids:{yaml_string_list(expected_gpus)}

# Local deployments use Ollama instead of AWS Bedrock for the demo LLM backend.
ollama_enabled: true
ollama_service_type: NodePort
ollama_node_port: 30085
ollama_node_port_allowed_cidrs: "{{{{ local_access_cidrs }}}}"
ollama_models:
  - gpt-oss:20b
ollama_model: "{{{{ ollama_models[0] }}}}"
ollama_keep_alive: 60m
ollama_context_length: 32768
ollama_internal_base_url: http://ollama.ollama.svc.cluster.local:11434/v1
ollama_public_base_url: "http://{{{{ k3s_public_ip }}}}:{{{{ ollama_node_port }}}}/v1"
ollama_base_url: "{{{{ ollama_internal_base_url }}}}"
direct_model_provider: ollama
direct_model_ollama_model: "{{{{ ollama_model }}}}"
direct_model_ollama_base_url: "{{{{ ollama_public_base_url }}}}"
direct_model_ollama_execute_on_k3s_host: false
direct_model_bedrock_read_credentials_from_terraform: false
litellm_bedrock_enabled: false
litellm_bedrock_use_terraform_output: false
litellm_use_ollama_model_list: true
litellm_ollama_base_url: "{{{{ ollama_internal_base_url | regex_replace('/v1/?$', '') }}}}"
litellm_passthrough_model_alias: pass-model
litellm_faig_backend_downstream_model: "{{{{ litellm_passthrough_model_alias }}}}"

# Local syslog keeps FortiAIGate log collection in-cluster and writes to a file
# inside the collector pod instead of requiring an AWS S3 archive bucket.
fortiaigate_syslog_collector_enabled: true
fortiaigate_syslog_output: file
fortiaigate_syslog_test_check_s3: false
fortiaigate_syslog_test_wait_seconds: 8
"""


def run_bootstrap_playbook(playbook: str, inventory: Path, bootstrap_vars: dict[str, str | list[str]]) -> str:
    result_file = tempfile.NamedTemporaryFile(
        mode="w",
        prefix="faig-local-bootstrap-result-",
        suffix=".yml",
        delete=False,
    )
    result_path = Path(result_file.name)
    result_file.close()
    result_path.chmod(0o600)

    vars_file = tempfile.NamedTemporaryFile(
        mode="w",
        prefix="faig-local-bootstrap-vars-",
        suffix=".yml",
        delete=False,
        encoding="utf-8",
    )
    vars_path = Path(vars_file.name)
    try:
        vars_file.write("---\n")
        for key, value in bootstrap_vars.items():
            if isinstance(value, list):
                vars_file.write(f"{key}:{yaml_string_list(value)}\n")
            else:
                vars_file.write(f"{key}: {yaml_quote(value)}\n")
        vars_file.write(f"local_bootstrap_result_file: {yaml_quote(str(result_path))}\n")
        vars_file.close()
        vars_path.chmod(0o600)

        argv = [
            "ansible-playbook",
            "-i",
            str(inventory),
            str(REPO_ROOT / "ansible/playbooks" / playbook),
            "-e",
            f"@{vars_path}",
        ]
        result = subprocess.run(
            argv,
            cwd=str(REPO_ROOT),
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        if result.returncode != 0:
            raise SystemExit(result.returncode)
        return result_path.read_text(encoding="utf-8")
    finally:
        vars_path.unlink(missing_ok=True)
        result_path.unlink(missing_ok=True)


def run_status_playbook(playbook: str, inventory: Path) -> bool:
    argv = [
        "ansible-playbook",
        "-i",
        str(inventory),
        str(REPO_ROOT / "ansible/playbooks" / playbook),
    ]
    result = subprocess.run(
        argv,
        cwd=str(REPO_ROOT),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode == 0


def prompt_fortigate_appliance(
    *,
    inventory_defaults: dict[str, str],
    generated_defaults: dict[str, str | list[str]],
    secret_defaults: dict[str, str | list[str]],
    current_access_cidrs: list[str],
    lab_cidr: str,
) -> ApplianceBootstrapResult:
    key = "fortigate"
    print_header("FortiGate Local Appliance")
    default_enabled = FORTIGATE_LOCAL_INVENTORY.exists() or generated_scalar(generated_defaults, "fortigate_local_enabled") == "true"
    if not prompt_yes_no("Configure an existing local FortiGate now?", default_enabled):
        print("FortiGate: do not install/configure selected.")
        if FORTIGATE_LOCAL_INVENTORY.exists():
            print(f"Leaving existing ignored inventory in place: {FORTIGATE_LOCAL_INVENTORY.relative_to(REPO_ROOT)}")
        return ApplianceBootstrapResult(key=key, enabled=False, generated_vars={}, secret_content="", access_cidrs=[])

    host_default = inventory_defaults.get("ansible_host") or generated_scalar(generated_defaults, "fortigate_public_ip")
    port_default = inventory_defaults.get("ansible_httpapi_port") or generated_scalar(generated_defaults, "fortigate_admin_port", "443")
    api_admin_default = inventory_defaults.get("fortigate_api_admin") or generated_scalar(generated_defaults, "fortigate_api_admin", DEFAULT_LOCAL_APPLIANCE_ADMIN)
    host = prompt_ip_or_host("FortiGate management/API IP or DNS", host_default)
    port = prompt_text("FortiGate HTTPS/API port", port_default)
    api_admin = prompt_text("FortiGate managed API admin user", api_admin_default)
    existing_internal_ip = inventory_defaults.get("fortigate_internal_ip") or generated_scalar(generated_defaults, "fortigate_internal_ip")
    if existing_internal_ip == host:
        existing_internal_ip = ""
    internal_ip_default = existing_internal_ip or suggested_local_backend_ip(lab_cidr, host, 120)
    internal_ip = prompt_optional_ip("FortiGate port2/backend IP on local routed network, empty if unknown", internal_ip_default)
    host_controller_cidr = discover_controller_cidr(host, port)
    trusthost_cidrs = list(dict.fromkeys(current_access_cidrs + ([host_controller_cidr] if host_controller_cidr else [])))

    write_text(FORTIGATE_LOCAL_INVENTORY, render_fortigate_local_inventory(host, port, api_admin, internal_ip))
    generated_vars = {
        "fortigate_local_enabled": "true",
        "fortigate_api_admin": api_admin,
        "fortigate_admin_port": port,
        "fortigate_public_ip": host,
        "fortigate_public_private_ip": host,
        "fortigate_internal_ip": internal_ip,
        "fortigate_admin_url": https_url(host, port),
        "fortigate_api_url": https_url(host, port, "/api/v2"),
        "fortigate_vdom": "root",
        "fortigate_bootstrap_api_account_name": api_admin,
        "fortigate_bootstrap_api_account_trusthost_cidrs": "{{ local_access_cidrs }}",
        "fortigate_readonly_api_account_trusthost_cidrs": "{{ local_access_cidrs }}",
        "fortigate_readonly_api_account_include_vpc_cidr": "false",
    }
    if internal_ip:
        generated_vars["mcp_fortigate_base_url"] = https_url(internal_ip, port)

    secret_content = ""
    existing_token = generated_scalar(secret_defaults, "fortigate_api_key")
    existing_credential_ready = False
    existing_credential_failed = False
    if existing_token:
        if prompt_yes_no("Existing FortiGate managed API token found. Use it and run status test now?", True):
            existing_credential_ready = run_status_playbook("status_fortigate.yml", FORTIGATE_LOCAL_INVENTORY)
            existing_credential_failed = not existing_credential_ready
            if existing_credential_ready:
                print("FortiGate existing managed API token validated.")
            else:
                print("FortiGate existing managed API token status test failed; bootstrap is recommended.")
        else:
            print("Skipped FortiGate existing managed API token test.")

    manage_default = len(existing_token) == 0 or existing_credential_failed
    if not existing_credential_ready and prompt_yes_no("Create/update FortiGate apiadmin and store managed API token now?", manage_default):
        if host_controller_cidr and host_controller_cidr not in current_access_cidrs:
            print(f"Including controller/API source CIDR in FortiGate trusthosts: {host_controller_cidr}")
        bootstrap_user = prompt_text("FortiGate current admin user", "admin")
        bootstrap_password = prompt_secret("FortiGate current admin password")
        secret_content = run_bootstrap_playbook(
            "bootstrap_fortigate_local_api.yml",
            FORTIGATE_LOCAL_INVENTORY,
            {
                "fortigate_local_bootstrap_username": bootstrap_user,
                "fortigate_local_bootstrap_password": bootstrap_password,
                "fortigate_local_bootstrap_api_admin": api_admin,
                "fortigate_local_bootstrap_trusthost_cidrs": trusthost_cidrs,
            },
        )
    elif not existing_credential_ready:
        print("Skipped FortiGate API admin bootstrap. Quickstart can run after local.secrets.yml contains fortigate_api_key.")

    return ApplianceBootstrapResult(key=key, enabled=True, generated_vars=generated_vars, secret_content=secret_content, access_cidrs=trusthost_cidrs)


def prompt_fortiweb_appliance(
    *,
    inventory_defaults: dict[str, str],
    generated_defaults: dict[str, str | list[str]],
    secret_defaults: dict[str, str | list[str]],
    current_access_cidrs: list[str],
    lab_cidr: str,
) -> ApplianceBootstrapResult:
    key = "fortiweb"
    print_header("FortiWeb Local Appliance")
    default_enabled = FORTIWEB_LOCAL_INVENTORY.exists() or generated_scalar(generated_defaults, "fortiweb_local_enabled") == "true"
    if not prompt_yes_no("Configure an existing local FortiWeb now?", default_enabled):
        print("FortiWeb: do not install/configure selected.")
        if FORTIWEB_LOCAL_INVENTORY.exists():
            print(f"Leaving existing ignored inventory in place: {FORTIWEB_LOCAL_INVENTORY.relative_to(REPO_ROOT)}")
        return ApplianceBootstrapResult(key=key, enabled=False, generated_vars={}, secret_content="", access_cidrs=[])

    host_default = inventory_defaults.get("ansible_host") or generated_scalar(generated_defaults, "fortiweb_public_ip")
    port_default = inventory_defaults.get("ansible_httpapi_port") or generated_scalar(generated_defaults, "fortiweb_admin_https_port", "443")
    managed_user_default = inventory_defaults.get("fortiweb_username") or generated_scalar(generated_defaults, "fortiweb_username", DEFAULT_LOCAL_APPLIANCE_ADMIN)
    host = prompt_ip_or_host("FortiWeb management/API IP or DNS", host_default)
    port = prompt_text("FortiWeb HTTPS/API port", port_default)
    managed_user = prompt_text("FortiWeb managed admin user", managed_user_default)
    access_profile = prompt_text("FortiWeb managed admin access profile", "prof_admin")
    existing_internal_ip = inventory_defaults.get("fortiweb_internal_ip") or generated_scalar(generated_defaults, "fortiweb_internal_ip")
    if existing_internal_ip == host:
        existing_internal_ip = ""
    internal_ip_default = existing_internal_ip or suggested_local_backend_ip(lab_cidr, host, 130)
    internal_ip = prompt_optional_ip("FortiWeb port2/backend IP on local routed network, empty to skip port2 config", internal_ip_default)
    managed_password = generate_password()
    host_controller_cidr = discover_controller_cidr(host, port)
    trusthost_cidrs = list(dict.fromkeys(current_access_cidrs + ([host_controller_cidr] if host_controller_cidr else [])))
    managed_trusthost_cidrs = list(dict.fromkeys(([host_controller_cidr] if host_controller_cidr else []) + trusthost_cidrs))
    managed_trusthostv4 = " ".join(managed_trusthost_cidrs) if managed_trusthost_cidrs else "0.0.0.0/0"

    write_text(FORTIWEB_LOCAL_INVENTORY, render_fortiweb_local_inventory(host, port, managed_user, internal_ip))
    generated_vars = {
        "fortiweb_local_enabled": "true",
        "fortiweb_username": managed_user,
        "fortiweb_admin_https_port": port,
        "fortiweb_admin_http_port": "8080",
        "fortiweb_hostname": "faig-fortiweb-local",
        "fortiweb_public_ip": host,
        "fortiweb_public_private_ip": host,
        "fortiweb_internal_ip": internal_ip,
        "fortiweb_admin_url": https_url(host, port),
        "fortiweb_http_admin_url": f"http://{host}:8080",
        "fortiweb_api_url": https_url(host, port, "/api/v2.0"),
        "fortiweb_vdom": "root",
        "fortiweb_mcp_proxy_enabled": "true",
        "fortiweb_static_route_vpc_gateway": "",
    }

    secret_content = ""
    existing_password = generated_scalar(secret_defaults, "fortiweb_admin_password_override")
    existing_credential_ready = False
    existing_credential_failed = False
    if existing_password:
        if prompt_yes_no("Existing FortiWeb managed admin password found. Use it and run status test now?", True):
            existing_credential_ready = run_status_playbook("status_fortiweb.yml", FORTIWEB_LOCAL_INVENTORY)
            existing_credential_failed = not existing_credential_ready
            if existing_credential_ready:
                print("FortiWeb existing managed admin password validated.")
            else:
                print("FortiWeb existing managed admin password status test failed; bootstrap is recommended.")
        else:
            print("Skipped FortiWeb existing managed admin password test.")

    manage_default = len(existing_password) == 0 or existing_credential_failed
    if not existing_credential_ready and prompt_yes_no("Create/update FortiWeb apiadmin and store managed password now?", manage_default):
        if host_controller_cidr and host_controller_cidr not in current_access_cidrs:
            print(f"Including controller/API source CIDR in FortiWeb managed admin trusthostv4: {host_controller_cidr}")
        print(f"FortiWeb managed admin trusthostv4: {managed_trusthostv4}")
        bootstrap_user = prompt_text("FortiWeb current admin user", "admin")
        bootstrap_password = prompt_secret("FortiWeb current admin password")
        secret_content = run_bootstrap_playbook(
            "bootstrap_fortiweb_local_admin.yml",
            FORTIWEB_LOCAL_INVENTORY,
            {
                "fortiweb_local_bootstrap_username": bootstrap_user,
                "fortiweb_local_bootstrap_password": bootstrap_password,
                "fortiweb_local_managed_username": managed_user,
                "fortiweb_local_managed_password": managed_password,
                "fortiweb_local_managed_access_profile": access_profile,
                "fortiweb_local_managed_trusthostv4": managed_trusthostv4,
            },
        )
    elif not existing_credential_ready:
        print("Skipped FortiWeb managed admin bootstrap. Quickstart can run after local.secrets.yml contains fortiweb_admin_password_override.")

    return ApplianceBootstrapResult(key=key, enabled=True, generated_vars=generated_vars, secret_content=secret_content, access_cidrs=trusthost_cidrs)


def render_appliance_local_vars(results: list[ApplianceBootstrapResult]) -> str:
    lines = ["# Local appliance facts generated by scripts/local_setup.py."]
    for result in results:
        if not result.enabled:
            continue
        for key, value in result.generated_vars.items():
            if value in {"true", "false"}:
                lines.append(f"{key}: {value}")
            else:
                lines.append(f"{key}: {yaml_quote(value)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n" if len(lines) > 1 else ""


def persist_appliance_result(result: ApplianceBootstrapResult) -> None:
    if result.secret_content.strip():
        replace_managed_secret_block(result.secret_content)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate local FortiAIGate deployment inventory and vars.")
    parser.add_argument("--non-interactive", action="store_true", help="Use defaults where possible and do not prompt for optional appliances.")
    parser.add_argument("--host", default=DEFAULT_LOCAL_HOST, help=f"Ubuntu host IP or DNS name. Default: {DEFAULT_LOCAL_HOST}.")
    parser.add_argument("--alias", default=DEFAULT_LOCAL_HOST, help=f"Ansible host alias. Default: {DEFAULT_LOCAL_HOST}.")
    parser.add_argument("--user", default="ubuntu", help="Ubuntu SSH user. Default: ubuntu.")
    parser.add_argument("--ssh-key", default="", help="SSH private key path. Empty uses ssh-agent/default SSH config.")
    parser.add_argument("--lab-cidr", default="", help="Local routed CIDR, for example 192.168.50.0/24.")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY, help=f"Local Docker registry. Default: {DEFAULT_REGISTRY}.")
    parser.add_argument("--repo-prefix", default="fortiaigate", help="Image repository prefix. Default: fortiaigate.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    local_defaults = load_generated_yaml(LOCAL_VARS)
    registry_defaults = load_generated_yaml(REGISTRY_VARS)
    secret_defaults = load_generated_yaml(LOCAL_SECRETS)
    local_alias, local_inventory_defaults = load_inventory_defaults(LOCAL_INVENTORY, "fortiaigate")
    _fortigate_alias, fortigate_inventory_defaults = load_inventory_defaults(FORTIGATE_LOCAL_INVENTORY, "fortigate")
    _fortiweb_alias, fortiweb_inventory_defaults = load_inventory_defaults(FORTIWEB_LOCAL_INVENTORY, "fortiweb")

    print("FortiAIGate local setup")
    print(f"Repo root: {REPO_ROOT}")
    print("This writes ignored local inventory and group_vars files. Cloud quickstart remains the default.")

    print_header("Ubuntu k3s Host")
    host_default = local_inventory_defaults.get("ansible_host") or generated_scalar(local_defaults, "k3s_public_ip") or args.host
    alias_default = local_alias or generated_scalar(local_defaults, "lab_name") or args.alias
    user_default = local_inventory_defaults.get("ansible_user") or generated_scalar(local_defaults, "ansible_user") or args.user
    key_default = local_inventory_defaults.get("ansible_ssh_private_key_file") or args.ssh_key
    host = host_default if args.non_interactive else prompt_ip_or_host("Ubuntu host IP or DNS", host_default)
    alias = alias_default if args.non_interactive else prompt_text("Ansible host alias", alias_default)
    user = user_default if args.non_interactive else prompt_text("SSH user", user_default)
    key_path = key_default if args.non_interactive else choose_local_ssh_private_key(key_default, alias)
    password = "" if args.non_interactive else prompt_secret("SSH password, leave empty for key/agent auth")
    target = SshTarget(alias=alias, host=host, user=user, key_path=key_path, password=password)

    can_discover = ssh_available(target)
    facts: dict[str, str] = {}
    gpus: list[Gpu] = []
    if can_discover:
        facts = shell_report(target)
        print_system_report(facts)
        gpus = discover_gpus(target)
        print_gpu_table(gpus)
    else:
        print("Skipping live system and GPU discovery for this run.")

    if not args.lab_cidr:
        args.lab_cidr = generated_scalar(local_defaults, "lab_routed_cidr")
    lab_cidr = choose_lab_cidr(args, facts)
    k3s_cluster_cidr = generated_scalar(local_defaults, "k3s_cluster_cidr", DEFAULT_K3S_CLUSTER_CIDR)
    k3s_service_cidr = generated_scalar(local_defaults, "k3s_service_cidr", DEFAULT_K3S_SERVICE_CIDR)
    k3s_cluster_dns = generated_scalar(local_defaults, "k3s_cluster_dns", DEFAULT_K3S_CLUSTER_DNS)
    validate_no_overlap(
        {
            "lab_routed_cidr": lab_cidr,
            "k3s_cluster_cidr": k3s_cluster_cidr,
            "k3s_service_cidr": k3s_service_cidr,
        }
    )
    existing_access_cidrs = generated_list(local_defaults, "local_access_cidrs")
    existing_appliance_hosts: list[tuple[str, str]] = []
    if fortigate_inventory_defaults.get("ansible_host"):
        existing_appliance_hosts.append((fortigate_inventory_defaults["ansible_host"], fortigate_inventory_defaults.get("ansible_httpapi_port", "443")))
    if fortiweb_inventory_defaults.get("ansible_host"):
        existing_appliance_hosts.append((fortiweb_inventory_defaults["ansible_host"], fortiweb_inventory_defaults.get("ansible_httpapi_port", "443")))
    local_access_cidrs = choose_local_access_cidrs(
        lab_cidr=lab_cidr,
        existing_cidrs=existing_access_cidrs,
        appliance_hosts=existing_appliance_hosts,
        non_interactive=args.non_interactive,
    )

    selected_faig: list[str] = []
    selected_ollama: list[str] = []
    if gpus and not args.non_interactive:
        compatible = [gpu for gpu in gpus if gpu.compatible]
        default_faig_fallback = compatible[0].index if compatible else "cpu-only"
        default_faig = gpu_selection_default(gpus, generated_list(local_defaults, "local_faig_gpu_uuids"), default_faig_fallback)
        selected_faig = select_gpus("GPU(s) dedicated to FortiAIGate", gpus, set(), default_faig)
        unavailable = set(selected_faig)
        remaining_gpus = [gpu for gpu in gpus if gpu.uuid not in unavailable]
        remaining_compatible = [gpu for gpu in gpus if gpu.compatible and gpu.uuid not in unavailable]
        default_ollama_candidates = remaining_compatible or remaining_gpus
        default_ollama_fallback = ",".join(gpu.index for gpu in default_ollama_candidates) if default_ollama_candidates else "cpu-only"
        default_ollama = gpu_selection_default(gpus, generated_list(local_defaults, "local_ollama_gpu_uuids"), default_ollama_fallback)
        selected_ollama = select_gpus("GPU(s) dedicated to Ollama", gpus, unavailable, default_ollama)
    selected_gpu_uuids = list(dict.fromkeys(selected_faig + selected_ollama))
    nvidia_driver_suffix = recommended_nvidia_suffix(selected_gpu_uuids, gpus)
    print_header("NVIDIA Driver")
    print(f"Generated local vars will request nvidia-driver-{nvidia_driver_suffix}.")

    print_header("Local Registry")
    registry_default = generated_scalar(registry_defaults, "local_registry", args.registry)
    repo_prefix_default = generated_scalar(registry_defaults, "repo_prefix", args.repo_prefix)
    local_registry = registry_default if args.non_interactive else prompt_text("Docker registry host:port", registry_default)
    repo_prefix = repo_prefix_default if args.non_interactive else prompt_text("Repository prefix", repo_prefix_default)

    resolved_public_ip = resolve_host_ip(host) or host
    private_ip = facts.get("default_route_ip") or facts.get("ssh_server_ip") or resolved_public_ip
    local_vars_kwargs = {
        "lab_name": alias,
        "ansible_user": user,
        "lab_cidr": lab_cidr,
        "k3s_public_ip": resolved_public_ip,
        "k3s_private_ip": private_ip,
        "k3s_cluster_cidr": k3s_cluster_cidr,
        "k3s_service_cidr": k3s_service_cidr,
        "k3s_cluster_dns": k3s_cluster_dns,
        "faig_gpus": selected_faig,
        "ollama_gpus": selected_ollama,
        "nvidia_driver_suffix": nvidia_driver_suffix,
        "gpu_inventory_captured": bool(gpus),
    }

    write_text(LOCAL_INVENTORY, render_local_inventory(target))
    write_text(
        LOCAL_VARS,
        render_local_vars(
            **local_vars_kwargs,
            local_access_cidrs=local_access_cidrs,
        ),
    )
    write_text(REGISTRY_VARS, render_registry_vars(local_registry, repo_prefix))
    if not LOCAL_SECRETS.exists():
        write_text(LOCAL_SECRETS, "---\n# Local secret overrides may be stored here. This file is ignored by Git.\n")
        LOCAL_SECRETS.chmod(0o600)

    if args.non_interactive:
        print("Non-interactive mode: skipped optional FortiGate/FortiWeb prompts.")
    else:
        appliance_results: list[ApplianceBootstrapResult] = []
        fortigate_result = prompt_fortigate_appliance(
            inventory_defaults=fortigate_inventory_defaults,
            generated_defaults=local_defaults,
            secret_defaults=secret_defaults,
            current_access_cidrs=local_access_cidrs,
            lab_cidr=lab_cidr,
        )
        appliance_results.append(fortigate_result)
        persist_appliance_result(fortigate_result)
        local_access_cidrs = list(dict.fromkeys(local_access_cidrs + fortigate_result.access_cidrs))
        fortiweb_result = prompt_fortiweb_appliance(
            inventory_defaults=fortiweb_inventory_defaults,
            generated_defaults=local_defaults,
            secret_defaults=secret_defaults,
            current_access_cidrs=local_access_cidrs,
            lab_cidr=lab_cidr,
        )
        appliance_results.append(fortiweb_result)
        persist_appliance_result(fortiweb_result)
        local_access_cidrs = list(dict.fromkeys(local_access_cidrs + fortiweb_result.access_cidrs))
        write_text(
            LOCAL_VARS,
            render_local_vars(
                **local_vars_kwargs,
                local_access_cidrs=local_access_cidrs,
            )
            + "\n"
            + render_appliance_local_vars(appliance_results),
        )

    print_header("Next Step")
    print("Run local deployment with:")
    print("  python3 scripts/automated_quickstart.py --local")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(130)
