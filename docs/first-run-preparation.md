# First-Run Preparation

Complete this preparation before running the
[8.0.2 quickstart](quickstart-802.md), which owns the deployment itself. This
release deploys to AWS only; the 8.0.1 local Ubuntu lane is preserved on
branch `archive/8.0.1`.

All commands run from `<repo_root>`, the `fortiaigate_demo/` directory that
contains `README.md`, `terraform/`, `ansible/`, and `scripts/`.

## 1. Place The Repository And Private Inputs

The default path variables expect this parent workspace:

```text
FAIG/
├── fortiaigate_demo/              <repo_root>
├── FAIG_helm/
│   └── <8.x.y>/
│       └── fortiaigate/           extracted vendor Helm chart
├── images/
│   └── <8.x.y>/                   vendor Docker image archives
└── licenses/
    ├── <fortiaigate-license>.lic  FortiAIGate license
    ├── <fortigate-license>.lic    optional FortiGate BYOL license
    └── <fortiweb-license>.lic     optional FortiWeb BYOL license
```

Use the exact three-part vendor release directory, such as `8.0.0` or `8.0.1`,
for both the chart and image inputs. Override `faig_workspace_root`, chart,
image, or license paths in operator-owned local configuration if the workspace
differs.

Never put licenses, tokens, private keys, certificates, credentials, image
archives, or extracted vendor charts in Git.

## 2. Prepare The Control Workstation

macOS and Linux are tested control platforms. Use WSL2 Ubuntu for Windows (not tested).

AWS deployment requires:

- Python 3;
- Terraform;
- AWS CLI v2;
- Ansible, `ansible-playbook`, and `ansible-galaxy`;
- Docker available to the current user without `sudo` when publishing images;
- SSH and an existing private key corresponding to the selected EC2 key pair;
- enough Docker disk capacity for the vendor archives, loaded layers, target
  tags, and comparison pulls (allow roughly two to three times the archive
  size).

Check the tools:

```bash
python3 --version
ansible-playbook --version
ansible-galaxy --version
ssh -V

terraform version
aws --version

# only when publishing images
docker version
```

The quickstart performs its own required-command check before changing the
environment.

## 3. Prepare One Deployment Target

### 3A. AWS

Before the AWS first run:

1. Configure an AWS CLI profile, preferably IAM Identity Center/SSO, and set a
   default region.
2. Log in and confirm the caller identity.
3. Create or identify an EC2 key pair in that region and keep its matching
   private key outside the repository.
4. Confirm the account has EC2 GPU On-Demand quota and capacity for the chosen
   instance type.
5. Confirm the selected Bedrock models are available to the account in the
   chosen region and that the relevant inference quota is sufficient.
6. If deploying FortiGate or FortiWeb, accept the selected AWS Marketplace
   terms before Terraform creates the instances.
7. Identify the trusted public source CIDRs that may reach SSH, management,
   and demo ports. Prefer `/32` entries for individual operator addresses.

```bash
aws configure list-profiles
aws sso login --profile <profile-name>
aws sts get-caller-identity --profile <profile-name>
aws ec2 describe-key-pairs \
  --profile <profile-name> \
  --region <aws-region>
aws bedrock list-foundation-models \
  --profile <profile-name> \
  --region <aws-region>
```

Model listing does not by itself guarantee invocation permission or capacity.
Use the AWS console or account-specific quota process to resolve access and
quota issues before the deployment window.

## 4. Optionally Pre-Stage Operator Configuration

Manual profile initialization is not required for a normal interactive first
run. If `terraform/user.tfvars` or `ansible/group_vars/user.yml` is missing,
automated quickstart offers to import an existing profile, create and configure
the files, or exit.

Use the standalone profile tool only when you want to prepare the files before
starting quickstart:

```bash
# AWS pre-staging
python3 scripts/user_profile.py init

python3 scripts/user_profile.py check
```

These are operator-owned local configuration files excluded from version
control by `.gitignore`:

```text
terraform/user.tfvars
terraform/aws-prep/99-local.auto.tfvars
terraform/aws-ec2-k3s/99-local.auto.tfvars
terraform/aws-fortigate/99-local.auto.tfvars
terraform/aws-fortiweb/99-local.auto.tfvars
ansible/group_vars/user.yml
```

`terraform/user.tfvars` supplies the AWS profile, region, name prefix, SSH key,
trusted CIDRs, and tags to every Terraform module through tracked
`50-user.auto.tfvars` symlinks. `ansible/group_vars/user.yml` contains only
operator overrides layered after repo and generated defaults.

