+++
title = "Working With Claude Code on Long-Running Refactors: Lessons From a Test-Suite Migration"
date = 2026-05-04T10:00:00+05:30
tags = ["ai", "claude-code", "developer-experience", "refactoring", "testing"]
categories = []
summary = "Eight habits that held up while pairing with an agentic AI on a multi-day test-suite migration: spec-first delivery, iteration-time CI economics, the 'natural pause' anti-pattern, why repeated fixes are evidence the model is wrong, and how memory turns one session's lessons into the next session's defaults."
showTableOfContents = true
+++

A test-suite migration I'd budgeted at a few months of careful manual work shipped over two days of pairing with Claude Code, in roughly seventy commits and north of seventeen thousand lines of new Go (and deleted bash).
Much of it ran during overnight autonomous loops — the agent finished a batch, scheduled its next turn, read CI when it woke up, and either fixed the failure or moved on.

What made that work — when it worked — was a small set of habits more than any clever prompt:

- A spec written before any code.
- A planning workflow (`superpowers:brainstorming` and `superpowers:writing-plans`) that turned "migrate 48 bash tests" into a sequenced delivery plan with acceptance criteria per phase.
- CI cycles short enough that the autonomous loop didn't starve.
- A memory system that promoted each session's hard-won lessons into the next session's defaults.

