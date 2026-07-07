# ECR Image Publishing

This workflow separates registry infrastructure from image publishing:

- Terraform creates private ECR repositories.
- `terraform/aws-prep` creates EC2 pull permissions when `registry_backend = "ecr"`.
- Ansible runs locally to load FortiAIGate image archives, tag images, compare immutable ECR tags, and push images.

## Create Private ECR Repositories

```bash
cd terraform/aws-ecr
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars before terraform init. Set registry-specific values
# such as repo_prefix and repositories.
# Do not put secrets or access keys in this file.
aws sso login --profile <profile-name>
terraform init
terraform fmt
terraform validate
terraform apply
```

ECR pull permissions are created by `terraform/aws-prep`, not by this module.
By default, `aws-prep` reads repository ARNs from
`terraform/aws-ecr/terraform.tfstate`.

Terraform also writes non-secret Ansible registry vars to:

```text
ansible/group_vars/ecr.generated.yml
```

The publish, deploy, status, and validation playbooks load `env.yml`,
`ecr.generated.yml`, `images.yml`, and then `all.yml`.

If repositories already exist from manual testing, import them before applying:

```bash
terraform import 'aws_ecr_repository.this["api"]' fortiaigate/api
terraform import 'aws_ecr_repository.this["core"]' fortiaigate/core
terraform import 'aws_ecr_repository.this["webui"]' fortiaigate/webui
terraform import 'aws_ecr_repository.this["scanner"]' fortiaigate/scanner
terraform import 'aws_ecr_repository.this["logd"]' fortiaigate/logd
terraform import 'aws_ecr_repository.this["license_manager"]' fortiaigate/license_manager
terraform import 'aws_ecr_repository.this["triton-models"]' fortiaigate/triton-models
terraform import 'aws_ecr_repository.this["custom-triton"]' fortiaigate/custom-triton
terraform import 'aws_ecr_repository.this["chatbot-basic"]' fortiaigate/chatbot-basic
```

## Stop Managing Imported ECR Repositories Without Deleting Them

Use `terraform state rm`, not `terraform destroy`, when repositories were
imported and should remain in AWS but no longer be managed by this local
Terraform state.

Back up local config and state first:

```bash
python3 scripts/backup_config.py
```

Then remove the imported repositories from Terraform state:

```bash
cd terraform/aws-ecr

terraform state rm 'aws_ecr_repository.this["api"]'
terraform state rm 'aws_ecr_repository.this["core"]'
terraform state rm 'aws_ecr_repository.this["webui"]'
terraform state rm 'aws_ecr_repository.this["scanner"]'
terraform state rm 'aws_ecr_repository.this["logd"]'
terraform state rm 'aws_ecr_repository.this["license_manager"]'
terraform state rm 'aws_ecr_repository.this["triton-models"]'
terraform state rm 'aws_ecr_repository.this["custom-triton"]'
terraform state rm 'aws_ecr_repository.this["chatbot-basic"]'
```

If lifecycle policies are also in state and should be left in AWS, remove those
from state too:

```bash
terraform state rm 'aws_ecr_lifecycle_policy.this["api"]'
terraform state rm 'aws_ecr_lifecycle_policy.this["core"]'
terraform state rm 'aws_ecr_lifecycle_policy.this["webui"]'
terraform state rm 'aws_ecr_lifecycle_policy.this["scanner"]'
terraform state rm 'aws_ecr_lifecycle_policy.this["logd"]'
terraform state rm 'aws_ecr_lifecycle_policy.this["license_manager"]'
terraform state rm 'aws_ecr_lifecycle_policy.this["triton-models"]'
terraform state rm 'aws_ecr_lifecycle_policy.this["custom-triton"]'
terraform state rm 'aws_ecr_lifecycle_policy.this["chatbot-basic"]'
```

`terraform state rm` only removes Terraform's local tracking for those
resources. It does not delete ECR repositories or lifecycle policies in AWS.

The `chatbot-basic` repository is used only by the optional demo chatbot image
published by `publish_chatbot_images.yml`. Keep it when deploying the chatbot
or demo home links to it. Remove it from `repositories` and skip the
`chatbot-basic` import/state commands only when intentionally omitting the demo
chatbot from the environment.

## Publish Images

The publisher runs on the local workstation and expects Docker plus AWS CLI SSO access. Docker must be usable by the current workstation user without `sudo`.

The current publish workflow is a local Docker staging workflow. It reads each
archive manifest, skips `docker load` when the archive's source tags already
exist locally with matching image IDs, inspects the local source images, tags
them for the target registry, and then runs `docker push`. When an immutable
ECR tag already exists, it may also pull the existing target image locally to
compare content before deciding whether to skip or fail.

Plan local disk capacity accordingly. Keep at least 2x-3x the total release
image archive size available on the local Docker disk before publishing. This
headroom accounts for the original archives, the loaded image layers, target
tags, and any existing ECR images pulled for comparison.

```bash
cd ansible
aws sso login --profile <profile-name>
ansible-playbook playbooks/publish_images.yml \
  -e registry_type=ecr
```

The playbook loads `ansible/group_vars/images.yml` when present. Copy the example catalog and set paths for local release directories:

