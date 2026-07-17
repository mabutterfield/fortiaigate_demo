# AWS Instance Sizing

This page separates low-cost test infrastructure from supported FortiAIGate validation targets.

FortiAIGate sizing guidance is approximately:

- 24 physical CPU cores
- 70 GB RAM
- dual GPU recommended

AWS publishes vCPU counts, not physical core counts. For typical Intel-based EC2 instances, 2 vCPUs roughly map to 1 physical core, so the 24-core recommendation is roughly 48 vCPUs.

Pricing below is an approximate us-east-1 estimate from lab notes. AWS pricing and instance availability change; verify the current price and availability before long-running tests. The `terraform/aws-ec2-k3s` module now also outputs a current AWS Price List estimate for the configured `instance_type` and `aws_region`:

```bash
terraform output ec2_instance_hourly_cost_usd
terraform output ec2_instance_monthly_cost_usd
```

Those outputs estimate Linux On-Demand shared-tenancy EC2 compute only. They do not include EBS, EIP idle charges, data transfer, Bedrock, marketplace, or licensing costs.

## Current Defaults

| Purpose | Instance | Notes |
|---|---|---|
| Terraform default lab size | `g4dn.4xlarge` | Cost-conscious T4 lab default; not an officially supported GPU family |
| Lower-cost supported GPU candidate | `g6.4xlarge` | L4 GPU family, modern single-GPU lab option |
| Production-like supported validation | `g6.8xlarge` | L4 GPU with stronger CPU/RAM headroom |
| Multi-GPU validation | `g6.12xlarge` | Four L4 GPUs, meets/exceeds the dual-GPU recommendation |

## FortiGate And FortiWeb Appliances

FortiGate and FortiWeb do not need GPU instances for the appliance baseline.
FortiGate uses `c6i.xlarge` by default; `c6i.large` is acceptable for
lighter validation when cost matters more than headroom. FortiWeb 8.0
Marketplace images support the older `c5`/`m5`/`t3` families, not `c6i`.

| Appliance | Instance | Approx. Cost | Use |
|---|---|---:|---|
| FortiGate | `c6i.large` | ~$0.08/hr | Acceptable lower-cost appliance test size |
| FortiGate | `c6i.xlarge` | ~$0.17/hr | Default FortiGate size |
| FortiWeb | `c5.large` | ~$0.085/hr | Acceptable lower-cost appliance test size |
| FortiWeb | `c5.xlarge` | ~$0.17/hr | Default FortiWeb size |

## Test Infrastructure

These are useful for automation, Kubernetes, and budget lab testing. The T4-based `g4dn` family is not treated here as officially supported FortiAIGate infrastructure.

| Instance | vCPU | RAM | GPU | GPU VRAM | Local NVMe | Approx. Cost | Use |
|---|---:|---:|---|---:|---:|---:|---|
| `g4dn.xlarge` | 4 | 16 GB | 1 x T4 | 16 GB | 125 GB | ~$0.53/hr | Smoke test automation only |
| `g4dn.2xlarge` | 8 | 32 GB | 1 x T4 | 16 GB | 225 GB | ~$0.75/hr | Minimum viable lab with reduced chart values |
| `g4dn.4xlarge` | 16 | 64 GB | 1 x T4 | 16 GB | 225 GB | ~1.20/hr | Current Terraform default lab size |
| `g4dn.8xlarge` | 32 | 128 GB | 1 x T4 | 16 GB | 900 GB | ~$2.18/hr | Strong budget T4 lab box |

## Supported Validation Infrastructure

Use these when validating FortiAIGate behavior on supported GPU families.

| Instance | vCPU | RAM | GPU | GPU VRAM | Local NVMe | Approx. Cost | Use |
|---|---:|---:|---|---:|---:|---:|---|
| `g6.4xlarge` | 16 | 64 GB | 1 x L4 | 24 GB | 600 GB | ~$2.30/hr | Reasonable modern single-GPU lab |
| `g5.8xlarge` | 32 | 128 GB | 1 x A10G | 24 GB | 900 GB | ~$3.06/hr | A10G production-like validation |
| `g6.8xlarge` | 32 | 128 GB | 1 x L4 | 24 GB | 1.2 TB | ~$2.95/hr | Recommended single-GPU L4 validation |
| `g5.12xlarge` | 48 | 192 GB | 4 x A10G | 96 GB total | 3.8 TB | ~$5.67/hr | Multi-GPU A10G validation |
| `g6.12xlarge` | 48 | 192 GB | 4 x L4 | 96 GB total | 1.8 TB | ~$5.85/hr | Multi-GPU L4 validation |

## Experimental Infrastructure

These are interesting for future or model-heavy tests, but should not be treated as the default FortiAIGate validation target without separate confirmation.

| Instance | vCPU | RAM | GPU | GPU VRAM | Local NVMe | Approx. Cost | Why |
|---|---:|---:|---|---:|---:|---:|---|
| `g6e.4xlarge` | 16 | 128 GB | 1 x L40S | 48 GB | Verify | ~$3.50/hr | Large single-GPU VRAM |
| `g7e.4xlarge` | 16 | 128 GB | Verify current AWS GPU | Verify | Verify | ~$4.50/hr | Future-looking large-VRAM testing |

## Recommendation Summary

| Category | Recommendation |
|---|---|
| Cheapest smoke test | `g4dn.xlarge` |
| Current default lab deployment | `g4dn.4xlarge` |
| Minimum modern supported GPU lab | `g6.4xlarge` |
| Preferred single-GPU supported validation | `g6.8xlarge` |
| Supported A10G validation | `g5.8xlarge` |
| Supported multi-GPU validation | `g6.12xlarge` |

## Notes

- `g4dn` is useful for proving the Terraform, Ansible, k3s, ingress, storage, and Helm workflow.
- `g4dn` should not be used as the final supported GPU validation result.
- Prefer `g6.8xlarge` when the goal is a stronger single-node validation pass with a supported L4 GPU.
- Prefer `g6.12xlarge` or `g5.12xlarge` when dual/multi-GPU behavior matters.
