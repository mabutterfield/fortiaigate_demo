# Changelog

This file summarizes major user-facing changes. It is intentionally written as
a "what's new" guide rather than a raw commit log.

## Unreleased

- Established the v1.0 documentation entry points and support vocabulary:
  - rebuilt the repository and documentation landing pages around AWS/local
    deployment choices and operator tasks rather than numbered phases or demo
    slots
  - documented Direct, FAIG protected, passthrough, FortiWeb MCP, optional
    FortiGate, and opt-in FAIG re-entry request paths in one architecture view
  - moved the authoritative baseline into `docs/reference/` and classified
    defaults, optional components, configurable behavior, and deferred paths
  - made the scenario catalog the sole scenario-status authority and kept the
    repository landing page focused on deployment choices
  - added a concise, non-committal Future Direction section for AMI creation,
    repository separation, FortiFlex, local scenario creation, Demo Home
    documentation, and future scenario/appliance validation

- Updated the local traffic generator for the complete Phase 11 baseline:
  - moved live validation, path checks, traffic generation, result aggregation,
    and tracked high-token prompt metadata into the dedicated `load_test/`
    package with `validate`, `paths`, and `run` commands
  - baseline selection now includes `resume-tool-injection`
  - configurable high-token canonical passthrough traffic supports tunable
    bypass-to-scenario mixes
  - scenario/action lanes receive deterministic minimum coverage
  - summaries now record wall time, throughput, approximate response tokens,
    and canonical provider-route counts for sequential/parallel comparison
  - every traffic result is validated against its action expectation, with
    Deny, Redact, sensitive-output, and resume tool-pivot checks summarized as
    expected results over total results for each provider route
  - added machine-readable validation cases to every baseline scenario so live
    setup checks and background traffic share prompts, verdicts, and required or
    forbidden tool traces
  - added a tracked variable 24-hour dashboard workload with a 75/25 long-run
    normal-to-suspicious baseline, bounded hourly volume, and mandatory hourly
    Alert, Deny, and Redact requests
  - added atomic live statistics and checkpoints, graceful signal handling,
    approximate token totals, and isolated NVIDIA utilization, memory, power,
    temperature, and estimated-energy sampling

- Started the Phase 11 scenario-matrix v1.0 foundation:
  - classified FortiStore Injection, HR Tool DLP, and Resume Tool Injection as
    baseline scenarios, while retaining FortiGate Operator as a future
    candidate
  - added a strict scenario profile v2 schema with scenario-owned Alert, Deny,
    and Redact actions, frontend profiles, MCP defaults, and disabled FAIG chain
  - added ignored editable local scenario packages with safe add, status,
    explicit backed-up update, and recoverable remove
  - added a deterministic Phase 3 builder for LiteLLM aliases and instruction
    profiles, chatbot simplified and advanced controls, MCP paths and scoped
    tool profiles, scenario-owned FAIG routes, and the FAIG GUI work order;
  - made matrix generation the default LiteLLM configuration source, resolving
    the environment-neutral `llm-default` target to Bedrock or Ollama during
    deployment and loading backend instructions from ignored local scenarios
  - added direct validation for canonical `pass-model`, `fortistore-injection`,
    and `hr-tool-dlp` aliases, including required scenario activation markers
  - made the consolidated chatbot consume the same scenario matrix for its
    models, FAIG static routes, simplified profiles, scenario/alternate MCP
    tool profiles, and named frontend instruction profiles
  - removed generated `demo-a`/`demo-b` options from the Phase 11 chatbot,
    defaulted the UI to simplified mode, and retained the canonical FAIG
    passthrough plus advanced controls
  - enabled the optional advanced FortiWeb MCP path only when its proxy is
    desired and an installed appliance endpoint is available; FortiGate LLM
    routes remain disabled while that path is still under development
  - published chatbot image `v0.5.2` for the new matrix-driven runtime
  - updated the scenario harness and traffic generator to resolve installed
    scenarios by canonical action, model alias, frontend profile, MCP path,
    scoped tool profile, and tool-round settings from the same matrix
  - updated the in-container agent probe to support MCP-disabled requests and
    named frontend profiles without defaulting to `demo-a` or `all-tools`, and
    published the result as chatbot image `v0.5.3`
  - retained explicit Phase 10 `--paths`, `--route`, and active-slot modes for
    old test invocations without using them as Phase 11 defaults
  - rewrote the scenario operator, authoring, catalog, active-scenario, and
    FortiAIGate GUI guides around generated scenario-owned paths, named
    profiles, editable local installs, and reusable `{{variable}}` flow setup
  - made rendered FAIG work orders show copy-safe configured URIs with the
    required trailing `/*` instead of only the bare request prefix
  - removed the unvalidated HR Tool DLP `input-dlp` flow and chatbot profile;
    input DLP remains available to a future dedicated scenario or revision
  - standardized scenario routes as `/v1/<scenario>/<action>/*` with Alert,
    Deny, and Redact actions; aligned flow names, guard names, chatbot profiles,
    harness/traffic options, and work orders to the same contract
  - removed stale-FAIG-object bookkeeping and `ack-stale`; disposable lab
    rebuilds or direct GUI changes now own appliance cleanup
  - consolidated the five experimental resume packages into the simulated
    `resume-tool-injection` baseline, with scenario-owned Alert and Deny paths,
    a poisoned `RESUME-9001` fixture, and no real uploads or cloud access
  - added per-chatbot-profile MCP tool-set selection so simplified resume
    profiles can demonstrate the synthetic cloud-tool pivot while Advanced
    mode retains a least-privilege comparison without the cloud tool
  - archived the superseded resume packages, taught the scenario harness to
    classify an executed cloud-tool pivot from the actual tool trace, and
    published the chatbot profile cleanup as image `v0.5.4`
  - validated the Resume Tool Injection Direct, Alert, Deny, clean, and
    least-privilege cases on Jarvis; strengthened the synthetic `RESUME-9001`
    injection signature so Deny reliably stops the agent after document read
    and before the synthetic cloud tool executes
  - added a trace-based Resume Tool Injection acceptance matrix, deterministic
    fixture/profile regression tests, canonical curl replay paths, and updated
    baseline, scenario, FAIG setup, and release-validation documentation
