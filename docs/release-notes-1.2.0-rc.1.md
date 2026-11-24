# v1.2.0-rc.1 — FortiAIGate 8.0.2 demo

This is a release candidate for project version 1.2.0, targeting FortiAIGate
8.0.2. It is intended for peer testing. The 8.0.1 release remains available
under `v1.0_faig8.0.1` and the `archive/8.0.1` branch.

## Scope

The tested path provisions one AWS GPU host with k3s, FAIG, LiteLLM, MCP
and the shared instructor/student interface. Quickstart can initialize the
FAIG administrator, upload a license, configure the direct LiteLLM provider
and verify a governed request. This initialization uses GUI-observed FAIG APIs;
Fortinet does not support this automation and a product change may break it.
Students use individual workspaces and can exercise the catalog scenarios.

An Ohio `g6.4xlarge` deployment at commit `7a53f3e` was validated with
existing ECR images and the NVIDIA package cache. Quickstart was resumed with
`--skip-terraform` after its EC2 health-check wait was interrupted. The license,
scanning and governed pass-model smoke test passed. All three scenario models
and two fully prepopulated student workspaces were created; both students
signed in. Catalog tests produced eight passes and the known Resume Block
failure below. The code suite passed 343 tests (16 skipped). Teardown removes
the lab host, networking, IAM, Elastic IPs and disposable prep buckets; ECR and
the separately managed NVIDIA package caches are retained. After the Ohio test,
teardown exited successfully and AWS inventory confirmed the host, lab VPC,
EIP and lab IAM role were gone while the Ohio ECR repositories and both regional
NVIDIA caches remained.

## Known limitations

- Resume tool injection's Block test is a known failure: FAIG blocks before
  `document_read` executes, so the test cannot verify the intended tool result.
- External Terraform state was exercised on a fresh deployment. Migration
  of existing state and recovery across environments remain unvalidated.
- Static instructor and student password files have unit coverage but have not
  been validated live. Use generated credentials for the default deployment.
- HTTPS uses a lab certificate. Browser trust and credentials must be handled
  as described in the instructor guide.
- Terraform state and backups contain generated credentials in plaintext;
  protect local state and private backups as described in
  [Lab Secrets and State](lab-secrets-and-state.md).
- Auto-approval approves all pending FAIG changes while enabled. The non-GPU
  mode and the separate FAIG re-entry provider are deferred.
- Syslog bucket export and teardown of buckets containing objects or older
  object versions have automated coverage but have not been validated live.
- FortiGate and FortiWeb appliance deployment logic is carried forward from
  8.0.1 (with Terraform backend wiring changes). It has not been validated for
  this 8.0.2 release; appliance testing is deferred to v1.2.1.
- ECR maintenance, including lifecycle policies and image deletion, is
  separate from normal deployment and teardown. Existing images are retained.

Start with [Quickstart](quickstart-802.md), then the
[Instructor Guide](instructor-guide-802.md) and [Student Guide](student-guide-802.md).
Peer testers should record the checkout and environment, any manual steps,
failures and unclear instructions. Do not include passwords or license contents
in feedback.

The current backlog is targeted at v1.2.1, including external-state rollout,
ECR cross-region/manifest and lifecycle work, and consolidated lab profiles.
