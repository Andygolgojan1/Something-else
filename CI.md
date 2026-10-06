# Local Validation and PR CI

This file is the **single source of truth** for required local validation before
any push or pull request. Repository-wide validation runs in GitHub Actions.
GitHub Actions owns the complete automated PR validation. Local work should
provide fast feedback on the change, without manually repeating that pipeline.

<!--
Keep this document focused on required local checks and post-PR follow-through.
Do not add optional commands, CI implementation details, or tool-specific
procedures unless they change what contributors must do locally.
Automated contributors must not invent or run additional local CI steps beyond
the scoped checks below unless another applicable instruction or the user
explicitly requires them.
-->

## 0) Setup and automatic push validation

Run `make install` after cloning. It installs locked development dependencies
and a blocking pre-push hook for this checkout. For an existing environment,
run `make install-hooks`. Installation preserves existing hooks and keeps
linked worktrees independent.

The hook validates the **committed revisions being pushed** in temporary Git
worktrees with their locked dependencies. An uncommitted fix cannot make a
broken commit pass. Existing push hooks run first and receive Git's original
arguments and ref updates.

## 2) Focused tests and complete CI

Use the smallest relevant regression test or `make test-scope` during
development. Choose one scope that exercises the changed behavior; do not
run a test file, its parent suite, and the scope target consecutively for the
same unchanged code. Repeat or broaden only after changes, failures, or an
unresolved concern justify it.

| Change | Manual local validation |
| --- | --- |
| Non-executable documentation without test-backed contracts | Review the diff and affected links; no Python checks. Runtime prompts and skill cards are not ordinary documentation. |
| Documentation with test-backed contracts | Run the closest contract tests for the edited content; documentation-only PR CI does not run these tests. |
| Product or test behavior | Run the closest regression tests, or `make test-scope` when the affected tests are unclear. Record the scope and result in the PR. |
| Behavior outside automated PR coverage | Run the relevant package-specific smoke, live-integration, install, or UI check. Explain what it verifies and any unavailable credentials or environment. |

For documentation contracts, consult the explicit path mappings in
[.github/ci/test_scope_rules.py](.github/ci/test_scope_rules.py) and tests that
read the edited file. The current documentation classifier skips these paths
in `make test-scope` and the push gate, so invoke the relevant mapped pytest
targets directly. A documentation extension alone is not evidence that no
tests are needed.

Do not require separate local `make lint`, `make format-check`,
`make typecheck`, import/registry checks, `make test-full`, or `make test-cov`
before each commit, push, or PR. Do not manually run `make check` or
`make pre-push` immediately before a push that already runs the installed
hook. These commands remain available for diagnosing a specific failure.

The installed hook still runs its shared quality checks and selected tests
against the committed revisions. This policy removes duplicate manual runs;
it does not disable the hook or authorize its emergency override for routine
work. Package guides may require checks for behavior that PR CI does not
exercise, but must not add another mandatory run of CI-covered checks.

GitHub Actions uses the same quality check definitions as the local gate and
runs the complete PR test selection. It owns repository-wide static checks,
typechecking, import/registry contracts, automated tests, and packaging
preflight. Coverage, full CodeQL, and release validation run on `main` as
described below. Local results do not waive required GitHub checks.

## 3) Emergency override

For an intentional emergency bypass, supply a reason for that push only:

```bash
git -c opensre.prePushOverride='incident reference and reason' push
```

The hook prints the override and appends the reason, timestamp, and pushed
revisions to `pre-push-overrides.jsonl` inside this checkout's Git directory.
Existing user hooks still run. This bypass does not waive remote CI or merge
requirements. Do not set the override permanently in Git configuration.

## 4) Pull-request latency and post-merge validation

The required automated pull-request execution gate has a p90 target of 90
seconds. Static checks, cached typechecking, duration-balanced pytest shards,
and interactive-shell checks run concurrently. Automated and
human review completion, including Greptile and Codex when available, remains a separate merge
requirement and is not part of that execution-time SLO.

Pull requests run the complete test selection without coverage instrumentation;
the same matrix produces and combines the full coverage report on `main`.

Full CodeQL `security-and-quality` analysis runs after every merge to `main` and
on the weekly schedule, not on ordinary pull requests. A production-only,
default-query profile is available through the CodeQL workflow's manual
`pr-fast` input for benchmarking. Do not make that profile required unless at
least ten representative runs demonstrate p90 at or below 75 seconds.

Post-merge validation is part of delivery. Monitor the `main` CI, CodeQL, and
release workflows for the merge commit; a failure requires an immediate fix or
revert and must not be reported as successful delivery.

## 8) Post-PR follow-through

Opening a pull request does not end the validation cycle. Follow it through until
the repository's merge requirements are satisfied: required GitHub checks are
green, actionable human or automated review feedback (including Greptile and
Codex when available) is
addressed, and resolved conversations are closed out.

Agents: the always-on rule lives in [AGENTS.md — CI failures and tests](AGENTS.md).
After every push, inspect `gh pr checks` / failing job logs and fix until required
jobs are green. The Cursor stop hook `.cursor/hooks/check-ci-failures.sh` will
re-prompt when the open PR still has failing checks.

A green check does not mean review feedback is clear. After checks complete,
and again after every push, inspect all unresolved conversations and latest
reviews. Validate each finding. For actionable feedback, push an appropriate
fix, reply, and resolve the addressed thread. For an incorrect or non-actionable
finding, reply with the rationale and resolve the thread without changing code.

After each completed PR update, once commits are pushed, the PR description is
current, and addressed threads are resolved, trigger the required automated
reviews. Follow [CONTRIBUTING.md](CONTRIBUTING.md#greptile-code-review) to
request Greptile; repeat until it reports 5/5 with no unresolved comments. If
Codex review is available for the repository, request it with `@codex review`
and address its actionable feedback. Do not re-trigger either reviewer while
its review is already running.

Use relevant built-in capabilities or locally installed skills, when available,
for PR monitoring, CI diagnosis, and review remediation rather than duplicating
tool-specific procedures in this document. Keep monitoring after each update;
do not treat creating or updating the PR as task completion. Validate review
suggestions before applying them, and rerun the appropriately scoped local
checks before pushing a fix.

## Precedence

If readiness instructions conflict across docs, **this file wins** for push/PR checks.