```bash
cp group_vars/images.example.yml group_vars/images.yml
```

Publish all builds marked `state: active`:

```bash
ansible-playbook playbooks/publish_images.yml
```

Publish a specific version, regardless of state:

```bash
ansible-playbook playbooks/publish_images.yml -e publish_image_version=8.0.0
```

For local registry publishing:

```bash
ansible-playbook playbooks/publish_images.yml \
  -e registry_type=local \
  -e local_registry=localhost:5000
```

## Immutable ECR Tag Behavior

ECR repositories are immutable by default. For each mapped image:

- If the target tag does not exist, Ansible pushes it.
- If the target tag exists, Ansible pulls it and compares Docker image IDs with the locally loaded source image.
- If the content is identical, Ansible skips the push.
- If the content differs, Ansible fails and requires a new tag.

## Image Tags

By default, `publish_auto_image_map: true` extracts image refs from `docker load` output and preserves the exact loaded tags when pushing to the target registry. The target repository is derived from the final path component of the loaded source image.

For example, a loaded source image:

```text
dops-jfrog.fortinet-us.com/docker-fortiaigate-local/api:V8.0.0-build0024
```

is pushed to:

```text
<registry>/<repo_prefix>/api:V8.0.0-build0024
```

Triton images keep their loaded chart-specific tags:

- FortiAIGate 8.0.0 `triton-models`: `0.1.4`
- FortiAIGate 8.0.0 `custom-triton`: `25.11-onnx-trt-agt`
- FortiAIGate 8.0.1 `triton-models`: `0.1.6-s1`
- FortiAIGate 8.0.1 `custom-triton`: `25.11-onnx-trt-agt-s1`

Example build catalog:

```yaml
fortiaigate_image_builds:
  - version: "8.0.0"
    # Loaded app image tag: V8.0.0-build0024
    # image_tag: "V8.0.0-build0024"
    image_archive_dir: "{{ faig_workspace_root }}/images/8.0.0"
    state: active
    # Loaded Triton tags:
    # triton_model_image_tag: "0.1.4"
    # triton_image_tag: "25.11-onnx-trt-agt"

  - version: "8.0.1"
    # Loaded app image tag: V8.0.1-build0031
    # image_tag: "V8.0.1-build0031"
    image_archive_dir: "{{ faig_workspace_root }}/images/8.0.1"
    state: archive
    # Loaded Triton tags:
    # triton_model_image_tag: "0.1.6-s1"
    # triton_image_tag: "25.11-onnx-trt-agt-s1"
```

`image_archive_dir` should contain the per-image Docker archives from the release, for example `FAIG_api-...tar`, `FAIG_core-...tar`, and the Triton image archives. A single `image_archive` file is still supported for bundled releases.

Set `image_tag`, `triton_model_image_tag`, or `triton_image_tag` only when intentionally overriding deployment defaults. Publishing keeps the loaded Docker tags when `publish_auto_image_map: true`.

Set `publish_auto_image_map: false` only when you need to provide `fortiaigate_image_map` explicitly.

## Deployment Integration

Use the same registry values for deployment:

```yaml
ecr_registry: "123456789012.dkr.ecr.us-east-1.amazonaws.com"
ecr_repo_prefix: fortiaigate
fortiaigate_image_repository: "{{ ecr_registry }}/{{ ecr_repo_prefix }}"
fortiaigate_version: "8.0.0"
fortiaigate_image_tag: "V8.0.0-build0024"
fortiaigate_triton_model_image_tag: "0.1.4"
fortiaigate_triton_image_tag: "25.11-onnx-trt-agt"

# FortiAIGate 8.0.1:
# fortiaigate_version: "8.0.1"
# fortiaigate_image_tag: "V8.0.1-build0031"
# fortiaigate_triton_model_image_tag: "0.1.6-s1"
# fortiaigate_triton_image_tag: "25.11-onnx-trt-agt-s1"
```

When `ecr.generated.yml` exists, Ansible gets the registry, account ID, region, and repo prefix from Terraform automatically.

## Future Expansion - Shared ECR

The current default assumes this deployment owns the ECR repositories through
`terraform/aws-ecr`. A planned expansion is a shared-registry mode where the
first deployment creates and publishes to ECR, while later deployments in other
VPCs consume the same registry values and skip ECR creation.

For same-account deployments, the later k3s EC2 roles only need IAM pull
permissions scoped to the shared ECR repository ARNs. For cross-account
deployments, the ECR owner must also add repository policies that allow the
consumer account or EC2 role to pull. Optional source-IP conditions can be used
as hardening, but cross-account IAM and ECR repository policy are the primary
access controls.

See `Phase2Plan.MD` in the parent FAIG workspace for the shared ECR expansion
plan.

A related future direction is to treat ECR primarily as a data-source/input
contract for this demo repository. ECR creation/import, cross-account repository
policies, and image publishing may move to a separate registry/image workflow or
repo. At minimum, keep ECR setup and publishing as a separate workflow from k3s
and application deployment.

Never commit real `terraform.tfvars`, image archives, registry passwords, or AWS credentials.
