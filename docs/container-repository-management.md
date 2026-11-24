# Container Repository Management

This is the source of truth for Docker image inputs, tags, ECR, local
registries, publication, verification, cleanup, and rollback. Repository
maintenance is a separate maintainer workflow and is not run by the 8.0.2
quickstart. The standalone publisher predates 8.0.2 and needs a fresh-image
verification before its commands can be treated as a validated 8.0.2 recipe.

All commands run from `<repo_root>`.

## Ownership And Image Inputs

| Image family | Source/build context | Target | How deployment consumes it |
|---|---|---|---|
| FortiAIGate application images | Vendor `.tar` archives under `../images/<release>/`; publisher uses `docker load` rather than building source | `api`, `core`, `webui`, `scanner`, `logd`, `license_manager` | FortiAIGate Helm values use the configured repository prefix and release tag |
| FortiAIGate 8.0.2 inference and guardrail images | Vendor archives and their loaded tags | `faig-models`, `vllm-server`, `custom-triton`, `guardrail`, `guardrail-scanner`, `llm-gateway` | The chart and rendered values use their corresponding tags; `triton-models` is retained for older releases |
| 8.0.1 demo chatbot (retired 2026-11-20) | Removed from the 8.0.2 branch; build context preserved on `main` / tag `v1.0_faig8.0.1` | `chatbot-basic` (existing images left in place) | Not deployed. The 8.0.2 lab chatbot uses the stock `python` image with code in ConfigMaps (no build) |
| Third-party application images | Public upstream registries, for example LiteLLM, PostgreSQL, Python, nginx, and optional Open WebUI | Not republished by the normal workflow | Individual Ansible role defaults and Helm values reference upstream repositories/tags |

Terraform in `terraform/aws-ecr` owns AWS ECR repositories, mutability,
scanning, lifecycle policies, and the generated registry contract. Ansible
owns loading/building, tagging, authentication, pushing, and reporting.

## Tag Policy

Increment the image tag whenever image content changes. This is mandatory for
release candidates and published releases.

FortiAIGate repositories are immutable by default. If the same tag exists:

- matching content is skipped;
- differing content fails and requires a new tag.

The existing `chatbot-basic` repository is mutable and retained for the 8.0.1
archive. The 8.0.2 lab chatbot does not publish to it. Do not modify or delete
its existing images merely because the old application was retired.

Primary tag variables live in tracked `ansible/group_vars/system.yml` for the
repository baseline. An operator can test an alternate existing tag through
local `ansible/group_vars/user.yml`, which is excluded by `.gitignore`. A
repository release must update the tracked tag in the same change that changes
image content.

## AWS ECR Infrastructure

The AWS registry module consumes shared values from `terraform/user.tfvars`
through `terraform/aws-ecr/50-user.auto.tfvars` and writes non-secret outputs
to `ansible/group_vars/ecr.generated.yml`.

Prepare an optional module override, then initialize and apply:

```bash
cp terraform/aws-ecr/99-local.auto.tfvars.example \
  terraform/aws-ecr/99-local.auto.tfvars

aws sso login --profile <profile-name>
terraform -chdir=terraform/aws-ecr init
terraform -chdir=terraform/aws-ecr fmt
terraform -chdir=terraform/aws-ecr validate
terraform -chdir=terraform/aws-ecr apply
```

The tracked repository set is:

```text
api, core, webui, scanner, logd, license_manager,
triton-models, custom-triton, chatbot-basic, guardrail,
guardrail-scanner, llm-gateway, faig-models, vllm-server
```

`terraform/aws-prep` grants the k3s EC2 role pull permissions scoped to the
configured ECR namespace in the current account and region; it does not read ECR state. Do not place static AWS access
keys in Terraform or Ansible files.

### Existing Repositories

Import a pre-existing repository before apply. Repeat with the matching key and
repository name for each existing item:

```bash
terraform -chdir=terraform/aws-ecr import \
  'aws_ecr_repository.this["api"]' \
  fortiaigate/api
```

Import is a separate maintainer action; quickstart does not import or apply ECR.
Review Terraform plans carefully so an import mistake does not create a
competing repository or lifecycle policy.

Lifecycle policies are owned by this same ECR module, not by lab deployment.
For each repository, first inspect whether AWS already has a lifecycle policy:

```bash
aws ecr get-lifecycle-policy --profile <profile-name> --region <region> \
  --repository-name fortiaigate/api
```

If one exists, import it into the **same ECR workspace** as its repository:

```bash
terraform -chdir=terraform/aws-ecr import \
  'aws_ecr_lifecycle_policy.this["api"]' fortiaigate/api
```

Repeat for the configured repositories, keeping Virginia and Ohio in separate
state workspaces. Do not import a policy that AWS reports does not exist. The
repository import helper does not import policies automatically. After imports,
inspect a plan and compare all existing lifecycle rules before applying: the
tracked policy can expire images and may differ from the policy in AWS. An
import does not itself change the live policy, but an apply can. Never use a
broad ECR destroy for a lab teardown. Quickstart discovers the registry directly from AWS and rebuilds `ecr.generated.yml` without applying ECR.

## Publish FortiAIGate Images