For AWS initialization, the profile tool also asks for the k3s GPU instance
size, durable syslog preservation, and whether to deploy FortiGate and
FortiWeb. Each enabled appliance then requires either a selected BYOL file or
a FortiFlex token. The choices are written to the module-local files above.
Enter accepts `g4dn.4xlarge`; choose `g6.4xlarge` or `g6.8xlarge` for a
supported NVIDIA L4 validation target, or `g5.8xlarge` for an A10G validation
target. Verify EC2 quota and Availability Zone capacity before selecting any
G5/G6 size. Existing explicit selections are reused as prompt defaults.
Changing the type of an existing instance can stop/restart it, and its
instance-store-backed k3s data is ephemeral.

Run `python3 scripts/user_profile.py init` again to add or change these AWS
appliance choices in an existing profile. Do not copy or edit the tracked
`00-system.auto.tfvars` files.

Profile archives contain the operator tfvars/YAML files and existing
module-local overrides. Treat the archive as sensitive.

## 5. Place Licenses And Optional Tokens

The normal baseline uses BYOL license files from the parent `licenses/`
directory:

| Product | Expected configuration | Default lookup |
|---|---|---|
| FortiAIGate | `fortiaigate_license_files`; override in local `ansible/group_vars/user.yml` only when needed | `FAIG/licenses/<configured-name>` |
| FortiGate | `fortigate_license_file_name` in local `terraform/aws-fortigate/99-local.auto.tfvars` | `FAIG/licenses/<configured-name>` |
| FortiWeb | `fortiweb_license_file_name` in local `terraform/aws-fortiweb/99-local.auto.tfvars` | `FAIG/licenses/<configured-name>` |

The tracked FortiAIGate default name is `License1.lic`; it can be replaced by
the configured file name. The tracked all-zero FortiGate and FortiWeb names are
placeholders, not usable licenses. Interactive quickstart asks for a real file
when a desired appliance still has a placeholder or missing path.

Guided profile initialization can store a FortiFlex token in the appropriate
local `99-local.auto.tfvars` file. FortiFlex lifecycle integration remains out
of scope: tokens may be recorded in Terraform state and must be replaced before
rebuilding an appliance when the licensing process requires it.

Restrict private inputs on a shared workstation:

```bash
chmod 600 ../licenses/*.lic
chmod 600 terraform/user.tfvars ansible/group_vars/user.yml 2>/dev/null || true
chmod 600 terraform/aws-fortigate/99-local.auto.tfvars 2>/dev/null || true
chmod 600 terraform/aws-fortiweb/99-local.auto.tfvars 2>/dev/null || true
```

## 6. Understand Generated And Sensitive State

Do not commit:

- `terraform/user.tfvars`, module `99-local.auto.tfvars`, Terraform state, or
  state backups;
- `ansible/group_vars/user.yml`, `*.generated.yml`, generated inventories, or
  files under `ansible/secrets/`;
- kubeconfigs, private keys, certificates, registry credentials, or profile
  archives;
- appliance licenses, FortiFlex tokens, generated API keys/passwords, or
  rendered cloud-init data.

Terraform state can contain licenses, Bedrock credentials, appliance API keys,
generated passwords, and rendered user data even when outputs are marked
sensitive. Store it as secret material.

On the managed k3s host, `/etc/rancher/k3s/k3s.yaml` and the SSH user's
`~/.kube/config` grant cluster access. The default HTTPS gateway generates
`tls.crt` and `tls.key` under the managed host's
`~/tmp/demo-https-gateway-cert/` before rendering them into a Kubernetes
Secret. Operator-provided certificate and key paths remain local private
inputs. Do not copy any of these files into the repository or expose them in
diagnostic output.

## 7. Preflight Checklist

Before quickstart, confirm:

- [ ] the shell is in `<repo_root>`;
- [ ] required control-workstation commands are installed;
- [ ] AWS login, region, quota, model availability, key pair, and Marketplace
      terms are ready;
- [ ] vendor chart, image archives, and FortiAIGate license are outside Git;
- [ ] desired appliance licenses or explicit opt-outs are ready;
- [ ] operator configuration is ready, or interactive quickstart will be
      allowed to create/import it;
- [ ] Docker can reach the selected registry if publishing is required.

Quickstart checks required commands and local files before deployment. If
operator configuration was pre-staged manually, this optional check confirms
that its required files exist:

```bash
python3 scripts/user_profile.py check
```

Successful output includes `Required user profile files exist.` Then run the
[8.0.2 quickstart](quickstart-802.md); it initializes FAIG, and scenarios are
provisioned from Lab Management (see the
[instructor guide](instructor-guide-802.md)).