- Re-scoped Phase 10 documentation as the final pre-Phase-11 cleanup:
  - Phase 11 is now planned as the v1.0 baseline for scenario-owned paths,
    generated scenario metadata, and the replacement for `demo-a`/`demo-b`
    terminology
  - active scenario examples now keep FortiStore Injection and HR Tool DLP,
    while FortiGate Operator and the HR Resume family are marked as Phase 11
    candidates
  - legacy or paused scenarios were moved to `archived_scenarios/` while
    remaining inspectable through inactive catalog entries
- Added and archived an MCP-backed FortiStore Product Advisor scenario used
  during Phase 10 prompt-injection and token-wasting tuning:
  - uses deterministic synthetic product catalog data through narrow MCP tools
    instead of external product docs or RAG
  - documents Direct, Demo A detect-only, and Demo B input-protection behavior
    with route, flow, guard, and model expectations
  - marks the older fast-food ordering and MCP-backed FortiStore scenarios as
    archived/unused for the Phase 10 active set
- Added FortiStore Injection as the active Phase 10 product-advisor injection lane:
  - keeps normal backend-only behavior product-focused
  - adds a toggleable chatbot frontend/system-prompt fixture for demonstrating
    compromised UI-layer instruction injection
  - packages the local frontend instruction slot by default when present, with
    the chatbot UI checkbox starting off for backend-only behavior
  - supports headless validation with frontend instructions enabled or disabled
- Added Phase 10E FortiGate traffic-demo preparation:
  - documented outbound AI application detection from a VM behind FortiGate and
    inbound inspection through `http://<fgt-ip>:4000/v1` for LiteLLM and
    `https://<fgt-ip>/v1/...` for FortiAIGate
  - added a dry-run-by-default app-touch helper that sends direct/no-proxy
    traffic by default, can use a run-scoped explicit proxy URL when requested,
    uses FortiGuard-style GenAI target labels, avoids GET range requests by
    default, and does not alter workstation proxy settings
  - added an opt-in chatbot and traffic-generator path for
    `chatbot -> FortiGate :4000 -> LiteLLM` plain HTTP inspection
  - added disabled-by-default FortiGate role variables that can generate the
    listener custom services, VIP objects, and inbound firewall policies for
    the LiteLLM and FortiAIGate inspection paths
  - added FortiGate static-route management and default SNAT for the optional
    AI inspection VIP policies so the path is more suitable for AWS k3s
    NodePort forwarding
- Started Phase 10 release hardening:
  - aligned README and documentation entry points around the v1.0 support
    contract
  - documented AWS quickstart as the primary supported path and local Ubuntu
    Ollama mode as a supported lab path
  - centralized known issues and workarounds for slow NVIDIA downloads,
    FortiAIGate GUI setup, FortiWeb MCP Security automation, and local Ollama
    NodePort exposure
  - marked the Phase 10 scenario set for validation and demo rehearsal while
    deferring final v1.0 scenario naming to Phase 11
- Added the Phase 10 release validation matrix covering no-apply checks, AWS
  fresh deployment, AWS teardown, local fresh deployment, scenario baseline
  validation, and an optional FortiGate Application Control traffic-generation
  investigation.
- Improved release smoke-test ergonomics:
  - quickstart now defaults to continuing into Ansible image publishing and
    deployment after Terraform confirmation
  - image publishing prompts now warn that FortiAIGate/all publishing can take
    significant time and show a best-effort ECR tag preflight
  - release validation docs now remind maintainers to bump or explicitly
    confirm `chatbot_image_tag` for branch-version releases
- Added `scripts/traffic_generator.py` for Phase 10 local-safe traffic:
  - default `path_test` mode that prints the inferred FAIG target and curls
    `/v1/demo-a`, `/v1/demo-b`, and `/v1/passthrough` once from the workstation
  - `steady` mode for persistent low-rate log/dashboard population
  - `burst` mode for short high-rate load or DoS-style testing
  - `--mode traffic` FAIG scan routing and active-slot scenario selection so sent
    prompts match the scenario installed into `demo-a`/`demo-b`
  - FAIG protect traffic now uses the `demo-b` entry point while keeping the
    active scenario and backend LiteLLM model aligned to `demo-a`
  - fixed-seed scenario traffic plans, compact ignored metadata, and
    cloud/long-run safeguards
  - blocked/redacted protected responses are counted as security dispositions
    rather than request failures
- Fixed `test_mcp.yml` local mode by adding an auto target mode that tests the
  MCP NodePort from the local k3s host instead of requiring AWS Terraform
  public-IP output.
