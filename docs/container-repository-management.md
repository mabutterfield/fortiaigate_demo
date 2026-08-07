# Container Repository Management

This is the source of truth for Docker image inputs, tags, ECR, local
registries, publication, verification, cleanup, and rollback. The automated
quickstart still calls this workflow today; future work intends to separate
repository maintenance from normal lab deployment.

All commands run from `<repo_root>`.

## Ownership And Image Inputs

| Image family | Source/build context | Target | How deployment consumes it |
|---|---|---|---|
| FortiAIGate application images | Vendor `.tar` archives under `../images/<release>/`; publisher uses `docker load` rather than building source | `api`, `core`, `webui`, `scanner`, `logd`, `license_manager` | FortiAIGate Helm values use the configured repository prefix and release tag |
| FortiAIGate inference images | Vendor archives and their loaded tags | `triton-models`, `custom-triton` | FortiAIGate Helm values use their independent Triton tags |
| Custom chatbot | Docker build context `chatbot/app/` | `chatbot-basic` | Chatbot Helm values use `chatbot_image_repository` and `chatbot_image_tag` |
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

`chatbot-basic` is mutable for development and
`chatbot_publish_overwrite_existing_tag: true` permits same-tag rebuilds. That
exception is convenient for iteration but is not a release-versioning policy.
Before a release, bump or explicitly confirm `chatbot_image_tag`; the chatbot
uses `imagePullPolicy: Always`, but a unique tag is the reliable audit trail.

Primary tag variables live in tracked `ansible/group_vars/system.yml` for the
repository baseline. An operator can test an alternate existing tag through
ignored `ansible/group_vars/user.yml`. A repository release must update the
tracked tag in the same change that changes image content.

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
triton-models, custom-triton, chatbot-basic
```

`terraform/aws-prep` reads ECR state and grants the k3s EC2 role scoped pull
permissions when `registry_backend = "ecr"`. Do not place static AWS access
keys in Terraform or Ansible files.

### Existing Repositories

Import a pre-existing repository before apply. Repeat with the matching key and
repository name for each existing item:

```bash
terraform -chdir=terraform/aws-ecr import \
  'aws_ecr_repository.this["api"]' \
  fortiaigate/api
```

The automated quickstart's repeat-run mode can import expected missing ECR
repository state when possible. Review Terraform plans carefully so an import
mistake does not create a competing repository or lifecycle policy.

## Publish FortiAIGate Images

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

Use `image_archive_dir` in ignored user vars or as an explicit extra variable
when the archive path differs from the configured build catalog:

```bash
ansible-playbook ansible/playbooks/publish_images.yml \
  -e image_archive_dir=/private/path/to/images/8.x
```

The publisher reads `docker load` output, preserves loaded tags when automatic
mapping is enabled, authenticates to the selected registry, and reports
published and skipped images.

## Build And Publish The Chatbot

When `chatbot/app/` content or its dependencies change, increment
`chatbot_image_tag`, then publish:

```bash
ansible-playbook ansible/playbooks/publish_chatbot_images.yml
```

The publisher builds `chatbot/app/Dockerfile` for the configured platform
(AWS defaults to `linux/amd64`), logs in, and pushes
`<registry>/<prefix>/chatbot-basic:<tag>`.

Scenario metadata, LiteLLM instruction files, and rendered chatbot profile
configuration are deployed through configuration and do not by themselves
require a chatbot image rebuild. Changes to `chatbot.py`, `agent_probe.py`,
`requirements.txt`, or the Dockerfile do.

## Local Registry

`scripts/local_setup.py` records the registry endpoint and repository prefix in
ignored `ansible/group_vars/registry.generated.yml`. Both the workstation and
local k3s host must resolve and reach the exact configured host and port.

```bash
ansible-playbook ansible/playbooks/publish_images.yml \
  -e registry_type=local \
  -e local_registry=<registry-host>:5000

FAIG_DEPLOYMENT_TARGET=local \
ansible-playbook -i local ansible/playbooks/publish_chatbot_images.yml
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
ansible-playbook -i cloud ansible/playbooks/status_chatbots.yml

# Local lane
FAIG_DEPLOYMENT_TARGET=local \
ansible-playbook -i local ansible/playbooks/status_chatbots.yml
```

Status proves readiness, not image provenance. For a release audit, also inspect
the pod image/image ID on the k3s host and compare it with the registry digest.

## Cleanup

Use the guided teardown for repeat AWS lab cycles:

```bash
python3 scripts/automated_teardown.py
```

It destroys dependent lab infrastructure while preserving ECR repository data
through the repository's state-removal workflow. Do not run a broad ECR
`terraform destroy` when the intention is to retain published images.

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
2. Set the applicable image tag in ignored `ansible/group_vars/user.yml` for a
   local rollback, or revert the tracked tag in a release branch.
3. Redeploy only the affected workload.
4. Run its status playbook and functional validation.

```bash
ansible-playbook -i cloud ansible/playbooks/deploy_chatbots.yml
ansible-playbook -i cloud ansible/playbooks/status_chatbots.yml
python3 -m functional_test
```

For FortiAIGate vendor images, keep the application and Triton tag set aligned
with a known compatible chart/release combination.

## Current Quickstart Integration And Future Boundary

Today, automated AWS quickstart creates/imports ECR, optionally publishes
vendor/chatbot images, and then deploys workloads that consume the generated
registry values. Local quickstart consumes the registry configuration created
by `local_setup.py` and uses the same publisher roles.

Do not remove those working calls yet. The intended future boundary is:

- repository maintenance creates/imports registries and publishes immutable,
  verified release images;
- deployment consumes repository URLs, tags, digests, and pull credentials as
  inputs; and
- the normal quickstart no longer needs Docker archives or registry ownership.

That separation is directional and is not implemented in the current v1.0
workflow.
