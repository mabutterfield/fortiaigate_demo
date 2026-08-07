# Deployment Quickstart

This is the single supported first-run deployment guide for the repository.
Use the guided script for both AWS and local Ubuntu deployments. Individual
Terraform and Ansible commands are operations and recovery tools, not a second
installation path.

Before continuing, complete these two required guides:

1. [First-Run Preparation](first-run-preparation.md)
2. [Deployment Options](deployment-options.md)

All commands run from `<repo_root>`, the `fortiaigate_demo/` directory.

You do not need to run the profile tool before quickstart. If the required
operator-owned files do not exist, quickstart launches profile initialization
or import before it starts the deployment. On later runs, existing values are
shown as the defaults so they can be accepted or changed.

Running `python3 scripts/user_profile.py init` separately is useful only when
you want to configure and review those values before beginning the longer
Terraform and Ansible workflow.

## Readiness Check

Confirm the following before starting:

- [ ] vendor Helm chart, image archives, and FortiAIGate license are in the
      parent workspace locations documented in First-Run Preparation;
- [ ] the control workstation has the commands required for the selected lane;
- [ ] one deployment lane—AWS or local Ubuntu—has been prepared;
- [ ] FortiGate and FortiWeb will use valid prerequisites or have been
      explicitly disabled;
- [ ] Docker can reach the selected registry if images must be published;
- [ ] operator configuration is ready, or quickstart will create or import it;
      and
- [ ] `scripts/local_setup.py` has generated inventory and variables when using
      the local lane.

Quickstart checks required commands, configuration files, licenses, and
generated local files before deployment. It does not replace cloud quota,
Marketplace subscription, network reachability, or registry-capacity checks.

## Choose Appliance Intent

FortiGate and FortiWeb are desired by default but remain optional to the core
k3s/FortiAIGate deployment:

- no appliance flags: try both and safely skip one whose prerequisites are
  absent;
- `--no-fortigate` or `--no-fortiweb`: explicitly disable one;
- `--no-appliances`: explicitly disable both;
- `--include-fortigate`, `--include-fortiweb`, or `--include-appliances`:
  require the selected appliance and stop if its prerequisites are missing.

FortiWeb is the preferred MCP transport when installed and desired. Disabling
or safely skipping FortiWeb selects Direct MCP as the fallback. FortiGate is
not required for the supported scenario paths.

For the smallest first deployment:

```bash
python3 scripts/automated_quickstart.py --no-appliances
```

Use that command only for the AWS lane. The equivalent local command includes
`--local`.

## AWS Lane

Start the guided AWS deployment:

```bash
python3 scripts/automated_quickstart.py
```

Quickstart runs the operator-profile step before deployment. Missing files
trigger initialization or import; existing values pre-populate the prompts.
It then guides the following sequence:

1. verify Terraform, AWS CLI, Ansible, and the repository root;
2. verify the AWS session and shared profile values;
3. record desired or disabled appliance intent;
4. check FortiAIGate and selected appliance licenses;
5. create/import ECR repositories and apply AWS prep, EC2/k3s, and selected
   appliance Terraform modules;
6. wait for the k3s EC2 instance and show appliance EC2 status snapshots;
7. optionally publish missing or changed images;
8. bootstrap NVIDIA, container runtime, and k3s;
9. deploy FortiAIGate and report its current readiness;
10. configure selected appliances after their APIs become ready;
11. deploy and check the application layer; and
12. print consolidated access URLs and a final FortiAIGate status.

Terraform approval remains interactive unless `--auto-approve` is supplied.
The script also pauses before Terraform and Ansible so operator configuration
can be reviewed.

### AWS Checkpoints