- Hardened local Ollama model validation:
  - local direct model tests now force Ollama and skip all Bedrock Terraform
    output and credential checks when the local inventory or
    `FAIG_DEPLOYMENT_TARGET=local` is used
  - local Ollama defaults now prefer `gpt-oss:20b`, keep the loaded model warm
    for 60 minutes, and set a 32768-token context length
  - direct local model tests print the loaded `ollama ps` table after the
    request so operators can confirm model, GPU placement, context, and unload
    timing
- Enabled local FortiAIGate syslog collection without AWS prep:
  - AWS deployments keep the existing Fluent Bit S3 archive output
  - local deployments can use file output inside the collector pod at
    `/logs/fortiaigate-syslog.jsonl`
  - status and test playbooks now show/tail the local syslog file and validate
    that synthetic UDP syslog messages are captured
- Aligned Phase 10 scenario routing around stable FAIG flows:
  - the default chatbot route surface remains passthrough, demo-a, and demo-b
    for the supported quickstart path
  - demo-c and demo-d are now documented as opt-in Phase 10 scenario routes
    that can be exposed with `chatbot_phase10_scenario_routes_enabled: true`;
    any shared backend mapping stays in the FAIG guard configuration
  - FortiWeb MCP path selection now has a derived local/AWS base URL when the
    FortiWeb proxy and front-end IP are present
  - scenario docs now use `detect_all`, `protect_input`,
    `protect_output_dlp`, and `protect_input_dlp`
  - the HR Tool DLP profile now exposes safe employee search/lookup tools plus
    the individual sensitive lookup tool for context-dependent output-DLP tests
  - the HR Tool DLP scenario now documents the full demo-a through demo-d
    walkthrough, including safe table, single sensitive record, and
    multi-record context prompts with expected DLP behavior
  - added a scenario-local detailed walkthrough for HR Tool DLP and linked it
    from the base scenario runbook; the latest demo-c single-employee rerun
    documents successful DOB/card placeholder redaction
  - added the `employee_table_with_cc` MCP tool for a one-call bulk HR DLP
    comparison against the earlier five-tool-loop table that redacted DOB but
    missed multiple credit card numbers in Demo C

## v0.9.0 - Local Deployment Support

Release date: 2026-07-29

- Added Phase 9 local hardware deployment foundations:
  - `scripts/local_setup.py` generates ignored local inventory, registry, host,
    appliance, GPU, and Ollama variables without changing the default AWS path
  - `automated_quickstart.py --local` skips Terraform and uses the generated
    local inventory
  - Ollama can deploy in k3s with model preloading, optional GPU UUID pinning,
    and a plain HTTP NodePort for trusted local-lab access
  - NVIDIA driver bootstrap now supports local branch switching and validates
    selected GPU UUID visibility
  - FortiAIGate Triton can be pinned to the selected FAIG GPU UUID so mixed
    legacy/current GPU hosts avoid unsupported TensorRT placements
  - local FortiGate/FortiWeb onboarding now creates managed `apiadmin`
    credentials during `local_setup.py` and stores only those managed
    credentials in ignored local secrets
- Added scenario-scoped MCP tool profiles:
  - chatbot UI and `agent_probe.py` can expose only the MCP tools needed for
    the selected scenario
  - scenario profiles now declare `mcp.tool_profile`, and the scenario test
    harness defaults to that profile
  - added `support-ticket-triage` to cover customer, ticket, and generic policy
    MCP tools without mixing them into HR, resume, menu, or FortiGate demos
  - documented when LiteLLM, chatbot, and MCP redeploys are required for
    scenario edits
- Added curl replay payloads for each tracked scenario so FortiAIGate and
  LiteLLM can be tested with spoofed MCP-like tool transcripts without running
  the chatbot agent or MCP server.
- Updated the HR MCP/DLP demo:
  - promoted the working HR Bot with MCP `demo-a` instructions into the
    tracked instruction examples
  - replaced the employee fixture set with five simulated dlptest.com-sourced
    records containing DOB, email, SSN, credit-card, salary, and source fields
  - kept normal employee lookup/search tools returning safe metadata while the
    explicit sensitive lookup demo tool returns full simulated records
  - refreshed the HR tool-DLP scenario prompt, reference matrix, and test
    harness sensitive-data matching for the new fixture shape
- Suspended versioning on the optional FortiAIGate syslog S3 bucket so exported
  demo logs do not leave noncurrent object versions/delete markers that block
  Terraform teardown.
- Added Phase 8 document-ingestion demo foundations:
  - tracked synthetic document fixtures for clean resume/policy retrieval and
    opt-in poisoned document tests
  - read-only MCP document and resume tools with explicit `include_attack`
    handling for attack fixtures
  - a simulated upload tool that reports pre-staged fixture availability
    without faking exploit success
  - a narrow synthetic cloud bucket inventory tool for prompt-injection
    tool-pivot demos
  - scenario profiles for clean resume screening, resume prompt injection,
    resume cloud-tool pivot, HR policy RAG risk, and menu poisoning
- Added natural safe/vulnerable resume cloud-tool pivot scenario profiles so
  demos can start from normal uploaded-resume screening prompts while still
  using deterministic poisoned fixtures behind the scenes.
- Added optional chatbot/FAIG lite mode and `test_fortiaigate_lite.yml` for a
  minimal static route surface: passthrough, demo-a, and demo-b.
- Added a chatbot in-container `agent_probe.py` helper for headless validation
  of the same MCP agent loop used by the Streamlit UI.
