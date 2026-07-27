#!/usr/bin/env python3
"""Generate local FortiAIGate deployment inventory and vars."""

from __future__ import annotations

import argparse
import csv
import getpass
import ipaddress
import socket
import subprocess
import sys
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
DEFAULT_REGISTRY = "jarvis:5000"
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


def prompt_ip_or_host(prompt: str, default: str) -> str:
    while True:
        value = prompt_text(prompt, default).strip()
        if value:
            return value
        print("Enter an IP address or DNS name.")


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


def render_local_inventory(target: SshTarget) -> str:
    parts = [
        "[fortiaigate]",
        f"{target.alias} ansible_host={target.host} ansible_user={target.user}",
        "",
        "[fortiaigate:vars]",
        "ansible_python_interpreter=/usr/bin/python3",
    ]
    if target.key_path:
        parts.append(f"ansible_ssh_private_key_file={target.key_path}")
    if target.password:
        parts.append(f"ansible_password={target.password}")
        parts.append("ansible_become_password={{ ansible_password }}")
    return "\n".join(parts) + "\n"


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
local_access_cidrs:
  - {yaml_quote(lab_cidr)}
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
  - llama3.1:8b
  - gpt-oss:20b
ollama_model: "{{{{ ollama_models[0] }}}}"
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
litellm_passthrough_model_alias: pass-ollama
litellm_faig_backend_downstream_model: "{{{{ litellm_passthrough_model_alias }}}}"
"""


def prompt_appliance(appliance: str, output_path: Path) -> None:
    print_header(f"{appliance} Local Appliance")
    if not prompt_yes_no(f"Configure an existing local {appliance} now?", False):
        print(f"{appliance}: do not install/configure selected.")
        if output_path.exists():
            print(f"Leaving existing ignored inventory in place: {output_path.relative_to(REPO_ROOT)}")
        return

    host = prompt_ip_or_host(f"{appliance} management/API IP or DNS", "")
    user = prompt_text(f"{appliance} admin user", "admin")
    password = prompt_secret(f"{appliance} admin password, leave empty to omit")
    port = prompt_text(f"{appliance} HTTPS/API port", "443")
    key = appliance.lower()
    network_os = "fortinet.fortios.fortios" if key == "fortigate" else "fortinet.fortiweb.fwebos"
    host_alias = f"local-{key}"
    content = f"""[{key}]
{host_alias} ansible_host={host} ansible_user={user} ansible_httpapi_port={port}