What follows are eight of those habits, illustrated against the migration of [Fission's](https://github.com/fission/fission) integration suite from 48 brittle bash scripts to a Go framework — [PR #3356](https://github.com/fission/fission/pull/3356) and the cleanup [PR #3357](https://github.com/fission/fission/pull/3357).
Most of them are not Claude-Code-specific.
They apply to any agentic-AI pairing that runs longer than one session.

## The migration: what shipped, and what "done" meant

Fission is a Kubernetes-native serverless framework — functions, environments, and on-cluster package builds.

The integration test suite at the start was forty-eight bash scripts, fanned out by GNU `parallel` from `test/kind_CI.sh` across three Kubernetes versions:

- String-grep assertions and retry-up-to-eight-times loops, papering over flakes.
- No shared types with the Go codebase — changing a Custom Resource field meant updating a regex.
- When a test failed, the only diagnostic was the `kubectl-and-grep` transcript.

The migration shipped across about seventy commits in two pull requests:

- [PR #3356](https://github.com/fission/fission/pull/3356) — added a Go test framework under `test/integration/`, ported forty-seven of the forty-eight bash tests on top of it, and added an env-gated cohort that runs only when image and jar paths are exported.
- [PR #3357](https://github.com/fission/fission/pull/3357) — retired the bash harness in one atomic teardown.

"Done" meant something concrete:

- Thirty-nine Go integration tests run on every pull request, on three Kubernetes versions.
- Six env-gated tests live in the same suite and run when their inputs are present.
- One un-migrated bash test was deleted outright; nobody could justify keeping it.
- The bash runner is gone.

## Plan once, ship in atomic slices

The first commit on the migration branch was docs-only — `docs/test-migration/00-design.md`.
That doc was the contract.
It captured the decisions that would otherwise have triggered a debate every batch:

- Real Kind cluster vs. envtest — chose Kind for production-fidelity.
- `testing` + `testify` over a heavier framework.
- Hybrid in-process CLI plus clientset.
- A new `test/integration/` tree, separate from `test/e2e/`.
- Three diverse pilots before any bulk migration.
- Every bash test gets `#test:disabled` in the same commit as its Go counterpart.

Every batch after Phase 0 was a single atomic commit:

- Add the Go test.
- Mark the bash counterpart `#test:disabled`.
- Drop it from `test/kind_CI.sh`.
- Update the migration ledger.

HEAD was always green.
Any reviewer (or the agent itself, the next morning) could rebuild context from any commit on the branch.

The phasing was explicit, with a single testable acceptance criterion per phase:

- **Phase 0** — design doc.
- **Phase 1** — framework + first pilot.
- **Phases 2-3** — two more pilots, deliberately different shapes (CLI-driven, fixtures-heavy).
- **Phase 4** — bulk migration by category.
- **Phase 5** — cleanup of tests originally classified as deferred.
- **Phase 6** — delete the bash harness in a follow-up PR.

"Phase 4 done" meant a category was zero bash tests and the corresponding Go tests were green on three Kubernetes versions.
Not "approximately ported."

The agent does not know your shipping conventions until you write them down.
Without a spec, every batch becomes a small debate about scope.
With one, the debate is settled in advance.

> *A spec is not a planning ritual; it's a leash for the AI's enthusiasm.*

## The autonomous loop is real — and has a failure mode

Claude Code exposes a `ScheduleWakeup` primitive that lets the agent schedule its own next turn N minutes from now.
The migration cycle settled into:

1. Push a batch of commits.
2. Schedule a wakeup roughly fifteen minutes out (matching the iteration-time CI cycle).
3. End the turn.
4. The runtime fires the next turn.
5. Read the latest CI run; fix the failure or push the next batch.
6. Schedule the next wakeup; end the turn.

Steering reduced to a couple of messages an evening, when the agent needed a decision it could not make on its own.
The kickoff for one overnight run was a single line:

> *"lets go ahead.
> I am going to sleep, you can continue till possible, fix failing test and then continue with further tests.
> Do not stop unless you are very unsure.
> We want to cover as much as tests possible.
> Optimize over period as much possible."*

The agent honored that contract across the next several batches without further input.

{{< mermaid >}}
sequenceDiagram
    participant U as User
    participant A as Agent
    participant W as ScheduleWakeup
    participant CI as CI

    U->>A: kick off batch
    A->>CI: push commit
    A->>W: schedule next turn (~15 min)
    Note over A: agent ends turn
    W-->>A: wake up
    A->>CI: read run status
    alt CI failed
        A->>A: diagnose + push fix
    else CI green
        A->>A: prepare next batch + push
    end
    A->>W: schedule next turn
    Note over U: User asleep / away
{{< /mermaid >}}

Two operational details made the loop survive long runs:

- **CI is the gate, not the agent's claim.**
  That is its own pattern below.
- **Context compaction.**
  On a multi-day session the conversation context fills up faster than expected — full CI logs and source files get read on every turn.
  The context ran out twice during the migration, forcing the session to restart from scratch.
  On the third occasion, automatic context compaction was enabled, and the loop kept running.
  *Configure compaction before the first wakeup, not after the first failure.*

### The failure mode: premature graceful deferral

The loop's natural failure mode has nothing to do with infrastructure.
The agent kept announcing "natural stopping points" and "natural handoffs" and that "the migration is complete" — and every time, the deferral was lazy categorization, not a real blocker.

The agent would label a batch of tests as blocked on a category — *"streams to `os.Stdout`,"* *"yaml fixtures need templating,"* *"needs a Maven jar."*
A nudge to investigate one step further would unblock all of them within an hour or two:

- *"Blocked on infrastructure changes."* → six tests landed in three hours, once an explicit per-test list forced the deferral to be defended.
- *"CLI streams to `os.Stdout`, can't capture."* → solved with a small framework helper that captures stdout under an RWMutex.
- *"YAML fixtures need templating."* → solved by materializing fixtures at load time and rewriting hardcoded resource names with the test's identifier.
- *"Needs a Maven jar fixture."* → solved by vendoring the Java source and letting the builder pod compile it in-cluster.

Each was one investigation step from being unblocked.
The agent had stopped one investigation step short.

> *When the agent says "this is naturally blocked," ask it to defend the deferral with code-path evidence — not a category.
> The categories are usually wrong.*

## When the AI guesses, it stacks heuristics — make it read the source

Around batch seven of the bulk migration, every test that exercised the package-build path started flaking with the same error:

```text
Post "http://nodejs-v2-f206b0-3031.default:8000/fetch":
dial tcp 10.96.236.106:8000: i/o timeout
```

A timing problem, surely.

The agent reached that conclusion four times in a row.
Each fix was more elaborate than the last; all four landed in [PR #3356](https://github.com/fission/fission/pull/3356):

| Attempt | Hypothesis | Fix |
|---|---|---|
| 1 | The runtime pod isn't Ready when the build starts | Auto-wait for one runtime pod |
| 2 | Need the *full* pool, not just one pod | Wait for every pod with `environmentName=<env>` |
| 3 | The pool is up but Service `Endpoints` aren't published | Also poll the env's `Endpoints` object |
| 4 | `Endpoints` is deprecated in K8s 1.33 | Switch to `EndpointSlice` |

Four commits.
Four CI cycles to confirm none of them fixed the flake.
Four wider-and-wider attempts to wait for *some* combination of runtime-pool readiness.

All four were chasing the wrong target.

When the loop finally paused to read the consumer code, sixty lines of `pkg/buildermgr/common.go` settled the question:

```go
// pkg/buildermgr/common.go:57
svcName := fmt.Sprintf("%s-%s.%s", env.Name, env.ResourceVersion, envBuilderNamespace)
fetcherC := fetcherClient.MakeClient(logger, fmt.Sprintf("http://%s:8000", svcName))
```

The fetcher inside the builder pod was POSTing to a *builder Service* — `<env.Name>-<env.ResourceVersion>`.
That Service selects builder pods labeled `envName=<env>`.
The runtime pool, which all four wrong fixes had been waiting for, has a different label entirely (`environmentName=<env>`) and is not even a backend of that Service.

The fix waited for the *builder Service's* EndpointSlice and added a short settle.
It could have been the first attempt, not the fifth.

{{< mermaid >}}
flowchart TD
    S["Symptom: dial tcp ...:8000:<br/>i/o timeout"]:::resource
    S --> H1["Attempt 1: auto-wait runtime pod"]:::process
    H1 --> F1["still flakes"]:::resource
    F1 --> H2["Attempt 2: wait full pool"]:::process
    H2 --> F2["still flakes"]:::resource
    F2 --> H3["Attempt 3: wait for Endpoints"]:::process
    H3 --> F3["still flakes"]:::resource
    F3 --> H4["Attempt 4: switch to EndpointSlice"]:::process
    H4 --> F4["still flakes on K8s 1.28"]:::resource
    F4 --> R["Read pkg/buildermgr/common.go:57<br/>dial target = builder Service,<br/>not runtime pool"]:::leader
    R --> Fix["Fix: wait for builder Service<br/>EndpointSlice + settle"]:::leader

    classDef resource fill:#fb7185,stroke:#be123c,color:#fff
    classDef process fill:#38bdf8,stroke:#0369a1,color:#fff
    classDef leader fill:#10b981,stroke:#047857,color:#fff
{{< /mermaid >}}

The cost of the four wrong commits:

- Four full CI cycles, twelve to fifteen minutes each.
- Working memory polluted with progressively more elaborate timing hypotheses.
- A drop in trust that the loop could debug rather than just react to error strings.

The lesson promoted to memory: *after two failed targeted fixes for the same symptom, stop iterating, grep for the error string, and read the consumer that produces it.*

> *Two failed timing-based fixes are not data about timing; they're data about the wrong model.*

A postscript, kept honest: the same `i/o timeout` race re-emerged on Kubernetes 1.28 once the merge-time CI matrix was restored.
Older `kube-proxy` takes longer to program iptables.
The follow-up fix in [PR #3357](https://github.com/fission/fission/pull/3357) lengthened the post-EndpointSlice settle and retried on the transient build-log signature.
Same diagnosis: read the failure, look at the actual code path, fix the right thing.

## CI is the verification gate, not the agent's claim

Across the migration the agent declared "all done," "the migration is complete," or "natural handoff point" several times.
Each time, more work appeared the moment CI was inspected.

Three habits hardened the gate:

- **Match the merge matrix before declaring done.**
  The branch ran on K8s 1.34 only during iteration; before merge, the matrix was restored to all three versions (1.28, 1.32, 1.34).
  The fetcher race that had been "fixed" actually re-emerged on 1.28.
  That re-emergence is what triggered the postscript fix in the previous section.
- **Read the failures, not the summaries.**
  Multiple `gh run view --log` fetches across the session pulled full job logs when `--log-failed` would have done.
  Token budget burned, signal lost in noise.
  Narrow the failure-inspection step.
- **Distinguish "done" from "shipped."**
  Done = green CI on the merge matrix.
  Shipped = merged.
  The agent often conflates them.

The agent's claim is a hypothesis.
CI is the test.

## Cut the CI loop down for iteration; restore it before merge

The migration branch carried these temporary CI suppressions for the whole iteration window:

- Matrix reduced to K8s 1.34 only.
- CodeQL workflow → `workflow_dispatch` (manual trigger) only.
- Upgrade-test workflow → `workflow_dispatch` only.
- Unit tests + CodeCov upload commented out in `lint.yaml`.
- Fission CLI build/install step skipped — the Go suite runs the CLI in-process.
- Bash integration step (`./test/kind_CI.sh`) commented out.

CI cycle dropped from ~25-30 minutes to ~14-16.
Across seventy commits, that is hours of clock time.

The discipline that kept the suppressions from leaking:

- **Tag every "TEMPORARY" change** with a comment plus a one-line restoration plan pointing at the design doc.
- **Restore in one atomic commit before merge.**
  Every suppression was reverted in [PR #3356](https://github.com/fission/fission/pull/3356) in a single commit, before review.
- **Keep what earned its place.**
  A parallelized image-preload loop in `kind_CI.sh` stayed because it was a real cross-phase improvement, not iteration sugar.

Cutting the CI loop down only works when the restoration moment is explicit.
Otherwise the suppressions silently become permanent.

## Memory turns one session's lessons into the next session's defaults

Claude Code installations expose a `/retrospect` skill that runs at session end.
It classifies findings by tier, requires evidence for every claim, and proposes durable fixes split between *project facts* (CLAUDE.md) and *user preferences* (memory entries the agent reads in future conversations).

Three memory entries landed at the end of this migration:

- **Don't defer tractable work as blocked.**
  Trigger: any "natural stopping point" claim.
  Required action: list what's actually left, defend each deferral with code-path evidence.
- **Read the source before iterating on flakes.**
  Trigger: two failed targeted fixes for the same symptom.
  Required action: stop, grep for the error string, read the consumer.
- **Iteration style for migration work.**
  A user-preference entry: explicit per-item lists over aggregate summaries; overnight `ScheduleWakeup` loops welcome; PR description as final-state ledger, not a checklist.

Each entry has a `Why` (the incident that prompted it) and a `How to apply` (the operational rule).
Without this loop, the next session re-makes the same misjudgments.
With it, the agent's defaults shift toward how the user actually works.

Not everything gets promoted.
The threshold is two occurrences in one session, or explicit user feedback.
Single-occurrence events stay in the session and are forgotten on purpose.

> *Memory entries are the durable artifact; the session itself is the consumable.*

## The PR description is the primary artifact, not the diff

Seventy commits is unreviewable as a diff.
The PR description carries the actual review burden:

- A final-state table of what shipped (test-by-test, with status).
- A "what's deferred to a follow-up PR" section with explicit links.
- An env-gated test catalog with the env vars that activate each.
- Pointers to the four or five commits that capture non-obvious decisions.

Treat the PR description as the deliverable.
Refresh it before review, not after merge.

An honest miss, worth flagging: on this migration the PR description was refreshed once, near the end.
A reviewer landing mid-migration would have seen a Phase-0-only description against a fourteen-batch branch.
The fix is to refresh the description after every meaningful phase, not as a one-shot pre-merge step.

## Summary

Eight habits, restated as a checklist:

1. **Write the spec first.**
   The doc is the contract; it kills scope debates before they happen.
2. **Make every commit atomic and shippable.**
   HEAD always green.
   Any commit can be the resume point.
3. **Schedule the next turn from inside the agent's turn.**
   `ScheduleWakeup` (or an equivalent) is what makes loops survive sleep.
4. **Configure context compaction before the first wakeup.**
   Long sessions fill context fast; a hard restart costs an hour.
5. **After two failed targeted fixes for the same symptom, read the source.**
   Repeated failures are evidence the model is wrong, not the timing.
6. **CI on the merge matrix is the gate.**
   The agent's "done" is a hypothesis; the matrix is the test.
7. **Cut the CI loop down for iteration, then restore it atomically before merge.**
   Suppressions silently leak otherwise.
8. **Promote each session's hard-won lessons into memory entries.**
   Pay for a lesson once.
9. **Treat the PR description as the deliverable.**
   Refresh it after every phase.
   The diff is unreviewable; the description is what reviewers actually read.

That is nine habits, not eight — the autonomous-loop section has two patterns inside it (the loop itself, and context compaction), and they earned separate lines on the checklist.

None of these are Claude-Code-specific.
They apply to any agentic-AI pairing that runs longer than one session — Cursor, Aider, Codex, the next one.

The single thing that mattered most: **always-green HEAD plus a written spec plus verification gates outside the agent**.
The agent is fast at executing, slow at noticing it is wrong.
Process design has to compensate for the second part.

We'd love to hear your thoughts on this post — start a conversation on [LinkedIn](https://www.linkedin.com/in/sanketsudake/).