- Added compact `agent_probe.py --summary` output for repeatable headless
  scenario sweeps with short reply excerpts, tool sequences, and key tool
  result fields.
- Hardened chatbot MCP dispatch against model-emitted tool names with stray
  channel or suffix markers.
- Updated MCP status output to report the live `/tools` catalog instead of the
  older hardcoded baseline tool list.
- Added `validate_phase8_documents.yml` for deterministic live checks of the
  Phase 8 MCP document, upload-simulation, prompt-injection, and synthetic
  cloud-inventory tools.
- Added a Phase 8 reference matrix for OWASP LLM/MCP/ASI mapping, route
  comparison, model behavior, expected prompts, raw-output conventions, and
  policy-tuning observations.
- Added `scripts/scenario_test_harness.py` for repeatable chatbot/MCP scenario
  sweeps through Direct LiteLLM, FAIG scan, and FAIG protect paths, with
  run-label safeguards and ignored raw JSON output under `docs/raw-output/`.
- Added FortiAIGate syslog preservation:
  - optional dedicated S3 archive bucket in `terraform/aws-prep`
  - Fluent Bit collector on UDP/514 via a k3s service
  - deploy, status, and test playbooks for the collector
  - automated teardown export support before bucket destruction
  - `scripts/export_fortiaigate_syslog.py` to sync gzip objects and reconstruct
    a combined JSONL archive
- Tightened Phase 8 prompt-injection demo behavior:
  - MCP document injection checks now flag role/constraint override language
    and safety-check bypass wording used by the menu poisoning fixture
  - menu poisoning instructions require a real MCP injection check after
    reading attack fixture documents
  - fast-food ordering instructions now refuse attempts to bypass allergies or
    dietary restrictions before recommending an unsafe item
- Improved chatbot MCP trace handling for tool-heavy demos:
  - MCP tool errors now remain visible as tool results instead of becoming
    generic HTTP failures
  - tool trace entries default collapsed and render in a fixed-height
    right-side pane to avoid long tool results driving page scroll
- Added Bedrock model comparison coverage for Phase 8 demo testing across
  GPT-OSS 20B, GPT-OSS 120B, Gemma 3 4B, and Ministral 3B. GPT-OSS models
  support the current chatbot MCP tool-calling path; Gemma and Ministral
  currently preserve useful unsupported-tool-call/provider error traces.
- Added FortiFlex token bootstrap support for optional FortiGate and FortiWeb
  Terraform modules while keeping BYOL license files as the default path.
- Hardened FortiWeb rebuild/configuration behavior by supporting a generated
  initial admin password, fixing the FortiWeb admin timeout bootstrap command,
  disabling FortiWeb password-policy enforcement during cloud-init bootstrap,
  and keeping the risky full-object admin-user Ansible update disabled by
  default.
- Moved FortiWeb HTTPAPI persistent connection sockets under `/tmp` and reset
  them around FortiWeb status/configuration playbooks to reduce stale local
  socket failures across rebuilds.
- Added Phase 7 MCP tool expansion:
  - deterministic fast-food menu/order tools for non-Fortinet tool-use demos
  - read-only FortiGate MCP tool schemas for status, interfaces, routes,
    firewall policies, address objects, and service objects
  - graceful disabled/error responses when FortiGate credentials are absent
- Added MCP FortiGate secret wiring so the MCP deployment can read the
  Phase 6 read-only FortiGate API account token from a Kubernetes Secret
  without exposing it through chatbot configuration.
- Moved mutable chatbot/LiteLLM instruction prompts out of tracked active
  paths. Tracked examples now live under `chatbot/instructions/examples/`,
  while active `demo-a`, `demo-b`, and `frontend` instruction slots live under
  ignored `chatbot/instructions/local/`.
- Added `scripts/instruction_profiles.py` with both CLI commands and a
  menu-driven wizard for installing tracked examples or local instruction files
  into one active slot at a time. The helper prints the relevant Ansible deploy
  command after preparing a slot.
- Updated user profile and automated quickstart setup to initialize missing
  local instruction slots alongside Terraform and Ansible user variables.
- Updated MCP, architecture, quickstart, deployment, and flow documentation for
  Phase 7: Bedrock requests tools and produces final answers, LiteLLM remains
  the proxy/auth/instruction-injection layer, and the chatbot/agent owns MCP
  TCP flows.
- Added tracked scenario profiles for repeatable demos:
  `fastfood-ordering`, `fortigate-operator`, and `hr-policy-risk`. The new
  `scripts/scenario_profiles.py` helper installs scenario instructions into
  local slots while keeping instruction profiles available for fine tuning.
- Scenario profiles now use the single shared MCP server only. Their
  `required_tools` lists document expected tool use and are validated against
  the shared MCP catalog.
- Removed scenario-profile recommended slots. Scenario installs now require an
  explicit instruction slot, and instruction-profile status output clarifies
  local source metadata.
- Added a scenario runbook with chatbot settings, sample prompts, attack or
  boundary prompts, and expected behavior for each tracked scenario.
- Added synthetic HR MCP tools and data for employee lookup/search, HR policy
  lookup, and redaction checks.
- Fixed the chatbot MCP final-answer path so Bedrock/LiteLLM receives the tool
  schema when summarizing after the configured maximum tool rounds.
- Added chatbot context controls for current-turn, recent-conversation, and
  consolidated-context modes, including reset and optional context visibility
  for scenario demos.