[{key}:vars]
ansible_connection=httpapi
ansible_network_os={network_os}
ansible_httpapi_use_ssl=true
ansible_httpapi_validate_certs=false
{key}_public_ip={host}
{key}_public_private_ip={host}
{key}_internal_ip={host}
{key}_vdom=root
"""
    if password:
        content += f"ansible_password={password}\n"
    write_text(output_path, content)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate local FortiAIGate deployment inventory and vars.")
    parser.add_argument("--non-interactive", action="store_true", help="Use defaults where possible and do not prompt for optional appliances.")
    parser.add_argument("--host", default="jarvis", help="Ubuntu host IP or DNS name. Default: jarvis.")
    parser.add_argument("--alias", default="jarvis", help="Ansible host alias. Default: jarvis.")
    parser.add_argument("--user", default="ubuntu", help="Ubuntu SSH user. Default: ubuntu.")
    parser.add_argument("--ssh-key", default="", help="SSH private key path. Empty uses ssh-agent/default SSH config.")
    parser.add_argument("--lab-cidr", default="", help="Local routed CIDR, for example 192.168.50.0/24.")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY, help=f"Local Docker registry. Default: {DEFAULT_REGISTRY}.")
    parser.add_argument("--repo-prefix", default="fortiaigate", help="Image repository prefix. Default: fortiaigate.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("FortiAIGate local setup")
    print(f"Repo root: {REPO_ROOT}")
    print("This writes ignored local inventory and group_vars files. Cloud quickstart remains the default.")

    print_header("Ubuntu k3s Host")
    host = args.host if args.non_interactive else prompt_ip_or_host("Ubuntu host IP or DNS", args.host)
    alias = args.alias if args.non_interactive else prompt_text("Ansible host alias", args.alias)
    user = args.user if args.non_interactive else prompt_text("SSH user", args.user)
    key_path = args.ssh_key if args.non_interactive else choose_local_ssh_private_key(args.ssh_key, alias)
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

    lab_cidr = choose_lab_cidr(args, facts)
    k3s_cluster_cidr = DEFAULT_K3S_CLUSTER_CIDR
    k3s_service_cidr = DEFAULT_K3S_SERVICE_CIDR
    k3s_cluster_dns = DEFAULT_K3S_CLUSTER_DNS
    validate_no_overlap(
        {
            "lab_routed_cidr": lab_cidr,
            "k3s_cluster_cidr": k3s_cluster_cidr,
            "k3s_service_cidr": k3s_service_cidr,
        }
    )

    selected_faig: list[str] = []
    selected_ollama: list[str] = []
    if gpus and not args.non_interactive:
        compatible = [gpu for gpu in gpus if gpu.compatible]
        default_faig = compatible[0].index if compatible else "cpu-only"
        selected_faig = select_gpus("GPU(s) dedicated to FortiAIGate", gpus, set(), default_faig)
        unavailable = set(selected_faig)
        remaining_gpus = [gpu for gpu in gpus if gpu.uuid not in unavailable]
        remaining_compatible = [gpu for gpu in gpus if gpu.compatible and gpu.uuid not in unavailable]
        default_ollama_candidates = remaining_compatible or remaining_gpus
        default_ollama = ",".join(gpu.index for gpu in default_ollama_candidates) if default_ollama_candidates else "cpu-only"
        selected_ollama = select_gpus("GPU(s) dedicated to Ollama", gpus, unavailable, default_ollama)
    selected_gpu_uuids = list(dict.fromkeys(selected_faig + selected_ollama))
    nvidia_driver_suffix = recommended_nvidia_suffix(selected_gpu_uuids, gpus)
    print_header("NVIDIA Driver")
    print(f"Generated local vars will request nvidia-driver-{nvidia_driver_suffix}.")

    print_header("Local Registry")
    local_registry = args.registry if args.non_interactive else prompt_text("Docker registry host:port", args.registry)
    repo_prefix = args.repo_prefix if args.non_interactive else prompt_text("Repository prefix", args.repo_prefix)

    write_text(LOCAL_INVENTORY, render_local_inventory(target))
    resolved_public_ip = resolve_host_ip(host) or host
    private_ip = facts.get("default_route_ip") or facts.get("ssh_server_ip") or resolved_public_ip
    write_text(
        LOCAL_VARS,
        render_local_vars(
            lab_name=alias,
            ansible_user=user,
            lab_cidr=lab_cidr,
            k3s_public_ip=resolved_public_ip,
            k3s_private_ip=private_ip,
            k3s_cluster_cidr=k3s_cluster_cidr,
            k3s_service_cidr=k3s_service_cidr,
            k3s_cluster_dns=k3s_cluster_dns,
            faig_gpus=selected_faig,
            ollama_gpus=selected_ollama,
            nvidia_driver_suffix=nvidia_driver_suffix,
            gpu_inventory_captured=bool(gpus),
        ),
    )
    write_text(REGISTRY_VARS, render_registry_vars(local_registry, repo_prefix))
    if not LOCAL_SECRETS.exists():
        write_text(LOCAL_SECRETS, "---\n# Local secret overrides may be stored here. This file is ignored by Git.\n")

    if args.non_interactive:
        print("Non-interactive mode: skipped optional FortiGate/FortiWeb prompts.")
    else:
        prompt_appliance("FortiGate", FORTIGATE_LOCAL_INVENTORY)
        prompt_appliance("FortiWeb", FORTIWEB_LOCAL_INVENTORY)

    print_header("Next Step")
    print("Run local deployment with:")
    print("  python3 scripts/automated_quickstart.py --local")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(130)
