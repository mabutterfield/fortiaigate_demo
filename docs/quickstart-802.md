# FAIG 8.0.2 quickstart

This experimental AWS workflow provisions the existing Terraform foundation,
installs k3s, FAIG, LiteLLM, MCP and the integrated Lab Management/chatbot
services, and optionally initializes FAIG through GUI-observed APIs. Those
application APIs are unsupported and can change between releases. A fresh
Ohio GPU host deployment and teardown were exercised for v1.2.0-rc.1; see the
[release notes](release-notes-1.2.0-rc.1.md) for the tested scope and limitations.

For using the deployed lab, see the [instructor guide](instructor-guide-802.md)
and [student guide](student-guide-802.md).

## Start an interactive deployment

After completing [first-run preparation](first-run-preparation.md), signing in
to AWS and placing the 8.0.2 chart and FAIG license in the workspace, run:

```bash
python3 scripts/automated_quickstart.py
```

The prompts configure your profile and deploy the lab. Quickstart detects your
public IPv4 when possible; verify the suggested address before accepting it.
If an imported profile's trusted CIDRs do not include the detected address,
quickstart warns in both interactive and `--yolo` modes but does not change
them. Review the effective `allowed_ingress_cidr`, including any `prep.tfvars`
override, before deploying. VPNs or proxies can make the detected web address
different from the SSH source address.
LiteLLM credentials are generated per instance. Once the profile is saved,
`--yolo` reuses it and applies infrastructure changes without prompting.
Check that `ansible-playbook --version` and `ansible-galaxy --version` work;
finding a command on PATH does not guarantee its Python interpreter exists.

Quickstart checks the vendor Helm chart on the controller before provisioning:
by default it expects `FAIG/FAIG_helm/8.0.2/fortiaigate/Chart.yaml`. Extract
the chart there, or set `fortiaigate_chart_path` in `ansible/group_vars/user.yml`.
If the chart was missing during an existing deployment, correct the path and
resume with `python3 scripts/automated_quickstart.py --skip-terraform` using
the same workspace and overrides.

For an existing named Terraform workspace with separate prep and host variable
files, for example the Ohio lab:

```bash
cd /path/to/FAIG/fortiaigate_demo_802
export TF_WORKSPACE=ohio-802
export FAIG_TERRAFORM_VARS_DIR=/path/to/FAIG/ohio-802
python3 scripts/automated_quickstart.py --yolo
```

`--terraform-vars-dir` is the equivalent CLI option. The directory must contain
`prep.tfvars` and `host.tfvars`; their region and profile must agree. The
workspace and overrides directory are saved in the storage profile for later
`--yolo` runs. An explicitly supplied environment value that conflicts with
the saved profile stops the run. Review the selected workspace and private
values before using `--yolo`: Terraform applies changes
without prompting. The option does not mean Terraform itself cannot change or
replace an instance. Existing ECR repositories and images are not managed by
the quickstart. Manage repositories through the separate ECR maintainer
workflow; image publishing and repository changes are not quickstart options.
Quickstart discovers the selected account and registry directly from AWS and
checks the required 8.0.2 repositories and image tags before applying prep.
ECR Terraform state is not required on the deployment machine.