**8.0.2 status:** The following publisher workflow is inherited from earlier
releases and has not yet been validated end to end for every 8.0.2 archive and
tag. Inspect the archive tags and image mapping before publishing. Never alter
existing 8.0.1 or 8.0.2 images as part of a normal lab deployment.

The workstation needs Docker disk space for source archives, loaded layers,
target tags, and possible comparison pulls. Allow roughly two to three times
the total archive size.

Publish the configured active build to ECR:

```bash
aws sso login --profile <profile-name>
ansible-playbook ansible/playbooks/publish_images.yml \
  -e registry_type=ecr
```

Publish one catalog release or selected target repositories:

```bash
ansible-playbook ansible/playbooks/publish_images.yml \
  -e publish_image_version=8.0.1

ansible-playbook ansible/playbooks/publish_images.yml \
  -e publish_target_repos=api,webui
```

Use `image_archive_dir` in local operator vars or as an explicit extra variable
when the archive path differs from the configured build catalog:

```bash
ansible-playbook ansible/playbooks/publish_images.yml \
  -e image_archive_dir=/private/path/to/images/8.x
```

The publisher reads `docker load` output, preserves loaded tags when automatic
mapping is enabled, authenticates to the selected registry, and reports
published and skipped images.

## Chatbot Image (Retired)

The 8.0.1 demo chatbot and `publish_chatbot_images.yml` were removed from the
8.0.2 branch on 2026-11-20. The 8.0.2 lab chatbot needs no image build: it runs
the stock `python` image with its code mounted from ConfigMaps (see
[lab chatbot](lab-chatbot.md)). Existing `chatbot-basic` images in ECR are not
deleted by this change.

## Local Registry

`scripts/local_setup.py` records the registry endpoint and repository prefix in
environment-owned `ansible/group_vars/registry.generated.yml`, which is
excluded from Git. Both the workstation and local k3s host must resolve and
reach the exact configured host and port.

```bash
ansible-playbook ansible/playbooks/publish_images.yml \
  -e registry_type=local \
  -e local_registry=<registry-host>:5000

```

For an authenticated local registry, pass credentials through
`LOCAL_REGISTRY_USERNAME` and `LOCAL_REGISTRY_PASSWORD` environment variables.
For plain HTTP, configure that exact host and port as an insecure registry on
the Docker publisher and k3s/containerd host. Limit an unauthenticated registry
to a trusted lab network.

## Verification

### ECR

```bash
terraform -chdir=terraform/aws-ecr output repository_urls
aws ecr describe-images \
  --profile <profile-name> \
  --region <aws-region> \
  --repository-name fortiaigate/chatbot-basic
```

Use the applicable FortiAIGate repository name to verify vendor images.

### Local Docker And Registry

```bash
docker image inspect <registry>/<prefix>/<repository>:<tag>
docker manifest inspect <registry>/<prefix>/<repository>:<tag>
```

### Deployed Workloads

```bash
ansible-playbook -i cloud ansible/playbooks/status_fortiaigate.yml
ansible-playbook -i cloud ansible/playbooks/status_litellm.yml
```

Status proves readiness, not image provenance. For a release audit, also inspect
the pod image/image ID on the k3s host and compare it with the registry digest.

## Cleanup

Use the guided teardown for repeat AWS lab cycles, selecting the same
Terraform workspace and overrides as the deployment:

```bash
python3 scripts/automated_teardown.py
```

It preserves ECR repositories, lifecycle policies and Terraform state, along
with S3 and shared prep resources. It does not remove ECR resources from state.
Do not run a broad ECR `terraform destroy` to remove a lab.

Local Docker cleanup should target confirmed image references rather than all
images on the workstation:

```bash
docker image rm <registry>/<prefix>/<repository>:<obsolete-tag>
```

ECR lifecycle policies retain a configured number of tagged images. Delete a
remote tag only after confirming no deployed release or rollback depends on
its digest.

## Rollback

Rollback reuses a known registry tag/digest; it does not rebuild old source
under the current tag.

1. Confirm the previous tag exists in ECR or the local registry.
2. Set the applicable image tag in local `ansible/group_vars/user.yml` for a
   local rollback, or revert the tracked tag in a release branch.
3. Redeploy only the affected workload.
4. Run its status playbook and functional validation.

```bash
ansible-playbook -i cloud ansible/playbooks/deploy_fortiaigate.yml
ansible-playbook -i cloud ansible/playbooks/status_fortiaigate.yml
# then re-run the affected catalog case, e.g.:
# python3 -m functional_test catalog-baseline --scenario <id> --action <alert|block|redact> --key-file <file> --admin-credentials <file>
```

For FortiAIGate vendor images, keep the application and Triton tag set aligned
with a known compatible chart/release combination.

## Current Quickstart Boundary

The AWS quickstart discovers the registry, repositories and required tags through read-only AWS calls; it does not import, apply or publish repositories. The intended final boundary is:

- repository maintenance creates/imports registries and publishes immutable,
  verified release images;
- deployment consumes repository URLs, tags, digests, and pull credentials as
  inputs; and
- the normal quickstart no longer needs Docker archives or registry ownership.

The versioned manifest consumer contract and independent state handling remain
to be implemented and validated. Local 8.0.2 deployment is not yet supported.