- Added Kubernetes pod detail lines, including pod `AGE`, to app status
  summaries so redeploy completion is easier to confirm.
- Improved FortiGate MCP troubleshooting: FortiGate API failures now include
  non-secret target URL/detail fields, and `test_mcp.yml` prints 400 responses
  before failing on `ok=false`.
- `deploy_mcp.yml` now restarts the MCP deployment when the FortiGate MCP
  Kubernetes Secret changes, ensuring updated API tokens and admin URLs are
  loaded into the pod environment.
- FortiGate MCP now targets the FortiGate port1 private IP by default instead
  of the public admin URL. Override `mcp_fortigate_base_url` only for a custom
  management destination.
- `deploy_mcp.yml` now validates the saved read-only FortiGate API token before
  writing it into the MCP Kubernetes Secret. When the saved token is stale or
  rejected, the play leaves FortiGate MCP disabled for that deployment and
  prints the rotate-token command.
- FortiGate read-only API token generation now treats a saved token from a
  different FortiGate EC2 instance ID as stale, so quickstart refreshes it
  before MCP is deployed after appliance rebuilds.
- FortiGate MCP system-status responses now include top-level FortiGate fields
  such as version, serial, and build, and the chatbot now sends assistant
  tool-call messages with null content for better Bedrock/LiteLLM compatibility.
- The chatbot now uses a wide layout with MCP tool calls shown in a separate
  right-side trace pane instead of inline inside the assistant response.
- Added `llama3.2:1b` as a default selectable LiteLLM/Ollama backend alias and
  documented commented model preference examples for `llama3.2:1b` and
  Bedrock `gpt-oss:20b`.
- Made `terraform/aws-prep` tolerate missing ECR repository outputs during
  teardown after ECR repositories have been removed from Terraform state.
- Moved automated teardown ECR state protection to the end of teardown so
  `aws-prep` can still read ECR outputs while dependent resources are destroyed.
- Moved optional GitHub SSH public-key import (`ec2_pull_github_keys`) into
  shared `terraform/user.tfvars.example` so it travels with the user profile.

## v0.5.0 - Variable Ownership And Quickstart Stabilization

Release date: 2026-07-16

- Trimmed profile onboarding prompts to user-owned basics: AWS identity/network
  values, SSH key selection, FortiAIGate license, LiteLLM credentials, and
  optional OpenWebUI enablement.
- Direct provider/model overrides, Ollama settings, chatbot prompt source path,
  and TLS certificate paths are now documented as manual advanced settings
  rather than quickstart prompts.
- Commented or neutralized Ollama defaults in tracked Ansible system/user
  examples, role defaults, and OpenWebUI chart values until the Ollama workflow
  is built.
- Quickstart review now optionally pages through profile-owned files only,
  instead of blocking on a broad manual review list.
- Interactive ECR setup now defaults to auto-discovering existing configured
  repositories in AWS and importing only those missing from Terraform state.
- LiteLLM and OpenWebUI Bedrock model selection now tolerate null local model
  overrides and fall back to Terraform outputs or the configured default model.
- Chatbot Helm values rendering now tolerates null optional prompt, ingress,
  image pull secret, and route override values after profile cleanup.
- Hardened OpenWebUI, direct model test, demo output, FortiAIGate, and status
  summaries against null optional values produced by older local profiles.
- Added `scripts/smoke_test.py` for no-apply release checks across Python
  scripts, Terraform formatting, shared variable-file structure, tracked
  local/secret file guards, and Ansible syntax.

## v0.4.3 - User Profile Lifecycle

Release date: 2026-07-16

- Added `scripts/user_profile.py` for explicit local user profile lifecycle:
  `init`, `import`, `export`, and `check`.
- Automated quickstart now checks for required user profile files before
  Terraform or Ansible and offers import/init/exit when they are missing.
- Added quickstart `--init`, `--import`, and `--export` profile options.
- Removed the transitional local config scripts:
  `backup_config.py`, `sync_all_vars.py`, `reconfigure_local_vars.py`, and
  `upgrade_v0_3_to_v0_4.py`.
- Removed automatic broad backup/sync behavior from quickstart and teardown.
  User profile export is now the portable user-owned configuration mechanism.
- Updated docs and legacy Ansible example comments so new deployments point to
  `terraform/user.tfvars`, `ansible/group_vars/user.yml`, and profile
  import/export instead of `env.yml`, `all.yml`, or sync/migration scripts.
- Moved `ssh_private_key_file` into shared `terraform/user.tfvars.example` so
  SSH key name and local private-key path travel together in the user profile.
- Added placeholder `ssh_private_key_file` declarations to modules that load
  shared `50-user.auto.tfvars`, preventing undeclared-variable warnings.
- Kept `bedrock_direct_test.py` and `fortiaigate_chat_test.py` as Ansible
  support smoke-test helpers.

## v0.4.2 - Terraform Variable Ownership Split

Release date: 2026-07-15

- Replaced the copied `terraform/common.tfvars` workflow with ignored
  `terraform/user.tfvars`, created from tracked `terraform/user.tfvars.example`.
- Added tracked `50-user.auto.tfvars` symlinks in each Terraform module so
  shared user values load automatically from `../user.tfvars`.
- Moved module-owned defaults into tracked `00-system.auto.tfvars` files.
- Added tracked `99-local.auto.tfvars.example` files for focused per-module
  local overrides while keeping real `99-local.auto.tfvars` files ignored.
