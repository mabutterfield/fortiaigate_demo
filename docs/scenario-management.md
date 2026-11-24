# Scenario Management (FortiAIGate 8.0.2)

How lab scenarios get from the repository to students in 8.0.2: where they
are defined, how an instructor selects and provisions them, how they are
tested, and how to change one.

> **8.0.1 users:** the scenario installer (`scripts/scenario_profiles.py`
> add/update/remove, `render-work-order`, manual GUI work orders and
> `functional_test validate`) is **retired** in 8.0.2 and refuses to run. See
> [Historical 8.0.1 workflow](#historical-801-workflow) at the end of this page.

## Overview

| Step | Who | Where |
|---|---|---|
| Define scenarios | maintainers | `catalog802/data/` in Git |
| Deploy the lab, including models, MCP tools and the student chatbot | instructor | the [quickstart](quickstart-802.md) (one command) |
| Select scenarios, apply models, create students, prepopulate | instructor | Lab Management, `https://<host>:30444/manage/` |
| Chat, inspect keys, run graded tests | students (or instructor via *Act as student*) | the lab chatbot, `https://<host>:30444/` |
| Command-line check of one case | maintainers | `python3 -m functional_test catalog-baseline` |

There is no installed local copy, no work order and no manual FortiAIGate
flow or guard configuration per scenario. Lab Management creates every
per-student FortiAIGate object from the catalog.

## The catalog is the source of truth

`catalog802/data/index.json` lists the active scenarios. Each
`catalog802/data/scenarios/<id>.json` defines:

- learning goals, display name and description;
- the model alias and its backend instructions (rendered into LiteLLM);
- the MCP tools it uses (contracts in `catalog802/data/tools/`);
- actions with their detector, guardrail and policy templates;
- prompt groups (`clean`, `attack`) and graded tests.

Active scenarios in this release:

| Scenario | Actions | MCP tools | Graded tests |
|---|---|---|---|
| `fortistore-injection` (FortiStore Injection Product Advisor) | alert, block | none | alert/block attack; alert/block with the compromised frontend (opt-in) |
| `hr-tool-dlp` (HR Tool DLP) | alert, redact, block | employee directory and lookups | alert, redact, block attack |
| `resume-tool-injection` (Resume Tool Injection) | alert, block | document upload/read/check, resume search/summary | alert, block attack (block is a documented KNOWN FAIL) |

8.0.2 names the stopping action **block** (8.0.1 used *deny*). Object names
follow `studentNN_<scenario>_<action>`, for example
`student03_hr-tool-dlp_redact`, plus one `studentNN_passthrough` key with no
policy.

Read the catalog without editing anything:

```bash
python3 -m catalog802 student   # what students see (no backend instructions)
python3 -m catalog802 faig      # what Lab Management provisions
python3 -m catalog802 models    # model aliases and instructions
python3 -m catalog802 mcp       # resolved MCP tool contracts
```

Lab Management shows the same information under **Scenarios** (models and
lab prices, actions, tools, prompts and tests). See
[catalog802/README.md](../catalog802/README.md) for views, hashes and the
result contract.

## Before class

Follow the [Instructor Guide](instructor-guide-802.md#before-class). In short,
in Lab Management:

1. **Scenarios:** tick the scenarios for this class and **Save selection**.
2. **Apply models to FAIG:** adds the selected scenario models and
   `pass-model` to the `litellm-direct` provider with lab prices, then reads
   them back.
3. **Create students:** one workspace per student and one project per
   selected scenario.
4. **Prepopulate (optional):** creates each student's detectors, guardrails,
   policies and one key per action. Leave it off when students should build
   their own objects.

Re-running any step for the same students and scenarios is safe; existing
objects and keys are kept. Selecting another scenario later and
prepopulating again adds only what is missing. Details:
[Lab Management](lab-management.md).

## Testing scenarios

- **Students and instructors:** the chatbot **Tests** tab runs a catalog test
  against the student's key and grades it from the FortiAIGate Traffic Log
  (PASS, FAIL, KNOWN FAIL or INCOMPLETE). **Try a prompt** shows the verdict
  without grading. Instructors use *Act as student*. See the
  [Student Guide](student-guide-802.md#tests) and
  [Lab Chatbot](lab-chatbot.md).
- **Command line (maintainers):** `catalog-baseline` runs one live case with
  an owner-only key file and FAIG admin credentials and checks the matching
  Traffic Log rows:

  ```bash
  python3 -m functional_test catalog-baseline --help
  python3 -m functional_test evaluate-catalog --help   # grade saved observations
  ```

  `python3 -m functional_test baseline` checks prepopulated per-student keys
  without the chatbot. See [Functional Validation](functional-validation.md).

The test suite needs PyYAML; run it with the workspace virtual environment
(`../.venv/bin/python -m unittest discover -s tests`) if your system Python
lacks it.

## Changing a scenario

Scenario changes are repository changes, reviewed like code. There is no
per-lab tuning copy in 8.0.2.

1. Edit `catalog802/data/scenarios/<id>.json` (and any instruction file or
   tool fixture it references). Add a new scenario's file to
   `catalog802/data/index.json`. The structure is documented in
   `catalog802/schema/scenario.schema.json`; the loader also checks
   cross-references.
2. Check it:

   ```bash
   python3 -m unittest discover -s catalog802/tests
   python3 -m catalog802 faig > /dev/null
   ```

3. Redeploy what the change affects (each role renders the catalog at deploy
   time from the checkout it runs in):

   | Change | Redeploy |
   |---|---|
   | Model alias or backend instructions | `deploy_litellm.yml` |
   | MCP tool contract or fixture | `deploy_mcp.yml` (a new tool *handler* is code: develop and test it first) |
   | Prompts, tests, actions or display text | `deploy_lab_chatbot.yml` and `deploy_lab_management.yml` |
   | Detector, guardrail or policy templates | `deploy_lab_management.yml`, then prepopulate; existing student objects are **not** changed |

   ```bash
   TF_WORKSPACE=<workspace> ansible-playbook -i ansible/inventory/aws.generated.ini ansible/playbooks/deploy_lab_management.yml
   ```

   Rerunning the quickstart on the same instance (it resumes and reuses the
   instance's credentials) also redeploys these components.
4. In Lab Management, **Apply models to FAIG** if models changed, then
   prepopulate. Prepopulation keeps existing objects, so a student who
   already has an object under the same name keeps the old version: delete it
   in FortiAIGate first, or use new student numbers.
5. Run the scenario's tests from the chatbot.

Candidate scenarios (for example `hr-sensitive-lookup`) and archived ones are
not in the 8.0.2 catalog. Moving one in means writing its catalog definition
and validating it live; the old package files are reference material only.

## Removing a scenario from a class

Untick it in Lab Management and save. Existing student projects, objects and
keys stay in FortiAIGate until you delete them there. To drop a scenario from
the release, remove it from `catalog802/data/index.json` and redeploy.

## Known limitations

- **Resume Block** is a documented KNOWN FAIL: FortiAIGate blocks before the
  `document_read` tool runs.
- Prepopulation never updates or deletes existing objects.
- The optional FortiAIGate re-entry chain is not part of 8.0.2 yet.
- Scenario editing in the browser is not built; change the catalog in Git.

## Historical 8.0.1 workflow

In 8.0.1, scenarios were packages under `chatbot/scenarios/examples/`,
installed as editable ignored copies with `scripts/scenario_profiles.py`, and
configured by hand in the FortiAIGate GUI from a rendered work order. That
workflow, the 8.0.1 chatbot and `functional_test validate` are retired in
8.0.2; the commands print a retirement message. The package folders remain
temporarily for migration and parity tests only.

The complete 8.0.1 code and documentation are preserved on branch
`archive/8.0.1` and tag `v1.0_faig8.0.1`. Pages that still describe the
8.0.1 model, kept for reference:
[Advanced Scenario Management](advanced-scenario-management.md),
[Scenario Authoring](scenario-authoring.md),
[Scenario GUI Configuration](fortiaigate-gui-config.md) and the
[package READMEs](../chatbot/scenarios/README.md).
