# 8.0.2 quickstart integration contract

This is a proposed handoff, not an implemented deployment interface. The
quickstart application guard must remain until the platform path and these
dependencies are implemented and tested on a disposable lab.

- Management deployment must accept an in-cluster FAIG origin and LiteLLM
  address from deployment configuration, deploy with no selected scenarios,
  students or pre-existing student keys, and expose a readiness check and
  instructor URL. It must document its playbook, inventory and variables.
- Management must define server-side instructor authorization, its signing and
  service secrets, their private locations, and catalog versus durable selected
  state. Quickstart must not pass credentials in command arguments or logs.
- A versioned catalog adapter must export every supported shipped alias and its
  instruction source to LiteLLM independently of class selection. The current
  LiteLLM role consumes the installed-scenario matrix, so it does not yet meet
  this contract. Validate instruction behavior and direct LiteLLM access as
  well as model listing before treating the preload as complete.
- Experimental initialization needs an idempotent, observable interface for
  fresh and partially initialized installations, including ambiguous write
  outcomes, verified license and scanner status, one provider using a private
  non-admin LiteLLM credential, and a real governed request with a scoped test
  key and defined cleanup. The existing experimental initializer reports
  upload acceptance, not license or scanner verification; it is not a safe
  implementation of this contract by itself.
- The platform path must use the selected AWS profile, region and Terraform
  workspaces without modifying ECR lifecycle or destroying shared resources;
  existing ECR and image-cache dependencies need a documented read-only
  interface. It must distinguish platform errors, setup pending, partial setup,
  invalid license and verified operation. Do not declare end-to-end success
  until management readiness and the selected initialization checks pass.

Integration must preserve the guard until both workstreams agree on the actual
interfaces, and validate opt-out and opt-in on disposable infrastructure. The
running lab is not a test target for this work.
