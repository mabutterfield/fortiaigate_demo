# AWS Instance Sizing for FortiAIGate 8.0.2

This is a planning guide, not proof that this repository deploys 8.0.2. The
current quickstart and Terraform defaults still target the earlier release and
must be updated and validated before use. EC2 is an instance type; an AMI is the
operating-system image launched on that instance.

## GPU support and lab categories

The FortiAIGate 8.0.2 Administration Guide lists NVIDIA L40/L40S/RTX 6000 Ada,
H100/H200/H800/H20, RTX PRO 6000/5000/5500 and B200/B300. It recommends
Blackwell for hardware acceleration. It does not list L4 or A10G as supported
production GPUs. The included 8.0.2 chart contains an `l4` tuning profile marked
`devOnly`, with one DLP instance and reduced vLLM concurrency. Its comments
show a 24 GB L4 can be used for development; this is not a vendor-supported
production minimum or proof that our entire lab fits.

The admin guide does not give a complete 8.0.2 CPU/RAM/storage minimum or
recommendation in its prerequisites section. Do not treat the earlier 8.0.1
4-vCPU/25-GB minimum or 24-core/70-GB and dual-GPU recommendation as 8.0.2
requirements. Confirm build-specific requirements with Fortinet and leave
capacity for k3s, LiteLLM, chatbot, MCP and operating system. One GPU can be
shared by Triton and vLLM according to the chart; multi-GPU placement and
licensing must be verified during the deployment.

- **24 GB development test:** G6/L4 with the `l4` profile; experimental and
  unsupported for 8.0.2 production. AWS reports 22,888 MiB usable GPU memory
  even though it markets an L4 as 24 GB.
- **Supported GPU candidate:** G6e/L40S, marketed as 48 GB; verify actual
  available VRAM, host resources, license and model behavior. AWS reports
  45,776 MiB per GPU. This is a supported GPU family, not a demonstrated
  minimum whole-system configuration.
- **Recommended GPU architecture:** G7e/RTX PRO 6000 Blackwell with 96 GiB
  per GPU, matching the chart's default tuning. Hardware qualification does not
  imply that the full demo has been validated.

The 8.0.2 guide requires license coverage for each distinct GPU used by Triton
and vLLM. Verify the **Security Scanning** status: uncovered GPUs can disable
inspection while model traffic continues. Extra GPUs can increase licensing
costs; check entitlement before planning a multi-GPU deployment.

## US East (N. Virginia) candidates