Experimental FAIG initialization defaults on. Use
`--no-experimental-faig-init` or set `quickstart_experimental_faig_init: false`
in ignored `ansible/group_vars/user.yml` to leave setup and licensing manual.
The instructor page cannot authenticate until the administrator completes that
manual setup. See [manual FAIG setup](lab-management.md#if-you-set-up-faig-yourself).
The initializer checks the setup API, uses the instance's canonical private
bootstrap credentials, rotates a matching license, checks Active and scanning
status, creates or verifies the direct LiteLLM `pass-model` provider, then
sends a governed request and checks a Traffic Log entry. Its journal and
smoke key belong to the instance; uncertain writes stop rather than being
repeated blindly.

### State and generated secrets

On first interactive setup, quickstart asks whether to store Terraform state
outside the repository and asks where to put generated secrets. Suggested
locations are `FAIG/.state` and `FAIG/.secrets` (or a custom location); they
must be separate and outside Git. The selection is stored in an owner-only
`FAIG/.faig-storage-settings.json`, including the selected Terraform workspace
and overrides directory, for later `--yolo` runs. External state is opt-in, but real-environment migration is unvalidated and deferred to v1.2.1; use local state for this release candidate.
Use `--storage-profile /absolute/path/outside/git.json` for a separate
environment profile; a verified existing external state root can be shared
without repeating migration. Pass the same option to teardown.
Quickstart inventories all worktrees, backs up and migrates each
module's default and named workspaces, then verifies their state identities
before archiving the originals. An interrupted migration stops for inspection; see the [recovery runbook](state-migration-recovery.md).
Never run independent Terraform operations against these states concurrently.

**Terraform host state, its backups, and saved plans contain generated FAIG
and LiteLLM credentials in plaintext.** State files and private directories
are restricted to the owner; do not commit or share them. Sensitive markings
hide ordinary output but not named outputs, `-raw`, `-json`, state or plans.
Pre-migration backups remain private until deliberately removed.

For v1.2.0, run host Terraform only through quickstart or teardown from the
checkout containing `terraform/aws-ec2-k3s/99-local.auto.tfvars`. Quickstart
records the generated-secret settings there and refuses conflicting host
overrides. These settings do not automatically follow a different worktree.
Do not supply conflicting `-var` or `-var-file` arguments in manual runs.

For each new EC2 instance, Terraform creates one owner-only
`bootstrap-secrets.json` under `<secrets-root>/<workspace>/<instance-id>/`.
It contains the generated admin and LiteLLM credentials. Same-instance reruns
reuse them. Static password files have not yet been live-tested in the fresh 8.0.2 deployment. Set `faig_admin_static_password_file` in ignored host tfvars to an
absolute, owner-only, one-line instructor file outside Git to use a static
admin password instead; Terraform records only the path. The static file and
licenses are never included in instance cleanup. An old `FAIG_ENV_DIR` that
does not name the selected instance directory stops the run; unset it when
moving from the old environment layout. Set `faig_admin_email` in ignored
`user.yml` to change the administrator address.

By default FAIG license filenames must fully match `FAIG.*\.lic` in the
configured `license_source_dir`. Set `quickstart_faig_license_regex` in ignored
`user.yml` to choose another pattern. The shared `.last-used` marker is updated
only after FAIG confirms an Active license. A missing marker target or an
uncertain upload requires manual reconciliation. FortiGate and FortiWeb are
optional and excluded unless explicitly enabled in their local overrides or CLI
flags; their existing license workflows are separate.

For a FAIG license with a different filename prefix, verify that it is a
FortiAIGate license, then set a matching regular expression, for example
`quickstart_faig_license_regex: '^CUSTOM.*\.lic$'`. The older
`fortiaigate_license_files` list does not select the 8.0.2 automatic license:
the initializer rotates files matching this regex. Alternatively, use
`--no-experimental-faig-init` and upload the license manually.

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
python3 scripts/teardown_802.py
```

Teardown removes the EC2 lab environment as one unit: tracked FortiWeb and
FortiGate appliances first, then the EC2/VPC stack, then everything in
`aws-prep` (lab IAM, Elastic IPs and the lab S3 buckets: FortiWeb cloud-init,
scenario documents and FortiAIGate syslog). Buckets are emptied, including
earlier object versions, before Terraform deletes them. ECR repositories and
the NVIDIA driver cache are managed outside this lifecycle and are not touched.

If the FortiAIGate syslog bucket has objects, teardown asks where to export
them first. With `--yes` or `--yolo`, choose up front: `--export-syslog DIR`
downloads the current objects to a directory outside the repository, and
`--discard-syslog` deletes them; without either, teardown stops before
destroying anything.

`--keep-eip` preserves the lab EIPs and removes the rest of `aws-prep`;
`--skip-ec2` keeps the whole lab environment and implies `--keep-eip`. `--yolo`
skips confirmations and approves the Terraform actions; review the workspace
and profile first.

Each destroy plan is saved and checked before it is applied: it may delete
only lab environment resources. The `aws-prep` plan is also checked before
anything is destroyed, so a refused plan stops the run with nothing removed and
names the resource and action. GPU termination may take several minutes.
Generated instance secrets are cleaned after AWS confirms termination, before
the `aws-prep` step.

**Known limitations (v1.2.0):**

- Teardown removes only appliances present in the selected workspace's state.
  It stops if other VPC network interfaces remain. AWS or Terraform may still
  reject deletion due to other dependencies.
- The EC2/VPC stack and the lab IAM and Elastic IP removal were validated
  live. Appliance teardown, bucket emptying and syslog export have local test
  coverage but have not yet been validated in a live deployment.
- After an Elastic IP is released, the next deployment gets a new address.
  Remove the old host key before connecting (`ssh-keygen -R <old-ip>`).

For the default AWS security group, FAIG's port 80 and the lab chatbot's
legacy HTTP port redirect to their HTTPS endpoints. Other generated legacy
HTTP NodePorts are not exposed by default; use their HTTPS gateway endpoints.
Explicit additional security-group ports are operator-controlled and may expose
unencrypted services. A redirect cannot protect data already sent over HTTP.
