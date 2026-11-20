# Instructor guide — FortiAIGate 8.0.2 lab

How to run a class on a deployed lab. For deployment see
[quickstart-802](quickstart-802.md); for internals see
[Lab Management](lab-management.md), [lab chatbot](lab-chatbot.md) and
[lab gateway](lab-gateway.md).

## Addresses

| What | Address | Who |
|---|---|---|
| FortiAIGate GUI | `https://<host>/ui` | instructor; students for their own workspace |
| Lab Management | `https://<host>:30444/manage/` | FAIG super administrators only |
| Student chatbot | `https://<host>:30444/` | students; instructors via **Act as student** |

Use HTTPS. `http://<host>:30081` only redirects to `https://<host>:30444`, and
a redirect cannot protect anything already typed into an HTTP page. The lab
uses its own generated certificate, so browsers show a warning the first time.

Sign in with your FAIG administrator account (super admin). Students get a
403 on `/manage/`.

## Before class

1. **Scenarios.** In Lab Management, tick the scenarios for this class and
   **Save selection**. The preview lists each scenario's models, prices,
   actions, tools, prompts and tests.
2. **Apply models to FAIG.** Adds the selected scenario models (and
   `pass-model`) to the LiteLLM provider with lab prices, keeping other models
   and credentials, then reads the provider back to verify.
3. **Create students.** Choose the first number and how many
   (`student01@…`, workspace `student01_workspace`, one project per selected
   scenario). Password options: one generated per student, one shared password,
   or a base plus the student number (`Base_` → `Base_01`). Passwords must pass
   FAIG's rules and differ from yours. Re-running the same numbers is safe.
4. **Prepopulate (optional).** Tick *Also prepopulate* (or use **Prepopulate
   existing students**) to create, for each student and selected scenario, the
   detectors, guardrails, policies and one key per action, plus a
   `studentNN_passthrough` key. Students who should build their own objects
   are left without prepopulation.
5. **Share page.** **Open share page** shows number, name, email, password and
   sign-in address, for screen sharing. Optional display names stay in the lab
   and are never sent to FAIG.

## During class

- **Auto-approval** (on by default). FAIG makes an administrator approve every
  detector, guardrail and policy a student submits, changes or deletes. While
  on, the lab approves **every pending change**, including deletions, about
  once a minute, using your FAIG session. The indicator (top right) shows
  running, the end time, the last run and how many were approved; **stale**
  means a run is overdue, **expired** means your FAIG session ended.
  - It keeps running when you close the page, for the hours you chose (up to
    8 hours from your sign-in). It stops when you turn it off, sign out, your
    FAIG session ends, or the lab gateway restarts. Opening Lab Management
    starts it again while it is on.
  - **Approval history** lists each approval: time, student, type (detector,
    guardrail, policy), object, change (add, change, delete), result, and
    whose session approved it. Filter by student.
- **Act as student** (chatbot sidebar). See any student's keys (read-only) and
  run their tests; results are graded against that student's Traffic Log.
- **Reset a student's password.** Generated, typed, or base + number. The new
  password is checked by signing in as the student before it is kept; if FAIG
  refuses or it does not work, the old one stays. The share page updates.
- **Restore lost key values.** If a prepopulated key exists in FAIG but its
  value is lost (FAIG shows a key value only once), run **Prepopulate existing
  students** with *Also restore lost key values*. The key is rotated and the
  new value stored; the old value stops working within about a minute.
- **Operation journal** lists every job with its result lines. It never holds
  passwords or key values.

## Sessions and restarts

- The lab gateway signs you out after **25 minutes idle** and after **8
  hours**; FAIG's own idle limit is 25–30 minutes. Sign in again when asked.
- If Lab Management restarts during a job, the job shows `interrupted`; run
  the same batch again, which reconciles what was already done.
- A lab gateway restart signs everyone out and stops auto-approval until you
  reopen Lab Management.

## Known limitations (v1.0)

- **Resume Block** (Resume tool injection, block action) is a known failure:
  FAIG blocks before the `document_read` tool runs, so the test reports
  KNOWN FAIL rather than PASS.
- Auto-approval approves everything pending in FAIG, not only lab students'
  changes; turn it off when you need to review changes yourself.
- Tests that the 8-hour limit and a mid-run FAIG rejection stop auto-approval
  are covered by unit tests, not yet by a live run.
- The GUI-only (no GPU, no license) mode is not supported in v1.0.

## Troubleshooting

| Symptom | What to do |
|---|---|
| `/manage/` shows 403 | Your account is not a FAIG super admin. |
| "Your FAIG session ended; sign in again" | Sign in again; re-run the job. |
| Auto-approval **expired** | Sign in again and reopen Lab Management. |
| Auto-approval **stale** | Check that FAIG and the lab gateway are up; reopen the page. |
| Create students: "rejects this password as weak" | Use a stronger password or the generated option. |
| A student's tests are INCOMPLETE with "no active FAIG session" | The student signs in again (after a gateway restart or 25 minutes idle). |
| Prepopulate reports a key "without a stored secret" | Re-run with *Also restore lost key values*. |
