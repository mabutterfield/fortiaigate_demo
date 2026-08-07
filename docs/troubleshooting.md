# Troubleshooting

Choose the symptom that matches the first failed checkpoint. Avoid rerunning
the entire deployment until the underlying status or prerequisite is corrected.
All commands run from `<repo_root>`.

Select the k3s inventory once for the commands on this page:

```bash
export FAIG_INVENTORY=cloud
# or
export FAIG_INVENTORY=local
```

Appliances use their dedicated inventory aliases instead.

## Quickstart Stops Before Terraform Or Ansible

Symptoms:

- a required command is missing;
- operator configuration is missing;
- a license preflight fails;
- local generated files are absent; or
- quickstart stops at a review prompt.

Actions:

1. Recheck [First-Run Preparation](first-run-preparation.md).
2. For an interactive first run, allow quickstart to import or create operator
   configuration. Standalone profile initialization is optional.
3. For local mode, generate inventory before quickstart:

   ```bash
   python3 scripts/local_setup.py
   ```

4. Confirm the configured license exists under the parent `licenses/`
   directory and is not a placeholder.
5. Review [Deployment Options](deployment-options.md) and explicitly disable an
   unwanted appliance rather than fabricating its prerequisites.

## AWS Login Fails

Confirm the configured profile and caller:

```bash
aws configure list-profiles
aws sso login --profile <profile-name>
aws sts get-caller-identity --profile <profile-name>
```

Use the same profile and region recorded in `terraform/user.tfvars`. Fix the
AWS CLI session before diagnosing Terraform. Do not put static AWS credentials
in repository files.

## Terraform Or AWS Infrastructure Fails

Common causes:

- insufficient EC2 GPU quota or capacity in the selected Availability Zone;
- missing EC2 key pair;
- unaccepted FortiGate/FortiWeb Marketplace terms;
- stale or competing ECR state;
- an invalid or missing BYOL license path;
- overlapping VPC, k3s pod, or k3s service CIDRs; or
- private k3s mode without a working management/data route.

Inspect the owning module from the repository root:

```bash
terraform -chdir=terraform/aws-ecr plan
terraform -chdir=terraform/aws-prep plan
terraform -chdir=terraform/aws-ec2-k3s plan
terraform -chdir=terraform/aws-fortigate plan
terraform -chdir=terraform/aws-fortiweb plan
```

Run only the module relevant to the failure. ECR import and image behavior are
documented in
[Container Repository Management](container-repository-management.md).
Network ownership is documented in [Terraform](terraform.md) and
[VPC Layout](vpc-layout.md).

## EC2 Is Running But SSH Fails

Check the Terraform-generated command:

```bash
terraform -chdir=terraform/aws-ec2-k3s output ssh_command
```

Then confirm:

- the private key matches `ssh_key_name` and `ssh_private_key_file`;
- the trusted source CIDR includes the operator's current public address;
- the instance and system checks are healthy;
- public k3s mode has the prep-owned EIP; and
- private mode has an intentionally configured management route.

Do not start Ansible until SSH works.

## Image Publication Or Pull Fails

Symptoms include Docker disk exhaustion, registry authentication errors,
immutable-tag conflicts, `ImagePullBackOff`, or missing repositories.

Actions:

1. Confirm Docker works without `sudo` on the publisher.
2. Confirm the exact tag exists in ECR or the local registry.
3. For changed content, increment the image tag instead of reusing an immutable
   release tag.
4. Confirm the k3s host can resolve and reach the configured registry.
5. For a plain-HTTP local registry, configure the exact host and port as
   insecure on both Docker and k3s/containerd.

See [Container Repository Management](container-repository-management.md).

## k3s, GPU, Or Container Runtime Is Not Ready

Run the foundation validation:

```bash
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/validate_k3s.yml
```

If NVIDIA package downloads are unusually slow on AWS, see
[Known Issues](known-issues.md) and the
[AWS NVIDIA Package Cache Workaround](aws-nvidia-package-cache-workaround.md).

On the host, inspect:

```bash
nvidia-smi
sudo systemctl status k3s --no-pager
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml get nodes -o wide
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml get pods -A
```