| Checkpoint | Expected evidence | If it fails |
|---|---|---|
| Profile and license preflight | Required files are found; selected licenses are accepted | Stop and correct the named operator file or license path |
| ECR | Repositories are created or imported; generated registry values exist | Review [Container Repository Management](container-repository-management.md) |
| Terraform foundation | `ansible/inventory/aws.generated.ini` and generated group vars are listed | Use [Troubleshooting](troubleshooting.md#terraform-or-aws-infrastructure-fails) |
| EC2 readiness | `k3s EC2 instance status is READY` | Fix quota, capacity, networking, SSH key, or instance health before Ansible |
| k3s bootstrap | Kubernetes and GPU foundation checks complete | Use [Troubleshooting](troubleshooting.md#k3s-gpu-or-container-runtime-is-not-ready) |
| FortiAIGate | Status reports `READY`, or an asynchronous startup state that becomes ready on recheck | Use [Troubleshooting](troubleshooting.md#fortiaigate-remains-not-ready) |
| Application layer | Status runs for enabled components finish without a deployment failure | Rerun the component from [Operations](operations.md#component-redeploy-and-status) |
| Completion | Consolidated URLs print and the script reports completion | Run the status sweep in [Operations](operations.md#status-sweep) |

## Local Ubuntu Lane

Local deployment uses an existing Ubuntu 24.04 GPU host and does not run
Terraform. Generate its inventory and variables first:

```bash
python3 scripts/local_setup.py
```

Then run local quickstart:

```bash
python3 scripts/automated_quickstart.py --local
```

Local quickstart:

1. verifies Ansible and the generated local files;
2. offers to import or create operator configuration without AWS onboarding;
3. uses the configured local/LAN registry;
4. discovers optional existing FortiGate/FortiWeb inventories;
5. checks the FortiAIGate license and local credentials;
6. optionally publishes required images;
7. bootstraps NVIDIA, container runtime, and k3s on the selected host;
8. deploys Ollama as the local model service;
9. deploys the same FortiAIGate, LiteLLM, MCP, chatbot, Demo Home, syslog, and
   selected optional application components; and
10. prints consolidated local access URLs.

If NVIDIA drivers were not usable during the first `local_setup.py` run,
quickstart can complete the GPU/k3s bootstrap and then stop because no
FortiAIGate GPU UUID is assigned. Rerun `local_setup.py`, select the GPUs, and
rerun local quickstart.

### Local Checkpoints

| Checkpoint | Expected evidence | If it fails |
|---|---|---|
| Local setup | `local`, `local.generated.yml`, and `registry.generated.yml` targets exist | Rerun `python3 scripts/local_setup.py` |
| SSH | The configured Ubuntu host is reachable with the generated inventory | Correct the SSH user, key, host, or privilege path in local setup |
| GPU assignment | FortiAIGate GPU UUIDs are present after bootstrap | Rerun local setup after `nvidia-smi` works |
| Registry | Workstation and k3s host can reach the exact registry host and port | Fix DNS, TLS/insecure-registry, authentication, or firewall settings |
| Ollama | `status_ollama.yml` reports the configured local model service | Use [Ollama](ollama.md) and the operations status commands |
| Completion | Consolidated local URLs print and final status checks run | Use the local status sweep in Operations |

## Image Publishing Decision

Image publication is currently integrated into quickstart. It is normally
needed only for the initial deployment, unless a required tag is missing or
image content has changed.

At the image prompt, choose:

- `none` when all required tags already exist;
- `chatbot` after chatbot application or dependency changes;
- `fortiaigate` when vendor image tags are missing or a new vendor build is
  being published; or
- `all` only when both image families need publication.

FortiAIGate publishing can require substantial time and Docker disk space.
Changed release image content requires a new tag. See
[Container Repository Management](container-repository-management.md) for the
authoritative build, tag, publish, verification, cleanup, and rollback rules.

## Optional Components During Quickstart

Quickstart records or applies selected optional behavior without making it the
critical path:

- Open WebUI is skipped when `openwebui_enabled=false`; no supported provider
  or scenario configuration is supplied for it.
- The HTTPS gateway is enabled in repository defaults, but interactive
  quickstart asks whether to run its deployment playbook.
- The syslog collector is part of the normal application sequence; durable S3
  preservation remains optional.
- FortiWeb HTTP-path validation runs only when FortiWeb is selected.

Use [Deployment Options](deployment-options.md) and [Operations](operations.md)
for component-specific controls and reruns.

## Expected Access URLs

Quickstart's `Demo Outputs` section is authoritative because ports and host
addresses are configurable. Default shapes are:

| Service | Default URL shape | Availability |
|---|---|---|
| FortiAIGate Admin | `https://<k3s-host>/ui/` | Core deployment |
| Chat Front-End | `http://<k3s-host>:30081` | Core deployment |
| Demo Home | `http://<k3s-host>:30082` | Core deployment |
| LiteLLM Admin | `http://<k3s-host>:30083/ui/` | Core deployment |
| MCP tools | `http://<k3s-host>:30084/tools` | Core deployment |
| Open WebUI | `http://<k3s-host>:30080` | Only when enabled/configured |
| Ollama API | `http://<local-host>:30085/v1` | Local lane only; trusted lab |
| HTTPS services | `https://<k3s-host>:30443` through `:30447` | Only when gateway deployed |

Self-signed HTTPS endpoints require explicit local trust or a deliberate
test-only certificate bypass. Never disable certificate validation as a
general workstation or production setting.

## Next Actions

After quickstart completes:

1. save the printed URLs without copying credentials into tickets or logs;
2. complete [FortiAIGate Initial Configuration](FortiAIGate-initial-config.MD)
   to create and validate the minimal passthrough path;
3. install or inspect scenarios through [Scenario Management](scenario-management.md);
4. create the scenario GUI objects with
   [Scenario GUI Configuration](fortiaigate-gui-config.md); and
5. run operator-facing scenario validation:

   ```bash
   python3 -m functional_test validate
   ```

Functional validation assumes the corresponding FortiAIGate GUI flows exist.

For repeat runs, component updates, status commands, recovery, and teardown,
continue with [Operations](operations.md). For a failed first run, start with
[Troubleshooting](troubleshooting.md).
