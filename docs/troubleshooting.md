# Troubleshooting

Start with the status playbooks. They are designed to give quick `READY`,
`NOT READY`, or `GO` / `NO GO` summaries before running deeper validation.

## First Checks

- Confirm AWS login: `aws sts get-caller-identity --profile <profile-name>`
- Confirm Terraform variables exist and are local ignored files.
- Confirm `terraform/aws-ec2-k3s` generated `ansible/inventory/aws.generated.ini`.
- Confirm SSH to the k3s host works before running Ansible.
- Confirm Docker can run without `sudo` before publishing images.

## Kubernetes

Use:

- `ansible/playbooks/validate_k3s.yml`
- `ansible/playbooks/status_fortiaigate.yml`
- `ansible/playbooks/validate_faig.yml`

`validate_k3s.yml` checks the Kubernetes foundation only. FortiAIGate app
readiness belongs in `status_fortiaigate.yml` and `validate_faig.yml`.

## FortiAIGate

FortiAIGate Helm deploys asynchronously by default. If the deploy playbook
returns after Helm accepts the release, pods may still be pulling images,
starting probes, binding storage, or waiting for Triton.

FortiAIGate 8.0.1 serves the web UI under `/ui/`.

## Image Publishing

FortiAIGate image publishing loads missing source images into local Docker,
tags them, and pushes to ECR. Keep enough Docker disk available and avoid
reusing immutable ECR tags for changed FortiAIGate release images.

The chatbot image publisher is separate. By default, the `chatbot-basic` ECR
repository is mutable and `chatbot_publish_overwrite_existing_tag: true`, so
rerunning the chatbot publisher can republish the same `chatbot_image_tag`.

## More Detail

- [Deployment Runbook](deployment-runbook.md)
- [ECR](ecr.md)
- [Kubernetes](kubernetes.md)
- [Bedrock](bedrock.md)
