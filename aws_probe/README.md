# EC2 Capacity Probe

`capacity_probe.py` performs a short-lived, point-in-time On-Demand EC2 capacity check. It creates an isolated temporary VPC, one private subnet per tested Availability Zone, a no-ingress security group, and a lightweight Amazon Linux instance. Each successful instance is terminated and confirmed before the next AZ is tested, followed by its temporary networking. This prevents prior successful allocations from creating artificial vCPU-quota failures later in the same run.

It does not use Terraform, create FortiAIGate resources, deploy k3s, use public IP addresses, or reserve capacity. A successful launch demonstrates only that the requested type could be allocated in that Availability Zone at that instant.

## Requirements

Run from the repository root with AWS CLI v2 credentials that can create and delete VPC, subnet, security-group, and EC2 resources, and read the public Amazon Linux SSM parameter. The generated JSON report is intentionally ignored because it contains AWS account and temporary resource IDs.

## Dry run

```bash
python3 aws_probe/capacity_probe.py \
  --profile ftnt-admin \
  --region us-east-1 --region us-east-2 \
  --instance-type g5.8xlarge --instance-type g6.8xlarge
```

## Execute the requested four regional/type probes

```bash
python3 aws_probe/capacity_probe.py \
  --profile ftnt-admin \
  --region us-east-1 --region us-east-2 \
  --instance-type g5.8xlarge --instance-type g6.8xlarge \
  --all-zones --execute
```

Add `--stop-on-first-success` to avoid trying further AZs after a type succeeds in a region. Use `--availability-zone us-east-2a` to restrict the test to a specific account-visible AZ.

## Reusing recent capacity results

The tracked [capacity history](capacity_history.md) records an AZ/type pair's last point-in-time status and timestamp. A normal execution skips a result less than seven days old, avoiding repeated GPU allocation attempts. This applies after EC2 has discovered the type's current offerings, so a withdrawn or newly offered AZ is still reflected correctly.

```bash
# Use the seven-day default cache (or another freshness window).
python3 aws_probe/capacity_probe.py ... --cache-days 14 --execute

# Force fresh allocation attempts despite the history table.
python3 aws_probe/capacity_probe.py ... --all-zones --refresh --execute

# Add an older report to the table without contacting AWS.
python3 aws_probe/capacity_probe.py --record-report aws_probe/reports/capacity-probe-<run-id>.json
```

The history is useful for planning, not a capacity reservation or a guarantee.

## Result meanings

| Outcome | Meaning |
| --- | --- |
| `capacity_available` | `RunInstances` accepted the request and EC2 assigned a temporary instance ID. It is immediately terminated. |
| `capacity_unavailable` | AWS rejected the On-Demand request with a capacity-specific error such as `InsufficientInstanceCapacity`. |
| `quota_error` | AWS rejected the request because an account quota prevented the launch, normally `VcpuLimitExceeded` or `InstanceLimitExceeded`. This is distinct from regional/AZ capacity. |
| `not_offered` | EC2 does not list the type as offered in an available AZ matching the requested constraints. |
| `aws_error` | Authentication, IAM permission, AMI/SSM, network-resource, or another AWS failure prevented a capacity result. |

The report also reads the standard EC2 **Running On-Demand G and VT instances** vCPU quota when permitted. It is advisory: it does not reveal current account usage and cannot prove a launch will succeed.

## Cleanup and recovery

The script cleans up on normal completion and `Ctrl-C`. Every created resource has `Project=FortiAIGate`, `Purpose=temporary-ec2-capacity-probe`, a `RunId`, and an `ExpiresAt` tag. If an interruption such as a forced process kill prevents cleanup, use the `RunId` from the ignored JSON report to locate and remove the remaining EC2 instances, subnets, security group, and VPC.
