# Operations

This guide owns repeat deployment, status, component reruns, updates,
validation, state portability, and teardown after the first deployment. Use
[Deployment Quickstart](quickstart.md) for a new installation and
[Troubleshooting](troubleshooting.md) when a status or rerun fails.

All commands run from `<repo_root>`. Use `-i cloud` for the AWS k3s host and
`-i local` for the local Ubuntu host. Appliance commands use
`cloud-fortigate`, `cloud-fortiweb`, `local-fortigate`, or `local-fortiweb`.
See [Command And Inventory Reference](reference/command-inventory.md) for the
alias and generated-file contract.

Both Terraform and Ansible are designed to bring the environment to the
configuration currently described by the repository and operator values.
Terraform shows the infrastructure changes it intends to make before approval;
Ansible checks the managed host and changes only what is missing or different.
That makes the guided workflow and component playbooks suitable for repeat
runs: matching resources are left in place and detected drift is reconciled.
Always review a Terraform plan before approval because an intentional
configuration removal can still produce a destroy action.

## Status Sweep

Start with status commands. They are read-only unless a referenced component
tool explicitly states otherwise.

Choose one k3s inventory alias:

```bash
export FAIG_INVENTORY=cloud
# or
export FAIG_INVENTORY=local
```

Then run the core sweep:

```bash
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/validate_k3s.yml
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/status_fortiaigate.yml
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/status_litellm.yml
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/status_mcp.yml
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/status_chatbots.yml
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/status_demo_home.yml
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/show_demo_outputs.yml
```

Run selected optional checks:

```bash
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/status_fortiaigate_syslog_collector.yml
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/status_ollama.yml
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/status_openwebui.yml
```

For appliances, use the matching environment-specific alias:

```bash
ansible-playbook -i cloud-fortigate ansible/playbooks/status_fortigate.yml
ansible-playbook -i cloud-fortiweb ansible/playbooks/status_fortiweb.yml

# Existing local appliances
ansible-playbook -i local-fortigate ansible/playbooks/status_fortigate.yml
ansible-playbook -i local-fortiweb ansible/playbooks/status_fortiweb.yml
```

Do not use a k3s inventory alias for an appliance playbook or vice versa.

## Repeat The Guided Deployment

Use the normal guided command when repository defaults, configuration, or
deployment choices need review:

```bash
# AWS
python3 scripts/automated_quickstart.py

# Local
python3 scripts/automated_quickstart.py --local
```

Common controlled variants:

```bash
# Reuse configured AWS values, auto-approve Terraform, import missing ECR
# state when possible, skip image publication, and minimize prompts.
python3 scripts/automated_quickstart.py --yolo

# Continue an AWS deployment from existing Terraform outputs.
python3 scripts/automated_quickstart.py --skip-terraform

# Stop after AWS Terraform and EC2 readiness.
python3 scripts/automated_quickstart.py --skip-ansible

# Wait for FortiAIGate READY before continuing to applications.
python3 scripts/automated_quickstart.py --faig-status-mode wait

# Local repeat run with preconfigured files.
python3 scripts/automated_quickstart.py --local --yolo
```

Use `--yolo` only after required configuration and images already exist. It is
not a substitute for first-run review and does not broaden permission to
destroy or overwrite unrelated state.

## Component Redeploy And Status

Component playbooks can be run again safely when a deployment was interrupted
or one component changed. They inspect the current state and apply only the
changes needed to reach the configured state. The commands below use the
`FAIG_INVENTORY` value selected in the status sweep.

| Component | Deploy or configure | Status/validation |
|---|---|---|
| k3s/GPU foundation | `ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/bootstrap_gpu_k3s.yml` | `ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/validate_k3s.yml` |
| FortiAIGate | `ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/deploy_fortiaigate.yml` | `status_fortiaigate.yml`, then `validate_faig.yml` when a failing gate is wanted |
| Ollama | `ansible-playbook -i local ansible/playbooks/deploy_ollama.yml` | `status_ollama.yml` |
| LiteLLM | `ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/deploy_litellm.yml` | `status_litellm.yml` or `validate_litellm.yml` |
| MCP | `ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/deploy_mcp.yml` | `status_mcp.yml` or `validate_mcp.yml` |
| Chatbot | `ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/deploy_chatbots.yml` | `status_chatbots.yml` or `validate_chatbots.yml` |
| Demo Home | `ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/deploy_demo_home.yml` | `status_demo_home.yml` or `validate_demo_home.yml` |
| HTTPS gateway | `ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/deploy_demo_https_gateway.yml` | `validate_demo_http_paths.yml` |
| Syslog collector | `ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/deploy_fortiaigate_syslog_collector.yml` | `status_fortiaigate_syslog_collector.yml` or `test_fortiaigate_syslog_collector.yml` |
| Open WebUI | `ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/deploy_openwebui.yml` | `status_openwebui.yml` or `validate_openwebui.yml` |

Commands copied from the table must include the `ansible/playbooks/` prefix.
For example:

```bash
ansible-playbook -i cloud ansible/playbooks/deploy_litellm.yml
ansible-playbook -i cloud ansible/playbooks/status_litellm.yml
```

Optional components may deliberately report disabled or absent. Confirm their
selected state in [Deployment Options](deployment-options.md) before treating a
skip as a fault.

## Appliance Configuration Reruns

FortiGate:

```bash
ansible-playbook -i cloud-fortigate ansible/playbooks/status_fortigate.yml
ansible-playbook -i cloud-fortigate ansible/playbooks/configure_fortigate.yml
ansible-playbook -i cloud-fortigate ansible/playbooks/configure_fortigate_api_accounts.yml
```

FortiWeb:

