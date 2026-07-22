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

Current FortiAIGate builds accept an IP address, not an FQDN, for this syslog
target. Configure FortiAIGate syslog to target the service ClusterIP shown by
the status output:

```text
10.70.38.54:514/udp
```

The collector role supports reserving that ClusterIP with:

```yaml
fortiaigate_syslog_service_cluster_ip: "10.70.38.54"
```

The service FQDN is still useful for in-cluster diagnostics, but should not be
used in the FortiAIGate GUI unless that UI later supports FQDN targets:

```text
fortiaigate-syslog.fortiaigate-logging.svc.cluster.local:514/udp
```

If FortiAIGate must send to the k3s node IP on UDP/514 instead of an internal
service IP, future options are `hostNetwork`, `hostPort`, or a host-level UDP
redirect.

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

## Archive Export

Syslog files are for archive preservation, not live demo viewing. The collector
uses a five-minute S3 upload timeout by default, so low-volume environments
will produce small gzip objects periodically. Reconstruct them from a local
backup with:

```bash
scripts/export_fortiaigate_syslog.py --label phase8-syslog-current
```

The script first syncs S3 objects to:

```text
/Users/mbutterfield/code/FAIG/backups/<label>/raw/
```

Then it writes:

```text
/Users/mbutterfield/code/FAIG/backups/<label>/fortiaigate-syslog-combined.jsonl
/Users/mbutterfield/code/FAIG/backups/<label>/manifest.json
```

To reconstruct from an existing backup without re-syncing:

```bash
scripts/export_fortiaigate_syslog.py \
  --skip-sync \
  --download-dir ../backups/phase8-syslog-current/raw
```

Pretty-print the reconstructed JSONL with `jq`:

```bash
LOG_FILE="../backups/phase8-syslog-current/fortiaigate-syslog-combined.jsonl"

jq -r '
  . as $r
  | ($r.message | capture("^<(?<pri>[0-9]+)>(?<body>.*)$")) as $m
  | "---\nreceived=\($r.date) deployment=\($r.deployment_id) pri=\($m.pri)\n  \($m.body | gsub(" (?=[A-Za-z_][A-Za-z0-9_]*=)"; "\n  "))"
' "$LOG_FILE"
```

The same formatter can be used in a pipeline:

```bash
cat "$LOG_FILE" | jq -r '
  . as $r
  | ($r.message | capture("^<(?<pri>[0-9]+)>(?<body>.*)$")) as $m
  | "---\nreceived=\($r.date) deployment=\($r.deployment_id) pri=\($m.pri)\n  \($m.body | gsub(" (?=[A-Za-z_][A-Za-z0-9_]*=)"; "\n  "))"
'
```

This is a readability formatter rather than a full parser. It preserves the
original `message` content and inserts line breaks before `key=value` fields.

## Teardown

Automated teardown checks the log bucket before destroying AWS prep resources
and offers to export logs to:

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
