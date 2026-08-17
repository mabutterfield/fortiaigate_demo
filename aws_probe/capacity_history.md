# EC2 Capacity Probe History

Point-in-time results written by `capacity_probe.py`. A `capacity_available` result means `RunInstances` accepted a short-lived On-Demand request; it is not a reservation and can change at any time.

By default, the probe skips a recorded AZ/type pair for seven days. Use `--refresh` to force a new allocation attempt, or `--cache-days` to choose a different freshness window.

| Instance type | Region | Availability Zone | Zone ID | Last status | Last checked (UTC) | Detail |
| --- | --- | --- | --- | --- | --- | --- |
| g5.8xlarge | us-east-1 | us-east-1a | use1-az6 | capacity_unavailable | 2026-08-17T21:08:51Z | AWS returned InsufficientInstanceCapacity. |
| g5.8xlarge | us-east-1 | us-east-1b | use1-az1 | capacity_unavailable | 2026-08-17T21:08:51Z | AWS returned InsufficientInstanceCapacity. |
| g5.8xlarge | us-east-1 | us-east-1c | use1-az2 | capacity_available | 2026-08-17T21:08:51Z | RunInstances accepted. |
| g5.8xlarge | us-east-1 | us-east-1d | use1-az4 | capacity_available | 2026-08-17T21:08:51Z | RunInstances accepted. |
| g5.8xlarge | us-east-1 | us-east-1f | use1-az5 | capacity_unavailable | 2026-08-17T21:08:51Z | AWS returned InsufficientInstanceCapacity. |
| g5.8xlarge | us-east-2 | us-east-2a | use2-az1 | capacity_available | 2026-08-17T21:08:51Z | RunInstances accepted. |
| g5.8xlarge | us-east-2 | us-east-2b | use2-az2 | capacity_available | 2026-08-17T21:08:51Z | RunInstances accepted. |
| g5.8xlarge | us-east-2 | us-east-2c | use2-az3 | capacity_available | 2026-08-17T21:10:25Z | RunInstances accepted; termination confirmed. |
| g6.8xlarge | us-east-1 | us-east-1a | use1-az6 | capacity_unavailable | 2026-08-17T21:08:51Z | AWS returned InsufficientInstanceCapacity. |
| g6.8xlarge | us-east-1 | us-east-1b | use1-az1 | capacity_unavailable | 2026-08-17T21:08:51Z | AWS returned InsufficientInstanceCapacity. |
| g6.8xlarge | us-east-1 | us-east-1c | use1-az2 | capacity_unavailable | 2026-08-17T21:08:51Z | AWS returned InsufficientInstanceCapacity. |
| g6.8xlarge | us-east-1 | us-east-1d | use1-az4 | capacity_unavailable | 2026-08-17T21:08:51Z | AWS returned InsufficientInstanceCapacity. |
| g6.8xlarge | us-east-1 | us-east-1f | use1-az5 | capacity_unavailable | 2026-08-17T21:08:51Z | AWS returned InsufficientInstanceCapacity. |
| g6.8xlarge | us-east-2 | us-east-2a | use2-az1 | capacity_unavailable | 2026-08-17T21:08:51Z | AWS returned InsufficientInstanceCapacity. |
| g6.8xlarge | us-east-2 | us-east-2b | use2-az2 | capacity_available | 2026-08-17T21:08:51Z | RunInstances accepted. |
| g6.8xlarge | us-east-2 | us-east-2c | use2-az3 | capacity_available | 2026-08-17T21:08:51Z | RunInstances accepted. |