- Updated quickstart, teardown, reconfigure, sync, and migration helpers to use
  the new Terraform variable layout.
- Existing legacy module `terraform.tfvars` files are treated as migration
  input; selected user-owned values are imported into `99-local.auto.tfvars`.

## v0.4.1 - Ansible Variable Ownership Split

Release date: 2026-07-15

- Added tracked `ansible/group_vars/system.yml` for repo-owned Ansible defaults
  such as FortiAIGate versions, image tags, app topology, NodePort-derived
  defaults, and validation settings.
- Added `ansible/group_vars/user.yml.example` as the baseline for ignored
  `ansible/group_vars/user.yml`, which now holds operator-owned values such as
  license selections, LiteLLM credentials, optional model overrides, and local
  paths.
- Updated playbook variable loading so legacy local files are read first for
  compatibility, followed by tracked system defaults, generated Terraform/ECR/
  port vars, and finally `user.yml` overrides.
- Added `ansible/group_vars/terraform.generated.yml`, generated by
  `terraform/aws-ec2-k3s`, to bridge Terraform user and infrastructure settings
  into Ansible without duplicating AWS profile, region, SSH key, CIDR, and k3s
  host values in Ansible local files.
- Updated quickstart, reconfigure, sync, backup, and upgrade helpers to create
  and maintain `user.yml` instead of copying new local `all.yml`, `env.yml`, or
  `images.yml` files.
- Completed in v0.4.3: the transitional migration flow was replaced by explicit
  user profile init/import/export.

## v0.4 - Phase 4 Appliance Baseline

Release date: 2026-07-14

Adds the optional FortiGate and FortiWeb appliance baseline without moving the
default public k3s/FortiAIGate path to a private or appliance-fronted topology.

### FortiGate And FortiWeb

- Added `terraform/aws-fortigate` for optional FortiGate EC2 deployment.
- Added `terraform/aws-fortiweb` for optional FortiWeb EC2 deployment.
- Added two-ENI appliance layouts:
  - public/management ENI
  - internal ENI
- Added prep-owned FortiGate and FortiWeb EIP support.
- Added FortiGate cloud-init bootstrap for management, SSH, admin timeout, and
  API admin token generation.
- Added FortiWeb S3-backed cloud-init bootstrap with generated config and BYOL
  license object upload.
- Set FortiWeb default version filter to `8.0` and default instance type to
  `c5.xlarge` after validating the FortiWeb Marketplace image constraints.
- Confirmed both FortiGate and FortiWeb initial admin password behavior uses
  the EC2 instance ID when an explicit initial password is not set.

### AWS Prep And Network Layout

- Extended `terraform/aws-prep` with optional appliance EIPs.
- Added FortiWeb cloud-init S3 bucket, bucket public-access blocking,
  encryption, versioning, TLS-only bucket policy, and FortiWeb instance-profile
  read access.
- Added FortiGate and FortiWeb public IP outputs.
- Added dedicated FortiGate and FortiWeb internal subnets and route tables in
  `terraform/aws-ec2-k3s`.
- Split the VPC Mermaid diagram into a compact VPC topology diagram and a
  separate AWS prep/module dependency diagram.

### Automated Upgrade And Repeat Runs

- Added `scripts/upgrade_v0_3_to_v0_4.py` for local ignored config migration
  when upgrading an existing `v0.3` lab.
- Automated quickstart now runs the v0.3-to-v0.4 upgrade step before normal
  example/default syncing.
- The upgrade script:
  - moves legacy module-local `ssh_key_name` into `terraform/user.tfvars`
  - comments out old module-local `ssh_key_name` assignments
  - creates missing FortiGate/FortiWeb local tfvars from examples
  - enables appliance prep defaults when local values still reflect the v0.3
    no-appliance baseline
- Automated quickstart now completes all Terraform, including enabled
  FortiGate/FortiWeb modules, before the k3s readiness wait and Ansible.
- Automated quickstart now checks enabled FortiGate/FortiWeb BYOL license file
  paths before Terraform starts, prompts when committed placeholder names are
  still configured, and fails fast in `--yolo` when files are missing.
- Automated teardown now checks AWS caller identity before backup or Terraform
  work and prompts for `aws sso login` or `aws login` when the session is not
  valid.
- Automated teardown now destroys FortiWeb and FortiGate before destroying the
  k3s foundation and AWS prep resources.
- ECR teardown now removes repositories from state and then runs a full ECR
  module destroy for remaining lifecycle/local-output resources, avoiding
  routine Terraform `-target` warnings.
- Security group rule generation now deduplicates overlapping management,
  generated demo, additional, and appliance ingress permissions before AWS
  security group updates.
- `show_demo_outputs.yml` now includes FortiGate and FortiWeb admin URLs plus
  EC2 instance IDs when the appliance Terraform modules have outputs.
- Added `scripts/reconfigure_local_vars.py` as a standalone local
  reconfiguration wizard for important quickstart variables plus any remaining
  local-vs-example top-level differences.
- Changed the current ingress routing default to `port_based`, matching the
  generated NodePort demo URLs. `path_based` remains a future ingress option.
- Split FortiGate and FortiWeb BYOL license settings into source directory and
  file-name variables, while keeping the old full-path variable as a
  compatibility override.

### Shared Terraform Defaults

- Moved `ssh_key_name` into `terraform/user.tfvars` so k3s, FortiGate, and
  FortiWeb use the same AWS EC2 key pair.
