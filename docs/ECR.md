# ECR Image Publishing

This workflow separates registry infrastructure from image publishing:

- Terraform creates private ECR repositories and optional EC2 pull permissions.
- Ansible runs locally to load FortiAIGate image archives, tag images, compare immutable ECR tags, and push images.

## Create Private ECR Repositories

```bash
cd terraform/aws-ecr
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars before terraform init. Set non-secret values such as
# aws_profile, aws_region, repo_prefix, and optional ec2_pull_role_name.
# Do not put secrets or access keys in this file.
aws sso login --profile <profile-name>
terraform init
terraform fmt
terraform validate
terraform apply
```

Set `ec2_pull_role_name` only when this module should attach a scoped pull policy to an EC2 role. The ECR module does not create IAM roles. To create the k3s host role and instance profile with Terraform, use `terraform/aws-ec2-k3s` with `create_iam_instance_profile = true`, then pass its `iam_role_name` output back to this module.

Terraform also writes non-secret Ansible registry vars to:

```text
ansible/group_vars/ecr.generated.yml
```

The publish, deploy, status, and validation playbooks load `ecr.generated.yml` first and `all.yml` second. Use `all.yml` for manual overrides.

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
```

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

Never commit real `terraform.tfvars`, image archives, registry passwords, or AWS credentials.
