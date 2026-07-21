# FortiAIGate Syslog Preservation

Phase 8 scenario testing should preserve FortiAIGate logs before teardown.
FortiAIGate syslog output is assumed to use UDP/514, so the collector design
must support that port.

## Implemented Design

```text
FortiAIGate syslog UDP/514
  -> k3s ClusterIP service on UDP/514
      -> Fluent Bit pod on UDP/5514
          -> S3 log archive bucket
```

UDP/514 is workable. A Kubernetes Service can expose UDP/514 while the
container listens on a higher unprivileged target port.

The collector is deployed by:

```bash
ansible-playbook ansible/playbooks/deploy_fortiaigate_syslog_collector.yml
ansible-playbook ansible/playbooks/status_fortiaigate_syslog_collector.yml
```

The quickstart invokes the collector playbook automatically. The role no-ops
unless `terraform/aws-prep` created `fortiaigate_syslog_bucket_name` and
`terraform/aws-ec2-k3s` regenerated `ansible/group_vars/terraform.generated.yml`.

Configure FortiAIGate syslog to target the status output:

```text
fortiaigate-syslog.fortiaigate-logging.svc.cluster.local:514/udp
```

If FortiAIGate cannot resolve the service DNS name, use the service ClusterIP
shown by the status playbook. If FortiAIGate must send to the k3s node IP on
UDP/514 instead of an internal service IP, future options are `hostNetwork`,
`hostPort`, or a host-level UDP redirect.

## AWS Prep

`terraform/aws-prep` can create a separate S3 bucket for FortiAIGate log
archives. It is distinct from document fixture storage.

Enable it with:

```hcl
fortiaigate_syslog_bucket_enabled = true
fortiaigate_syslog_prefix         = "fortiaigate/syslog"
```

Required protections:

- S3 block public access
- bucket-owner-enforced object ownership
- default encryption
- lifecycle expiration
- least-privilege write access for the k3s host or collector

Suggested prefix:

```text
s3://<bucket>/fortiaigate/syslog/YYYY/MM/DD/HH/
```

## Teardown

Automated teardown should check the log bucket before destroying AWS prep
resources, offer to export logs to:

```text
/Users/mbutterfield/code/FAIG/backups/
```

The teardown script exports logs when approved, then empties the dedicated
bucket so Terraform can destroy it:

```bash
python3 scripts/automated_teardown.py
```

Useful options:

```bash
python3 scripts/automated_teardown.py --skip-appliances
python3 scripts/automated_teardown.py --skip-syslog-export
python3 scripts/automated_teardown.py --syslog-export-dir ../backups
```

For tonight's syslog-only test path, keep FortiGate/FortiWeb appliance modules
skipped and enable only the syslog bucket in `terraform/aws-prep`.

## Test

After deployment, send a synthetic UDP syslog message through the service and
check collector logs plus S3 listing:

```bash
ansible-playbook ansible/playbooks/test_fortiaigate_syslog_collector.yml
```

## Security

Treat logs as sensitive. They may include prompts, responses, synthetic PII,
policy actions, internal URLs, and model/provider errors. Do not commit raw
logs to the repo. Create sanitized summaries under `docs/` only when needed.