- FortiGate and FortiWeb example tfvars are enabled by default for the Phase 4
  project baseline.
- Local private-key path initially remained in
  `terraform/aws-ec2-k3s/99-local.auto.tfvars`; v0.4.3 moved it into shared
  `terraform/user.tfvars`.

### Deferred

- FortiGate private k3s routing/NAT/inspection path.
- FortiWeb-protected MCP or application publishing path.
- Full private `k3s_subnet_mode = "private"` validation.
- Fortinet policy automation and chatbot/MCP-driven Fortinet configuration.
- Move fast-changing chatbot image tags into a generated or versioned runtime
  vars file so local copied personal vars do not pin old demo image tags.
- FortiFlex licensing.

## v0.3 - Phase 3 Demo Milestone

Release date: 2026-07-14

Consolidates the work after `v0.2` into the Phase 3 demo milestone.

Validation note: this release has been exercised through repeated build/rebuild
cycles and targeted component testing. Not every optional configuration path has
been fully retested from a completely fresh environment, including a fully fresh
ECR repository creation/import and image publishing cycle. Treat the documented
default path as the primary validated workflow and use the status/test playbooks
after changing optional paths.

### Agent, LiteLLM, And Chatbot Demo

- Made LiteLLM the baseline model/provider layer for the demo.
- Added LiteLLM profile aliases for:
  - `pass-bedrock`
  - `demo-a`
  - `demo-b`
  - `demo-a-faig-be`
  - `demo-b-faig-be`
- Added backend instruction-profile support through LiteLLM.
- Consolidated the custom chatbot into one UI with selectable paths:
  - direct LiteLLM
  - FortiAIGate static route
  - FortiAIGate intelligent/header route
- Added path-specific profile selectors in the chatbot UI.
- Added optional frontend system-prompt injection for the chatbot.
- Made chatbot image publishing separate from FortiAIGate image publishing.
- Made the chatbot ECR image mutable for faster demo iteration.
- Added source checksum rollout support so chatbot app changes trigger a pod
  rollout on redeploy.

### MCP Demo Tools

- Added an optional MCP demo server in the `mcp` namespace.
- Added deterministic demo tools:
  - customer lookup/search
  - ticket lookup/search
  - policy lookup/search
  - customer ticket summary
  - echo/debug
- Added MCP Ansible playbooks:
  - `deploy_mcp.yml`
  - `status_mcp.yml`
  - `validate_mcp.yml`
  - `test_mcp.yml`
- Added an LLM-directed MCP tool loop to the custom chatbot:
  - the model receives available tool schemas
  - the model requests tool calls
  - the chatbot calls MCP
  - the chatbot sends tool results back through the selected LLM path
- Added configurable MCP direct/FortiWeb-future endpoint variables.

### FortiAIGate Routing And Validation

- Reworked the FortiAIGate routing model around explicit URI paths.
- Documented that broad `/v1/*` fallback routes should be created last.
- Added supported default FAIG route concepts:
  - `/v1/passthrough/*`
  - `/v1/demo-a/*`
  - `/v1/demo-b/*`
  - `/v1/demo-a-faig-be/*`
  - `/v1/demo-b-faig-be/*`
  - `/v1/intelligent/*`
  - fallback `/v1/*`
- Added FAIG intelligent routing defaults using a configurable model-route
  header.
- Updated `test_fortiaigate_chat.yml` to support:
  - single endpoint tests
  - route-matrix tests
  - static routes
  - intelligent/header routes
  - optional diagnostic routes
  - concise final pass/fail summary
- Changed route-matrix behavior to continue after expected endpoint failures
  and report a final summary instead of stopping at the first failed endpoint.
- Updated test prompts so each route asks the model to repeat the URI under
  test, making FortiAIGate logs easier to verify.

### Open WebUI, Demo Home, And HTTPS Gateway

- Consolidated Open WebUI into one optional deployment.
- Changed Open WebUI to default-off so the primary demo path uses the custom
  chatbot UI unless `openwebui_enabled=true`.
- Updated Open WebUI settings for the LiteLLM/FortiAIGate model path when it is
  enabled.
- Updated the demo home page to link to:
  - FortiAIGate Admin UI
  - custom chatbot
  - Open WebUI when enabled
  - LiteLLM Admin UI
  - MCP tools
- Added optional HTTPS gateway support for HTTP-only demo services.
- Aligned generated HTTP and HTTPS NodePort assignments by index:
  - `30080` -> `30443`
  - `30081` -> `30444`
  - `30082` -> `30445`
  - `30083` -> `30446`
  - `30084` -> `30447`
- Updated consolidated demo outputs to print HTTP/HTTPS URLs, LiteLLM provider
  values, and SSH access instructions.

### Automated Setup, Teardown, And Local Config

- Expanded `scripts/automated_quickstart.py` into a fuller guided workflow:
  - prerequisite checks
  - AWS profile/login handling
  - AWS SSO/device-code prompt support
  - CIDR validation and `/32` conversion prompt for bare public IPs
  - EC2 SSH key selection
  - FortiAIGate license preflight
  - LiteLLM key/password prompts
  - ECR state inspection/import guidance
  - Terraform apply across ECR, AWS prep, and EC2 k3s foundation
  - EC2 readiness polling
  - optional image publishing
  - Ansible deployment orchestration
