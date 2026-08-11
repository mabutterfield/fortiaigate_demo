# Python Scripts

Run documented commands from the repository root. The files remain together in
`scripts/` so the deployment playbooks and Python imports have one stable path,
but they are grouped below by who normally invokes them.

## User-executed workflow scripts

These are the primary commands used to prepare, deploy, manage, and remove a
demo environment.

- `automated_quickstart.py` — guides the AWS or local deployment workflow. It
  initializes or imports the user profile when needed, runs the applicable
  Terraform stages, and invokes the Ansible deployment. Use
  `python3 scripts/automated_quickstart.py` for AWS or add `--local` for an
  existing local Ubuntu GPU host.
- `automated_teardown.py` — guides repeat AWS teardown in dependency order. It
  can preserve FortiAIGate syslog data and avoids deleting retained ECR image
  repositories. Review its plan before approving destructive actions.
- `local_setup.py` — collects local deployment settings and generates the
  ignored local inventory and variable files. It describes existing local
  infrastructure; it does not provision the host.
- `user_profile.py` — initializes, checks, exports, or imports user-owned
  configuration. The quickstart runs profile initialization automatically when
  required. AWS initialization also records the selected k3s GPU instance size
  in the ignored EC2 module override. Direct use is useful for pre-staging
  configuration or transferring a profile between checkouts.
- `scenario_profiles.py` — lists, validates, installs, updates, backs up, and
  removes scenario packages. It also previews the installed scenario matrix and
  renders the FortiAIGate GUI work order.

The supported scenario validation commands live in the `functional_test/`
package rather than `scripts/`:

```bash
python3 -m functional_test validate
python3 -m functional_test render-curl --help
```

See `docs/functional-validation.md` for their expected scope and results.

## Optional operator and troubleshooting scripts

These commands are user-executable, but they are not part of the normal
quickstart path.

- `export_fortiaigate_syslog.py` — downloads FortiAIGate syslog objects from
  the configured S3 archive and reconstructs a combined JSON Lines log plus a
  manifest. The guided teardown can also preserve syslog automatically.
- `fortigate_ai_app_proxy_touch.py` — generates controlled AI application,
  MCP, or Bedrock traffic for FortiGate Application Control investigation. It
  defaults to dry-run and sends traffic only with `--execute`.
- `local_var_cleanup.py` — exports or restores ignored, generated local
  inventory and variable files without uninstalling workloads or changing
  Terraform state. Its archive may contain secrets and must be protected.

## Supporting scripts called by automation

These files are implementation details used by Ansible roles or by the
user-facing scripts. Users normally should not invoke them directly.

- `bedrock_direct_test.py` — sends a signed Bedrock Converse request for the
  `model_direct_test` Ansible role. Direct invocation is documented only for
  Bedrock troubleshooting.
- `build_scenario_matrix.py` — converts installed scenario metadata into the
  deterministic LiteLLM/chatbot/MCP matrix consumed by deployment roles. Its
  command-line output is also useful for advanced dry-run inspection.
- `fortiaigate_chat_test.py` — sends the canonical `pass-model` request through
  `/v1/passthrough/chat/completions` for the `fortiaigate_chat_test` Ansible
  role.
- `scenario_local.py` — library for ignored, operator-owned scenario packages,
  installed state, backups, and safe local file handling. It is imported by
  scenario management, functional testing, and profile export/import.
- `scenario_matrix.py` — library that validates installed metadata and builds
  deterministic runtime objects. It is imported by the matrix builder,
  scenario manager, functional tests, and load generator.

The Helm post-renderer at `k8s-overlays/bin/post_render_fortiaigate.py` and the
deployed chatbot probe at `chatbot/app/agent_probe.py` are also automation-only
Python components, but live beside the artifacts that consume them.

## Developer and release scripts

These checks are for repository maintenance and release validation. They are
not steps in the end-user quickstart.

- `docs_quality.py` — validates current Markdown links, filenames, and release
  vocabulary.
- `smoke_test.py` — performs no-apply repository checks: Python compilation,
  Terraform formatting, inventory links, tracked-secret safeguards, retired
  runtime residue checks, unit tests, and Ansible syntax validation.

Developer-only dashboard workload generation lives in `load_test/`. Its public
entry point is `python3 -m load_test paths|run`; see
`docs/development/load-testing.md`.

FortiAIGate image publishing is handled by
`ansible/playbooks/publish_images.yml`, not by a Python script.
