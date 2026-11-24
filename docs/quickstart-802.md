# FortiAIGate 8.0.2 quickstart

Use this guide to deploy the AWS lab, prepare a class, and tear the lab down.
For the tested scope and current limitations, see the [release notes](release-notes-1.2.0-rc.1.md).

## Before you start

Complete [first-run preparation](first-run-preparation.md): install the required
local tools, sign in to AWS, and place the FortiAIGate 8.0.2 Helm chart and
license in your FAIG workspace. Confirm your AWS account has the required GPU
quota and access to the selected region.

## Deploy the lab

From the repository directory, run:

```bash
python3 scripts/automated_quickstart.py
```

On the first run, quickstart offers to create or import your local profile,
then asks for the deployment settings. Review the AWS region and trusted IP
address before continuing. Select whether to run the experimental FAIG
initialization: when enabled, quickstart sets up the administrator, installs a
license, configures `pass-model`, and verifies a governed request. When disabled,
complete [FAIG setup manually](lab-management.md#if-you-set-up-faig-yourself)
before signing in to Lab Management. The initialization uses unsupported
GUI-observed APIs and may need changes after a FortiAIGate update.

After deployment, quickstart displays the FAIG and instructor URLs, the admin
email, and the private directory containing the generated password. The lab
uses a self-signed certificate, so your browser will prompt you to accept it.
No students or scenario policies are created until you choose to create them.

To prepare your profile without deploying, run
`python3 scripts/user_profile.py init`. Once your profile and deployment
settings are saved, a later run can reuse them without prompts:

```bash
python3 scripts/automated_quickstart.py --yolo
```

`--yolo` applies the saved settings without asking for confirmation. Review
them first, especially if your AWS account, region, or public IP has changed.
If a deployment stops after infrastructure is created, correct the issue and
resume with `python3 scripts/automated_quickstart.py --skip-terraform` using the
same profile.

## Prepare the class

Open the instructor URL and sign in as the FAIG administrator. Select and save
the scenarios, apply their models to FAIG, and create students. Choose whether
to prepopulate each student's scenario configuration or have students build it
in FAIG themselves. The [instructor guide](instructor-guide-802.md) walks
through these steps; share the [student guide](student-guide-802.md) with your
class.

## Tear down the lab

From the same checkout and saved profile, run:

```bash
python3 scripts/teardown_802.py
```

Teardown removes the lab's instances, network, Elastic IPs, IAM resources and
lab-owned S3 buckets. ECR images and the separate NVIDIA cache are retained.
If the syslog bucket contains logs, you can export them before deletion. For an
unattended teardown, use `--yolo` and, if logs exist, choose either
`--export-syslog /path/outside/repo` or `--discard-syslog`. GPU termination
can take several minutes.

## More help

- [First-run preparation](first-run-preparation.md): prerequisites, profile files,
  licenses and AWS setup.
- [Lab secrets and state](lab-secrets-and-state.md): credential locations,
  storage settings and static passwords. Keep private files and state out of Git.
- [Known issues](known-issues.md): current limitations and troubleshooting.
- [Advanced deployment reference](quickstart-802-advanced.md): named
  workspaces, overrides, recovery and teardown options.
- [Lab Management reference](lab-management.md): manual setup and advanced
  operations.