For local mode, rerun `local_setup.py` after `nvidia-smi` works so GPU UUIDs
can be assigned.

## FortiAIGate Remains Not Ready

FortiAIGate deployment is asynchronous. Image pulls, Triton startup, storage,
and readiness probes can take time.

```bash
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/status_fortiaigate.yml
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/validate_faig.yml
```

If status remains `NOT READY`, inspect pods, events, and previous logs in the
`fortiaigate` namespace. Confirm image tags, GPU allocation, license mapping,
storage, and ingress before redeploying.

The FortiAIGate UI is expected under `https://<k3s-host>/ui/`.

## LiteLLM Or Direct Model Calls Fail

Isolate the model provider from the rest of the chain:

```bash
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/test_model_direct.yml
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/status_litellm.yml
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/test_litellm_direct.yml
```

The `cloud` inventory selects Bedrock; `local` selects Ollama. For Bedrock,
confirm region, model access, IAM permission, and credential expiration. For
local, confirm Ollama status, the selected model, GPU capacity, and the
in-cluster endpoint. See [Bedrock](bedrock.md) or [Ollama](ollama.md).

## MCP Or Tool Calls Fail

Separate server health, transport, and model tool selection:

```bash
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/status_mcp.yml
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/test_mcp.yml
```

If Direct MCP works but FortiWeb MCP fails, check FortiWeb status, generated
proxy objects, backend reachability, and the selected MCP path. FortiWeb changes
transport; it does not change the scenario tool profile. See [MCP](mcp.md) and
[FortiWeb](fortiweb.md).

## Chatbot Or Demo Home Is Unavailable

```bash
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/status_chatbots.yml
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/status_demo_home.yml
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/show_demo_outputs.yml
```

Confirm the printed host/port rather than assuming defaults. A chatbot code
change requires image publication and redeployment; scenario metadata or
instruction changes normally require configuration redeployment only.

## HTTPS Fails While HTTP Works

Check whether quickstart actually ran the optional HTTPS gateway playbook and
whether `demo_https_gateway_enabled=true`.

```bash
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/deploy_demo_https_gateway.yml
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/validate_demo_http_paths.yml
```

Self-signed certificates require explicit trust. Operator-provided certificate
and key paths must remain outside Git and must form a matching pair.

## FortiGate Or FortiWeb Is Not Ready

Use the appliance inventory, not the k3s inventory:

```bash
ansible-playbook -i cloud-fortigate ansible/playbooks/status_fortigate.yml
ansible-playbook -i cloud-fortiweb ansible/playbooks/status_fortiweb.yml
```

For existing local appliances, use the matching `local-*` alias. Confirm
Marketplace subscription and license mode for AWS, management reachability,
admin port, credentials, and lockout state. Optional appliance failure does not
invalidate the core deployment unless the appliance was explicitly required.

## Local Commands Load AWS Variables

Use the `local` inventory alias:

```bash
ansible-playbook -i local ansible/playbooks/show_demo_outputs.yml
```

The inventory is authoritative for deployment-target selection, including
localhost-only utility playbooks. Remove a stale `FAIG_DEPLOYMENT_TARGET`
environment override if one was deliberately set for an unusual no-inventory
call.

## Functional Scenario Validation Fails

First confirm LiteLLM, MCP, chatbot, and FortiAIGate status. Then confirm the
scenario is installed and its GUI work order matches the deployed FAIG objects:

```bash
python3 scripts/scenario_profiles.py list-installed
python3 scripts/scenario_profiles.py render-work-order
python3 -m functional_test --scenario-id <scenario-id>
```

A missing or stale GUI flow is not repaired by rerunning the functional test.
Use [Scenario Management](scenarios.md), the generated work order, and
[FortiAIGate GUI Configuration](FortiAIGate-initial-config.MD).

## Escalate With Evidence

When a problem remains, collect:

- deployment lane and exact command;
- first failing checkpoint;
- relevant status/validation summary;
- Terraform module and plan for infrastructure failures;
- Kubernetes pod description, events, and redacted logs; and
- scenario/test ID for functional failures.

Never include licenses, private keys, kubeconfigs, API tokens, Terraform state,
generated passwords, or unredacted secret-bearing output.
