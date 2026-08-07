# Upcoming Features

This page records likely directions for the FortiAIGate demo. Items here are
not implemented features, release commitments, or supported setup steps. Use
the [Current Baseline](reference/current-baseline.md) for what works now.

## Repository And Deployment Separation

- Move container-repository creation, image import, and ECR publishing out of
  the normal deployment quickstart into a distinct source-repository
  maintenance workflow.
- Keep the quickstart focused on consuming prepared images and deploying the
  lab, while retaining a clear link to the maintenance workflow for builders.

## Licensing

- Integrate FortiFlex-based licensing choices for applicable appliances and
  products.
- Preserve secure local handling of entitlements, tokens, license files, and
  generated credentials.

## Scenario Creation

- Add `scenario create --blank` for a locally owned starter package with a
  visible template instruction response.
- Add `scenario create --copy <existing>` for an independently named local
  scenario derived from an installed scenario or tracked example.
- Evaluate an explicit per-scenario FAIG-chain switch as part of creation,
  instead of relying only on hand-edited metadata and documentation.

## Demo Home User Guide

- Publish selected repository Markdown into a browsable Demo Home guide.
- Keep source documentation authoritative while presenting operator and demo
  walkthrough content inside the running lab.

## Scenario And Appliance Coverage

- Mature retained candidate scenarios only after their fixtures, metadata,
  expected outcomes, documentation, and live tests meet the baseline contract.
- Validate additional appliance traffic paths, including FortiGate-observed
  LLM traffic and more restrictive appliance-fronted access designs, without
  making optional appliances dependencies of the core deployment.