Prices below are AWS Price List Linux On-Demand shared-tenancy compute prices
queried 2026-11-09. GPU VRAM labels use marketed GB or reported GiB, as
indicated above; RAM is GiB. Prices exclude EBS, networking, public IPs,
Bedrock, FortiAIGate and appliance licenses, taxes and other services. Actual
capacity, account quota and prices can change. AWS specifications:
[accelerated instance types](https://docs.aws.amazon.com/ec2/latest/instancetypes/ac.html)
and [G6 instances](https://aws.amazon.com/ec2/instance-types/g6/).
The price source is the AWS Price List API (`AmazonEC2`, location US East
(N. Virginia), Linux, shared tenancy, no preinstalled software, used capacity,
On-Demand hourly rate). Verify the live price before a long-running lab.

| Classification | Instance | vCPU | RAM GiB | GPUs | GPU memory per card | USD/hour |
|---|---|---:|---:|---|---:|---:|
| Experimental L4, smaller lab | `g6.4xlarge` | 16 | 64 | 1 x L4 | 24 GB | 1.3232 |
| Experimental L4, more host RAM | `g6.8xlarge` | 32 | 128 | 1 x L4 | 24 GB | 2.0144 |
| Experimental multi-GPU L4 | `g6.12xlarge` | 48 | 192 | 4 x L4 | 24 GB | 4.6016 |
| Supported GPU candidate, small host | `g6e.2xlarge` | 8 | 64 | 1 x L40S | 48 GB | 2.24208 |
| Supported GPU candidate, initial sizing | `g6e.4xlarge` | 16 | 128 | 1 x L40S | 48 GB | 3.00424 |
| Supported GPU candidate, more CPU/RAM | `g6e.8xlarge` | 32 | 256 | 1 x L40S | 48 GB | 4.52856 |
| Supported GPU candidate, multi-GPU | `g6e.12xlarge` | 48 | 384 | 4 x L40S | 48 GB | 10.49264 |
| Blackwell candidate, single GPU | `g7e.4xlarge` | 16 | 128 | 1 x RTX PRO 6000 | 96 GiB | 3.99816 |
| Blackwell candidate, more CPU/RAM | `g7e.8xlarge` | 32 | 256 | 1 x RTX PRO 6000 | 96 GiB | 5.26824 |
| Blackwell candidate, dual GPU | `g7e.12xlarge` | 48 | 512 | 2 x RTX PRO 6000 | 96 GiB | 8.28608 |

`g7e.12xlarge` is a two-GPU comparison; the listed G6 and G6e families jump
from one to four GPUs. Four 24 GB cards do not combine into one 96 GB memory
space for a single model without software support. A single GPU shared by
both engines is the simplest baseline; compare a dedicated second card only
after verifying scheduling, throughput and per-GPU license coverage.

The L40S `g6e.4xlarge` is a reasonable supported-GPU starting candidate,
not a validated vendor minimum. The `g7e.4xlarge` is the first Blackwell
candidate to investigate. The L4 profile offers a cheaper exploratory lane;
use it only if the license and vendor allow it, without claiming support.
An 8-hour session costs approximately $10.59 on `g6.4xlarge`, $24.03 on
`g6e.4xlarge`, or $31.99 on `g7e.4xlarge` for EC2 compute alone.

## Point-in-time capacity

The existing `origin/feature/advanced` capacity probe was run on 2026-11-09
in `us-east-1`, testing offered account-visible AZs in order until the first
successful launch for each instance type. Successful probe instances were
terminated and the script reported deletion of every temporary VPC. The
G/VT On-Demand quota was 768 vCPUs at the time. Results:

| Instance | Outcome | Tested AZs |
|---|---|---|
| `g6.4xlarge` | Available | `1a` insufficient; `1b` succeeded |
| `g6.8xlarge` | Available | `1a` succeeded |
| `g6.12xlarge` | Insufficient capacity | `1a`, `1b`, `1c`, `1d`, `1f` |
| `g6e.2xlarge` | Insufficient capacity | `1a`, `1b`, `1c`, `1d` |
| `g6e.4xlarge` | Available | `1a` insufficient; `1b` succeeded |
| `g6e.8xlarge` | Insufficient capacity | `1a`, `1b`, `1c`, `1d` |
| `g6e.12xlarge` | Insufficient capacity | `1a`, `1b`, `1c`, `1d` |
| `g7e.4xlarge` | Available | `1a` succeeded |
| `g7e.8xlarge` | Available | `1a` succeeded |
| `g7e.12xlarge` | Available | `1a` succeeded |

AZ abbreviations refer to `us-east-1`; names are account-specific. A
successful temporary launch indicates capacity at that moment for that
account and AZ; it is not a reservation or guarantee for later deployment.
AZs after the first success were not tested. The run's detailed JSON is kept
locally outside the repository and contains account and resource identifiers.
Do not commit it. `InsufficientInstanceCapacity`, quota errors, unsupported
offerings and authentication errors must be reported separately.

## Operational notes

- AWS reports a GPU vCPU quota for the account, not guaranteed capacity. A
  larger multi-GPU instance may consume many vCPUs and require separate quota.
- Each GPU used by the inference engines requires coverage. A multi-GPU EC2
  shape does not mandate allocating all cards, but placement and licensing
  must be verified with the 8.0.2 chart and license manager.
- Compare the vendor GPU support list with instance GPU model and drivers,
  and confirm that the intended region/AZ actually offers the instance type.
- Existing quickstart choices and the `g4dn.4xlarge` Terraform default are
  inherited from 8.0.1 and are not 8.0.2 sizing guidance. Do not use them as
  the supported baseline until the automation has been updated.
- The old reduced Triton overlay was designed for 8.0.1; do not assume it is
  correct for 8.0.2. Validate Helm output, GPU scheduling, available memory,
  detector availability and sustained workload on a fresh instance.
- This research does not select an AMI. Verify Ubuntu 24.04 compatibility,
  NVIDIA drivers and toolkit, architecture and storage before provisioning.