- Added `--yolo` mode for repeat lab rebuilds using preconfigured values.
- Changed automated quickstart to check FortiAIGate status once after deploy,
  continue with the remaining app deployments, then check FortiAIGate status
  again at the end.
- Added `scripts/automated_teardown.py` for repeat lab teardown while
  preserving ECR repositories.
- Added `scripts/backup_config.py` usage to preserve local config, generated
  values, inventory, and Terraform state before destructive work.
- Added `scripts/sync_all_vars.py` and wired it into automated quickstart so
  new example defaults are appended to existing local files without overwriting
  local values.

### Terraform And AWS Infrastructure

- Continued the split Terraform flow:
  - `terraform/user.tfvars`
  - `terraform/aws-ecr`
  - `terraform/aws-prep`
  - `terraform/aws-ec2-k3s`
- Added/continued AWS Prep as the home for:
  - EC2 IAM role/profile
  - ECR pull permissions
  - trusted source CIDRs
  - EIPs
  - optional Bedrock IAM values
- Added generated demo port output for Ansible through
  `ansible/group_vars/ports.generated.yml`.
- Added support for multiple trusted source CIDRs.
- Added EC2 hourly and monthly compute cost outputs using AWS Price List data.
- Added VPC layout documentation for:
  - public k3s subnet
  - private k3s subnet placeholder
  - FortiGate/FortiWeb public subnet placeholders
  - EIPs
  - k3s pod and service networks

### ECR And Image Publishing

- Improved FortiAIGate image publishing idempotency by using source archive
  metadata and skipping already-loaded/published images when possible.
- Added filtering so operators can publish only selected image groups, including
  chatbot-only publishing.
- Documented imported ECR repository teardown safety:
  - remove ECR repo resources from Terraform state before destroy when
    repositories must be preserved
  - keep ECR creation/import as a separate workflow from repeat EC2 rebuilds
- Added future notes for shared, unmanaged, same-account, and cross-account ECR
  use.

### Documentation

- Reworked quickstart documentation into manual and automated flows.
- Added current architecture and baseline docs.
- Added MCP documentation.
- Added VPC layout documentation with Mermaid diagram.
- Rebuilt the FortiAIGate initial configuration guide:
  - LiteLLM provider values
  - guard/provider table
  - route/flow table
  - explicit route order guidance
  - onboarding screenshots
  - guard and flow screenshots
  - intelligent routing screenshots
  - log review guidance
- Added a Mermaid flow reference for the FortiAIGate/LiteLLM/chatbot path.
- Added macOS/Windows/editor noise entries to `.gitignore`.

### Deferred

- FortiWeb and FortiGate appliance deployment.
- Private k3s mode.
- Local Ubuntu parity.
- Bedrock direct as a first-class alternate provider path.
- Ollama as a first-class alternate provider path. Current Ollama support is
  limited to alternate/test configuration after an external Ollama endpoint and
  corresponding provider settings exist.
- Shared/cross-account ECR automation.
- Single smoke-test wrapper script.

## v0.2 - Frontend Redesign

Tag: `v0.2` (`dd84204`)

This was the first larger frontend/application milestone.

- Added the LiteLLM deployment path and Admin UI.
- Added consolidated demo application deployments for:
  - LiteLLM
  - Open WebUI
  - custom chatbot
  - demo home
  - optional HTTPS gateway
- Added chatbot app, Helm chart, and instruction files.
- Added Open WebUI chart/deployment support.
- Added demo home chart/deployment support.
- Added optional HTTPS gateway chart/deployment support.
- Added publish flow for the chatbot image.
- Added status and validation playbooks for the new app layer.
- Added consolidated output playbook for demo URLs and provider values.
- Introduced `terraform/user.tfvars` and moved user-facing AWS prep work into
  `terraform/aws-prep`.
- Removed the standalone user-facing `terraform/aws-bedrock` flow in favor of
  AWS Prep.
- Updated quickstart documentation, deployment runbook, architecture docs, and
  troubleshooting docs around the new frontend/application flow.

## v0.1 - FortiAIGate 8.0.1 And Deployment Hardening

Tag: `v0.1` (`9222e3d`)

This milestone stabilized the original FortiAIGate AWS demo and updated it for
FortiAIGate 8.0.1 behavior.

- Updated defaults and docs for FortiAIGate 8.0.1.
- Documented version-specific behavior:
  - UI path changed to `/ui/`
  - default admin password differences
  - HTTPS backend behavior
  - Triton startup timing
- Added initial FortiAIGate GUI setup screenshots.
- Improved README quickstart and deployment runbook flow.
- Improved k3s validation output with `GO` / `NO GO` style status.
- Improved FortiAIGate status output.
- Added or refined FortiAIGate validation and chat test behavior.
- Improved image publishing by splitting archive load/push behavior and adding
  idempotency checks.
- Moved smoke-test helper scripts under `scripts/`.
- Added Bedrock direct test helper updates.

## Initial Foundation

Commits before `v0.1` established the first working AWS/k3s/FortiAIGate demo
foundation.

- Initial repository structure and README.
- Terraform module for AWS EC2 k3s foundation.
- Terraform module for ECR repositories.
- Initial Bedrock IAM setup.
- Ansible bootstrap for Ubuntu 24.04 GPU k3s host.
- NVIDIA driver/runtime and k3s bootstrap automation.
- FortiAIGate Helm deployment automation.
- Initial deployment docs and troubleshooting notes.
- Instance sizing notes.
- First full successful Terraform + Ansible test pass.
