# FortiAIGate Syslog Preservation Plan

Phase 8 scenario testing should preserve FortiAIGate logs before teardown.
FortiAIGate syslog output is assumed to use UDP/514, so the collector design
must support that port.

## Recommended Design

```text
FortiAIGate syslog UDP/514
  -> k3s syslog collector service
      -> Vector, Fluent Bit, or syslog-ng pod
          -> S3 log archive bucket
```

UDP/514 is workable. A Kubernetes Service can expose UDP/514 while the
container listens on a higher unprivileged target port. If FortiAIGate must
send to the k3s node IP on UDP/514, use one of these patterns:

- collector pod with `hostNetwork: true` binding UDP/514
- host-level redirect from UDP/514 to a collector NodePort
- `hostPort` or load-balancer style exposure if cleaner for the lab

For the first implementation, prefer the simplest reliable lab design:
a single collector pod with `hostNetwork: true`, documented security context,
and S3 upload.

## AWS Prep

Add a separate S3 bucket in `terraform/aws-prep` for FortiAIGate log archives.
It should be distinct from document fixture storage.

Required protections:

- S3 block public access
- private bucket ownership controls
- default encryption
- lifecycle expiration
- least-privilege write access for the k3s host or collector

Suggested prefix:

```text
s3://<bucket>/fortiaigate/syslog/<deployment-id>/YYYY/MM/DD/
```

## Teardown

Automated teardown should check the log bucket before destroying AWS prep
resources and offer to export logs to:

```text
/Users/mbutterfield/code/FAIG/backups/
```

Default behavior should not silently discard logs. For unattended teardown,
either export automatically or require an explicit discard option.

## Security

Treat logs as sensitive. They may include prompts, responses, synthetic PII,
policy actions, internal URLs, and model/provider errors. Do not commit raw
logs to the repo. Create sanitized summaries under `docs/` only when needed.
