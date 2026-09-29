---
name: delegating-github-ci-repairs
description: >-
  In the interactive shell, prepare the hosted gateway and delegate a bounded
  GitHub PR repair or remote demo. Use for remote CI repair onboarding. Gateway
  execution and repair-status requests belong to operating-github-ci-repairs.
getting_started: Run CI/CD repairs remotely
demo_order: 3
metadata:
  owner: Vincent
  last_changed_by: Jan
  last_changed_at: 2026-09-29
  usecases:
    - For interactive-shell users running a GitHub CI repair on their hosted gateway.
  requires:
    - An interactive shell and an organization administrator account for hosted gateway access.
    - A reachable hosted gateway with a GitHub integration and an authenticated coding agent.
    - GitHub write access to the selected PR; demo mode also needs private-repository creation.
  version: "2.4"
---

# Delegate a remote CI repair

The shell owns gateway readiness, target selection, handoff, and reporting.
The gateway owns repair execution through `operating-github-ci-repairs`.
This demonstrates a bounded repair that continues without the shell; it does
not establish continuous repository monitoring.

## Plan

Create the live plan with `update_plan`. Preserve completed steps across menu
answers. Mark Step 4 `verifies: true` and Step 5 `deliverable: true` in every
plan update. Pair bookkeeping with an action where possible; a menu must be
the only tool call in its response.
Include Step 2 only when target information is missing. When the request
already selects a demo or PR, record that scope in the plan explanation and
proceed from readiness to delegation. A reasoning-only selection cannot earn
a separate completed plan step.
Record work that cannot run as `blocked`, with its reason in `explanation`.

- [ ] Step 1. Prepare the hosted gateway with check_hosted_gateway.
- [ ] Step 2. Ask for missing repair-target information with ask_user_choice.
- [ ] Step 3. Delegate execution with ask_hosted_gateway and retain its prompt ID.
- [ ] Step 4. Verify the remote repair outcome through ask_hosted_gateway.
- [ ] Step 5. Show the remote outcome and evidence as Markdown.
- [ ] Step 6. Offer the next step or blocker resolution with ask_user_choice.

## Workflow

### Step 1. Prepare the hosted gateway

Call `check_hosted_gateway()`. Follow its setup guidance if sign-in or provisioning
is needed: use `/account login` in the shell and `start_hosted_gateway()` as
appropriate, then check readiness again. Reuse a healthy running gateway.

Complete when the gateway is ready, or report the concrete setup blocker.
The first repair request in Step 3 also verifies the prompt round-trip; a
separate ping or inventory of historical loops is unnecessary.

### Step 2. Ask for missing repair-target information

Use the user's existing PR selection or demo choice. Otherwise ask once with
`ask_user_choice`, title `Remote Repair Target`, offering
`Use a disposable demo repository` and `Use an existing pull request`, with
custom answers enabled.
For an existing target, obtain its PR URL or owner, repository, and PR number.
The bounded tool repairs a PR; a repository or branch alone is incomplete.

Explain that demo mode uses a reusable private demo repository and retains the
repository and evidence afterward. Carry the user's choice forward; the remote
tool may separately request approval for its concrete invocation.

Complete when the chosen scope is known. Keep local GitHub credentials out of
the handoff: the gateway uses its organization's integration.

### Step 3. Delegate execution

Send one complete request with `ask_hosted_gateway(prompt=..., facts=...)`.
Name `operating-github-ci-repairs` as the remote execution skill and include
either `demo: "true"` or the selected PR details as string facts. For example:

> Use operating-github-ci-repairs on this gateway to run the selected bounded
> repair. The user selected the private demo. Return the repair task ID and
> retained outcome with CI evidence. Relay any required tool approval. If the
> named skill is unavailable, report the gateway version mismatch before
> scheduling anything.

Execute the shell's skill here; the remote request names the gateway's skill.
Complete when the request is accepted and its `prompt_id` is recorded.

### Step 4. Verify the remote outcome

Continue according to the returned request state:

- `needs_input`: the tool opens the gateway's question in the shell. Wait for
  the user's answer, then call `ask_hosted_gateway(prompt_id=...)` with no new
  prompt. Use the latest returned prompt ID for subsequent questions.
- `queued` or `running`: retrieve that same prompt ID; keep the original work.
- `done`: inspect the answer for the repair `task_id` and outcome. A completed
  prompt can describe a repair that is still running. For that case, send a
  narrow new request naming `operating-github-ci-repairs` and the existing
  `task_id`, asking only to inspect and wait for that repair. A settled prompt
  ID returns its old answer, not a fresh repair status.
- `failed`: report the failure and any returned integration guidance. Recover
  an already-known task by its ID before considering another execution request.

Retain both IDs: `prompt_id` continues the gateway exchange; `task_id` identifies
the repair. Continue observation within the repair's original deadline; never
restart setup or create another repair to obtain status. For a GitHub connection
blocker, direct the user to https://app.opensre.com/dashboard/github and follow
the tool's continuation guidance after it is corrected.

Complete when the remote task has a terminal outcome, or a concrete blocker
prevents further verification. Claim a successful demo only with the failing
run, repair commit, and passing run from that task. An accepted request, token
permission check, or successful scheduler delivery alone proves no repair.

### Step 5. Show the outcome

Report the target PR, task ID, repair outcome, available CI evidence links, and
retained resources. State pending, blocked, or failed outcomes plainly. The
task's gateway ownership establishes independence from the shell; claim a tested
disconnect only if the shell was actually disconnected during execution.

Complete when the Markdown report has been shown. Keep the gateway running so
an unfinished repair can continue.

### Step 6. Offer the follow-up

After a successful repair report, use `ask_user_choice`:

- Configure Slack or Telegram
- Add more scheduled tasks
- Exit to interactive shell

For a blocked repair, offer a choice that would address the concrete blocker
and one to leave the work blocked. For a pending task, offer to continue
observing the same task ID or leave it running. Keep these recovery choices
separate from the successful-demo options above.

Complete when the appropriate menu is offered. Keep this step pending until
the report has been shown; skipping it as already completed conflicts with
the runtime's requirement to resolve blocked work with the user.
