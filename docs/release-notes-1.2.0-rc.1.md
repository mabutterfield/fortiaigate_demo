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

A fresh Ohio deployment was tested with generated credentials and local
Terraform state. The instructor and two students signed in, prepopulated
scenarios were exercised, FAIG scanning was active, and an unchanged Terraform
plan was confirmed. Teardown removed the host, VPC and EIP and cleaned the
instance credentials. It retained the shared prep IAM resources, ECR and S3.
The integrated automated suite passed 403 tests with 16 skipped before this
release documentation and backend-backup change; rerun it on the final tag.

## Known limitations

- Resume tool injection's Block test is a known failure: FAIG blocks before
  `document_read` executes, so the test cannot verify the intended tool result.
- External Terraform state migration and re-import are not validated against
  the real environment; use the tested local-state path for this RC.
- Static instructor and student password files have unit coverage but have not
  been live-tested in the fresh deployment. Use generated passwords for the RC.
- HTTPS uses a lab certificate. Browser trust and credentials must be handled
  as described in the instructor guide.
- Terraform state and backups contain generated credentials in plaintext;
  protect local state and private backups as described in
  [Lab Secrets and State](lab-secrets-and-state.md).
- Auto-approval approves all pending FAIG changes while enabled. The non-GPU
  mode and the separate FAIG re-entry provider are deferred.
- ECR maintenance, including lifecycle policies and image deletion, is
  separate from normal deployment and teardown. Existing images are retained.

Start with [Quickstart](quickstart-802.md), then the
[Instructor Guide](instructor-guide-802.md) and [Student Guide](student-guide-802.md).
Peer testers should record the checkout and environment, any manual steps,
failures and unclear instructions. Do not include passwords or license contents
in feedback.

The current backlog is targeted at v1.2.1, including external-state rollout,
ECR cross-region/manifest and lifecycle work, and consolidated lab profiles.