```bash
ansible-playbook -i cloud-fortiweb ansible/playbooks/status_fortiweb.yml
ansible-playbook -i cloud-fortiweb ansible/playbooks/configure_fortiweb.yml
```

Use the `local-*` equivalent when configuring existing local appliances.
Status must succeed before a configuration rerun. Repeated failed management
logins can trigger appliance lockout; correct credentials and allow the lockout
window to clear before retrying.

## Image Publication And Workload Updates

Container publication is maintained separately from component deployment. Use
[Container Repository Management](container-repository-management.md) as the
source of truth.

Common publisher commands:

```bash
# AWS ECR, configured release inputs
ansible-playbook -i cloud ansible/playbooks/publish_images.yml

# Chatbot application image only
ansible-playbook -i cloud ansible/playbooks/publish_chatbot_images.yml

# Local registry
ansible-playbook -i local ansible/playbooks/publish_images.yml \
  -e registry_type=local \
  -e local_registry=<registry-host>:5000
```

Increment the applicable tag whenever image content changes for a release.
After publishing, redeploy only the affected component and rerun its status
check. Scenario metadata, installed scenario instructions, and rendered
LiteLLM/chatbot configuration do not by themselves require a chatbot image
rebuild.

## Repository Update Workflow

Before moving to a fresh clone or switching to a new repository release:

1. export operator configuration;
2. preserve local generated state only when it must move to another checkout;
3. obtain the updated repository version;
4. review `CHANGELOG.md`, current defaults, and deployment options;
5. import operator/local state into the fresh checkout when applicable;
6. rerun guided quickstart; and
7. explicitly review installed scenario template updates.

Export/import the operator profile:

```bash
python3 scripts/user_profile.py export ../user_profile.tgz
python3 scripts/user_profile.py import ../user_profile.tgz
```

The profile excludes licenses, private keys, certificates, Terraform state,
generated inventories, and generated Ansible variables. Those inputs must be
preserved separately and securely.

For local generated inventory/variables, export is a move operation: it creates
a sensitive archive and removes the generated files from the current checkout.
Use it only when changing checkouts or intentionally clearing local state:

```bash
python3 scripts/local_var_cleanup.py export --dry-run
python3 scripts/local_var_cleanup.py export
python3 scripts/local_var_cleanup.py import
```

It does not uninstall k3s, applications, images, or appliances.

Installed scenarios are editable local state. Inspect them after an update:

```bash
python3 scripts/scenario_profiles.py list-installed
python3 scripts/scenario_profiles.py update <scenario-id>
```

The update command reports local modifications and source changes. Use its
explicit overwrite option only after reviewing or preserving local tuning.

## Functional Validation

After the required FortiAIGate GUI flows exist, validate all installed scenario
metadata and paths:

```bash
python3 -m functional_test
```

For a targeted scenario or action:

```bash
python3 -m functional_test --scenario-id fortistore-injection
python3 -m functional_test --scenario-id hr-tool-dlp --action deny
```

The functional tester validates expected Alert, Deny, and Redact behavior from
scenario metadata and writes run evidence under its configured output root.
See [Functional Test](../functional_test/README.md).

## Direct Component Probes

Use these after the corresponding status is healthy:

```bash
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/test_model_direct.yml
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/test_litellm_direct.yml
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/test_mcp.yml
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/test_fortiaigate_chat.yml
```

The model test uses Bedrock for `cloud` and Ollama for `local`. The local
inventory supplies the deployment target automatically.

## Logs And Kubernetes Inspection

Use the SSH command from Demo Outputs or Terraform:

```bash
terraform -chdir=terraform/aws-ec2-k3s output ssh_command
```

On the k3s host:

```bash
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml get nodes -o wide
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml get pods -A
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml get events -A --sort-by=.lastTimestamp
```

For a failing pod, inspect its description and current/previous logs without
posting secrets:

```bash
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml -n <namespace> describe pod <pod>
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml -n <namespace> logs <pod> --all-containers
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml -n <namespace> logs <pod> --all-containers --previous
```

See [FortiAIGate Syslog Preservation](fortiaigate-syslog-preservation.md) for
collector and S3 export details.

## AWS Teardown

The guided teardown is destructive to AWS lab infrastructure. It preserves ECR
repositories by removing repository resources from Terraform state before
destroying ECR lifecycle/local-output resources.

Review the plan and confirmations:

```bash
python3 scripts/automated_teardown.py
```

The normal order is FortiWeb, FortiGate, EC2/k3s, optional syslog export and AWS
prep, then ECR state protection and cleanup. Terraform skips a module when its
state tracks no resources.

Useful controlled variants:

```bash
# Terraform destroy still prompts only at its own approval points.
python3 scripts/automated_teardown.py --yes

# Fully non-interactive repeat teardown, including syslog export/emptying.
python3 scripts/automated_teardown.py --yolo

# Preserve both appliance deployments.
python3 scripts/automated_teardown.py --skip-appliances

# Keep ECR state/lifecycle handling untouched.
python3 scripts/automated_teardown.py --skip-ecr
```

Use other `--skip-*` flags only when intentionally preserving a dependency and
you understand the resulting Terraform relationships. Do not run individual
module destroys in an arbitrary order.

## Local Lab Lifecycle

There is no repository-owned automated uninstall for a local k3s host. Running
`local_var_cleanup.py export` only moves generated checkout state; it does not
remove the deployed lab. Re-running local quickstart or component playbooks is
the supported update/reconciliation path.

If the local host, k3s cluster, images, or applications must be removed, treat
that as an explicit host-administration task and preserve any required logs,
licenses, configuration, and local generated state first.
