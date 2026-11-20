# FAIG 8.0.2 quickstart

This experimental AWS workflow provisions the existing Terraform foundation,
installs k3s, FAIG, LiteLLM, MCP and the integrated Lab Management/chatbot
services, and optionally initializes FAIG through GUI-observed APIs. Those
application APIs are unsupported and can change between releases. The full
fresh-host workflow must be validated before it is treated as release-ready.

For an existing named Terraform workspace with separate prep and host variable
files, for example the Ohio lab:

```bash
cd /path/to/FAIG/fortiaigate_demo_802
export TF_WORKSPACE=ohio-802
export FAIG_TERRAFORM_VARS_DIR=/path/to/FAIG/ohio-802
export FAIG_ENV_DIR=/path/to/FAIG/.secrets/ohio-lab
python3 scripts/automated_quickstart.py --yolo
```

`--terraform-vars-dir` is the equivalent CLI option. The directory must contain
`prep.tfvars` and `host.tfvars`; their region and profile must agree. An
explicit `TF_WORKSPACE` is required with these overrides. Review the selected
workspace and private values before using `--yolo`: Terraform applies changes
without prompting. The option does not mean Terraform itself cannot change or
replace an instance. Existing ECR repositories and images are not managed by
default; `--manage-ecr` explicitly opts into the separate ECR workflow.
When preserving ECR, quickstart rebuilds the local Ansible registry settings
from the selected workspace's existing `terraform/aws-ecr` outputs and checks
the account and region. That ECR state must already exist in the checkout;
otherwise initialize or import it through the separate ECR workflow first.

Experimental FAIG initialization defaults on. Use
`--no-experimental-faig-init` or set `quickstart_experimental_faig_init: false`
in ignored `ansible/group_vars/user.yml` to leave setup and licensing manual.
The instructor page cannot authenticate until the administrator completes that
manual setup. See [manual FAIG setup](lab-management.md#if-you-set-up-faig-yourself).
The initializer checks the setup API, uses a private administrator setup file,
rotates a matching license, reads back Active and scanning-enabled status,
creates or verifies the direct LiteLLM `pass-model` provider, then sends a
governed request and checks a matched Traffic Log entry. It keeps an owner-only
journal and smoke key per EC2 instance in `FAIG_ENV_DIR`; uncertain writes stop
rather than being repeated blindly. A previous instance's private files are not
deleted. If existing credentials or the provider differ, reconcile them rather
than overwriting them automatically.

The directory in `FAIG_ENV_DIR` must be owner-only. If the admin setup/login
files are absent, quickstart generates them there, using `admin@fortiai.lab` by
default. To choose a password, set `faig_admin_password_file` in ignored
`user.yml` to an owner-only, one-line file. Do not put passwords in CLI flags or
tracked files. Set `faig_admin_email` to change the address.

By default FAIG license filenames must fully match `FAIG.*\.lic` in the
configured `license_source_dir`. Set `quickstart_faig_license_regex` in ignored
`user.yml` to choose another pattern. The shared `.last-used` marker is updated
only after FAIG confirms an Active license. A missing marker target or an
uncertain upload requires manual reconciliation. FortiGate and FortiWeb are
optional and excluded unless explicitly enabled in their local overrides or CLI
flags; their existing license workflows are separate.

Quickstart prints the FAIG and instructor URLs, administrator email and private
credential directory, not passwords. The FAIG re-entry provider is not yet
implemented in this workflow. The current preflight stops before infrastructure
changes if the reviewed Lab Management playbooks have not been integrated.

## Tear down the disposable lab

Select the same workspace and overrides used to deploy, then run the separate
teardown command:

```bash
export TF_WORKSPACE=ohio-802
export FAIG_TERRAFORM_VARS_DIR=/path/to/FAIG/ohio-802
python3 scripts/automated_teardown.py
```

By default it destroys the EC2/VPC stack and releases its lab Elastic IP.
`--keep-eip` preserves the IP for reuse; `--skip-ec2` keeps the entire lab
and implies `--keep-eip`. ECR, S3, shared IAM/prep resources, and optional
appliances are untouched. `--yolo` skips confirmations and approves the
Terraform actions; review the workspace and effective profile first. EIP
release uses a saved plan that must contain only that IP's deletion. An EC2
failure stops before the IP is released. GPU termination may take several
minutes; the VPC remains until AWS releases its dependencies.

**Known limitations (v1.0):**

- **Optional FortiGate/FortiWeb appliances are not handled.** They are
  deployed into the lab VPC's subnets, so the VPC cannot be destroyed while
  they exist. With the FortiGate private default route configured
  (`k3s_private_default_route_network_interface_id`), the host plan also
  contains an `aws_route` deletion, which the plan check does not allow, so
  teardown stops before changing anything. Tear the appliances down first
  with their own Terraform folders (`terraform/aws-fortigate`,
  `terraform/aws-fortiweb`), then run this teardown. The default lab has no
  appliances and is not affected.
- **Not yet run end to end** on a disposable deployment; the plan checks and
  ordering are covered by unit tests.
- After an Elastic IP is released, the next deployment gets a new address.
  Remove the old host key before connecting (`ssh-keygen -R <old-ip>`).
