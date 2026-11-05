---
name: bug-hunter
description: Use when asked to hunt bugs, audit system stability, find edge-case defects, or perform codebase QA reviews across Python, JS/TS, Go, Java/Kotlin, C#, PHP, or Rust with real test reproductions and verified fixes. (ใช้เมื่อขอให้หาบัค ไล่บัค ตรวจความเสถียร หรือ audit ระบบด้วยการพิสูจน์เทสต์จริง ไม่ใช้แก้บัคเดี่ยวที่รู้สาเหตุแล้ว)
---

# Bug Hunter

Goal: Discover defects **empirically proven through real test execution**, not mere speculation or static suspicion. Deliver a structured Markdown report accompanied by verified regression tests and sandbox-proven unified diffs to harden system stability, without ever modifying host project code or environment during inspection.

**Supreme Principle:** A test that FAILS due to harness or environment breakdown is NOT evidence of a defect. Conversely, a test that PASSES without executing the target code path is NOT evidence of correctness. Adhering to the letter of the rules while violating their intent constitutes a violation.

## Default Parameters
If the user specifies any parameter in their prompt, prioritize their value:
- `MIN_ROUNDS` = 3 — Mandatory rounds; do not stop before completing these (unless coverage saturation occurs in Phase 2).
- `MAX_ROUNDS` = 10 — Hard ceiling when the user chooses to continue beyond the checkpoint.
- `HYPOTHESES_PER_ROUND` = 3–7
- `ATTEMPT_LIMIT` = 3 — Maximum harness repair attempts per hypothesis before concluding INCONCLUSIVE.
- `SCOPE` = Entire project (for large codebases, see Phase 1.4).
- `ROOT` = Project root directory. All commands must execute with ROOT as working directory.
- `S` = `.bughunt/<YYYYMMDD-HHMMSS>/` — Session execution directory (under ROOT).
- **Report Language:** Automatically matches the user's prompt language (e.g., Thai if requested in Thai, English if requested in English). Technical terms (e.g., *race condition*, *off-by-one*, *deadlock*, *memory leak*) remain in standard English.

## Reference Files
- `resources/lang/00-common.md` — **Read Every Run**: Bash/PowerShell translation table, log capture, sandbox cloning, dependency download prevention, harness failure signals, and concurrency testing methodology.
- `resources/lang/<language>.md` — Read only the adapter matching the detected project language: `python.md`, `js-ts.md`, `go.md`, `jvm.md` (Java/Kotlin), `dotnet.md`, `php.md`, `rust.md`.
- `resources/bug-taxonomy.md` — 12-category defect taxonomy checklist for hypothesis generation and confidence validation.
- `resources/report-template.md` — Standard Markdown report template; must be followed strictly.
- `resources/team-mode.md` — Read when operating in multi-agent / subagent mode.

## Identifier & Naming Conventions
- **ID** (used in messages and reports): `R{round}-H{index}`, e.g., `R1-H2`. When referencing previous sessions, format as `<Session_Dir>/R1-H2`.
- **TID** (used in filenames): `r{round}_h{index}`, e.g., `r1_h2` (always lowercase with underscore).
- Test file: `S/tests/test_<TID>_<short_name>.<ext>`
- Log file: `S/logs/<TID>.log`
- Languages requiring specific naming conventions (Go, Java/Kotlin, C#, PHP, Rust) must follow their respective adapter rules while always incorporating the TID.

## Core Rules
1. Execute Phases 0 → 6 sequentially. Never skip, reorder, or collapse phases.
2. Rounds 1–3 must run continuously without asking the user. At the end of Round 3, STOP and prompt the user at the checkpoint (Phase 5). If the user chooses to continue, execute Round 4 onwards until confidence criteria are met or `MAX_ROUNDS` is reached.
3. Outside of designated checkpoints, never prompt the user unless: ROOT cannot be identified, required permissions/credentials are missing, tools attempt internet downloads, or an action violates "Absolute Prohibitions".
4. Prefix each round announcement with `== Round X ==` (in continuation mode: `== Round X/<MAX_ROUNDS> ==`).
5. `S/worklog.md` is the primary execution journal. Update it immediately after proving each hypothesis. The first line must always reflect current status, e.g., `Status: In Progress - Round 2 - R2-H3`.
6. Deliverables must be saved as a physical file at `S/bug-report.md`. Summaries residing solely in chat or ephemeral artifacts do not count as completion.

## Isolated Workspace Rules
```text
.bughunt/
├── .cache/              # Tool caches (deleted upon completion)
└── 20261105-143005/     # = S (one dedicated directory per run)
    ├── bug-report.md    # Primary delivered report
    ├── worklog.md       # Real-time state journal
    ├── tests/           # Standalone reproduction & regression test suite
    ├── logs/            # Raw process execution output = concrete evidence
    ├── tmp/             # Ephemeral data created by tests (deleted upon completion)
    ├── sandbox/         # Project replica for compiled/in-tree languages (deleted upon completion)
    └── sandbox-fix/     # Replica for validating proposed fixes in Phase 6 (deleted upon completion)
```
- Every file created by the agent must strictly reside inside `.bughunt/`. Never place tests inside the host project's test directories.
- Never install, upgrade, or download dependencies into the host environment. Use only pre-installed tools. Refer to `00-common.md` for download prevention flags.
- Tool caches must be disabled or redirected to `.bughunt/.cache/` per the language adapter.
- Languages requiring tests to reside alongside source code (Go), or compiled languages generating build artifacts into source trees (Java/Kotlin, C#), must duplicate the project into `S/sandbox/` per `00-common.md`. Since files in the sandbox are copies, necessary sandbox adjustments (such as fixing relative path references) are permitted.
- Database tests must use SQLite, in-memory instances, or mock databases only. Database files must be created inside `S/tmp/`.
- **Workspace Cleanliness:** At session start, record an initial snapshot in `S/logs/fs-before.txt`. If inside a git repository, run `git status --porcelain --ignored`. If not a git repo, record a file listing with timestamps (commands in `00-common.md`). Compare snapshots at the end of each round.
  - `.bughunt/` will appear as untracked; note in the report that this directory should not be committed (logs may contain sensitive trace data), and suggest adding `.bughunt/` to `.git/info/exclude` with explicit user consent.
  - If new files appear outside `.bughunt/`, delete only safe agent-generated artifacts (`__pycache__`, `.pytest_cache`). Document any remaining items in the report.
  - Never run destructive commands like `git checkout`, `git restore`, `git reset`, `git stash`, or `git clean`, as they risk overwriting uncommitted user work.

## Phase 0 — Locate ROOT & Parse Project Instructions
1. Determine ROOT from the workspace or current working directory. If ambiguous (no active workspace, monorepo with multiple roots, user referencing another directory), ask the user.
2. Perform a case-insensitive search at ROOT and subdirectories within SCOPE for: `agent.md`, `agents.md`, `gemini.md`, `claude.md`, `.cursorrules`, `.github/copilot-instructions.md`, `CONTRIBUTING.md` (skip `.git`, `node_modules`, `.venv`, `venv`, `vendor`, `target`, `.bughunt`).
3. **If found:** Read thoroughly and extract 3–5 bullet points: build/test commands, conventions, forbidden areas, and external dependencies.
4. **If not found:** Output a single line: "No agent instruction file found — skipping Phase 0" and proceed immediately to Phase 1. Do not create these files.
5. Priority order: Absolute Prohibitions & Isolated Workspace Rules > Project Instructions > Default Skill Parameters. If instructions conflict (e.g., instructions demand placing tests in `tests/`), follow this skill's isolation rules and document the divergence under "Project Instruction Conflicts" in the report.

## Phase 1 — Project Exploration & Workspace Preparation
**1.1 Workspace Setup**
- Format `S` using the current timestamp (`date +%Y%m%d-%H%M%S` or `Get-Date -Format yyyyMMdd-HHmmss`). If collision occurs, append `-2`. Create `S/tests/`, `S/logs/`, `S/tmp/`, and `.bughunt/.cache/`.
- Capture initial workspace snapshot per "Workspace Cleanliness".
- If prior sessions exist in `.bughunt/`, review the latest `bug-report.md` and `worklog.md`:
  - Hypotheses previously REFUTED where associated code has not changed since (verified via `git log --since` or file modification times) need not be repeated.
  - Re-run existing CONFIRMED bug tests to verify if they have been resolved. For sandbox-based languages, instantiate a fresh sandbox, restore test files from `<Previous_S>/tests/sandbox/`, and record status as "Fixed" or "Still Active".

**1.2 Codebase Exploration** — Never rely solely on project names or folder structures:
- Read README/docs, package manifests (`pyproject.toml`, `requirements*.txt`, `package.json`, `go.mod`, `pom.xml`, `build.gradle*`, `*.csproj`, `composer.json`, `Cargo.toml`), configs, and `.env.example`.
- Identify language, frameworks, and runtime versions. Read the corresponding adapter in `resources/lang/`.
- Map entry points, primary data flows, and external integration points (DB, cache, message broker, external HTTP APIs, filesystem).
- Audit existing test coverage and identify untested modules.
- Search for `TODO|FIXME|HACK|XXX`. In git repositories, analyze churn hotspots and recent bugfix commits (commands in `00-common.md` section 9), as bugs frequently cluster in churned areas.

**1.3 Baseline Verification** — Execute existing project test suite, linters, and type checkers using cache isolation flags. Pre-existing failures provide immediate leads.
- **Pre-execution Security Check:** Before running baseline tests and Phase 3 verification tests, inspect configs, `.env`, test runners (`conftest.py`), and module-level import side-effects (e.g., `load_dotenv()`, eager DB connection pools). If configurations point to production or external services, override them with environment variables pointing to `S/tmp/` or mock services. If non-production safety cannot be established, STOP and ask the user.
- Compiled languages whose builds write artifacts into project source trees (Java/Kotlin, C#) must run baseline checks inside `S/sandbox/`.
- If baseline cannot run (requires unavailable services, external downloads, or exceeds 10 minutes), restrict execution to relevant Risk Areas and record the rationale.

**1.4 Large Codebases** (>= 50,000 lines of code or complex multi-service monorepos):
- If the user did not specify SCOPE, focus initially on critical paths. Notify the user with a single line regarding the chosen scope (no confirmation wait required), and document out-of-scope modules in the report.
- Partition Risk Areas by module, focusing each round on 1–2 key modules.
- Utilize "Team Mode" (`resources/team-mode.md`) if the host runtime supports subagents.

**Output → Project Map** (Record in `worklog.md` and provide a concise chat summary):
- System summary, languages, frameworks, runtime versions.
- Core modules and architectural dependencies.
- Critical paths (flows where failure causes high business or operational impact).
- Baseline execution commands and results.
- **Risk Areas** categorized by High / Medium / Low risk with rationale, serving as the Coverage Matrix throughout the hunt.

## Phase 2 — Formulate Hypotheses
Formulate `HYPOTHESES_PER_ROUND` hypotheses, ordered by Probability × Impact. Every hypothesis must be **concrete, falsifiable, and directly tied to examined source code**. Leverage language-specific patterns and `resources/bug-taxonomy.md`.

```text
R{round}-H{index}: <Short Name>
- Location: <path:line -> function>
- Hypothesis: <Exact failure mechanism>
- Trigger Condition: <input / state / timing sequence>
- Impact if true: <...>
- Rationale: <Observed code anomaly / git history / baseline failure>
- Proof Plan: <Target test assertion + control test>
- Priority: Probability High|Med|Low x Impact High|Med|Low
```

- **Invalid:** "Billing system might have bugs."
- **Valid:** "R1-H2: `apply_discount()` in `app/billing/discount.py:57` relies on `round(x, 2)`, performing banker's rounding. A value of 0.125 yields 0.12 instead of 0.13. / Proof Plan: Feed amounts ending in half-cents, asserting against `Decimal` with `ROUND_HALF_UP`, alongside a control test for non-rounding amounts."

Never repeat hypotheses recorded in `worklog.md`. Never formulate baseless hypotheses merely to satisfy counts. If fewer than 3 high-confidence hypotheses can be found in a round, proceed with the qualified ones.

**Coverage Saturation:** If 0 meaningful hypotheses remain in a round **AND** all High/Medium Risk Areas have been tested **AND** all applicable categories in `bug-taxonomy.md` have been evaluated, record "Coverage Saturated" with evidence and transition immediately to Phase 5 (or Phase 6 during continuation mode), even if `MIN_ROUNDS` has not been reached. If criteria are unmet, saturation cannot be claimed; hypotheses must be drawn from uninspected Risk Areas or taxonomy categories.

## Phase 3 — Execution & Proof
Investigate each hypothesis sequentially according to priority. **Complete every hypothesis in the current round**; never stop upon discovering the first bug.
1. Trace the complete source execution path. Never infer behavior from function signatures or comments alone.
2. Author test files according to the "Identifier & Naming Conventions" section:
   - Tests must import and invoke **actual project code**. Never copy-paste implementation logic into tests.
   - Tests must assert **correct desired behavior**. When the defect is present, the test must FAIL. When the defect is resolved, the test must PASS, functioning as an immediate regression test.
   - Every test file must contain at least one **control test** passing valid standard input through the target code to establish that harness wiring, imports, and environments are sound.
   - Include header metadata: ID, TID, target (`path:function`), and reproduction command.
   - Mock only external services; never mock the target logic under investigation. Apply execution timeouts to prevent hanging processes.
   - Concurrency / intermittent defects: Follow "Concurrency Testing Methodology" in `00-common.md`. Repeat 50–200 iterations and report as a concrete ratio (e.g., `37/200`).
3. Execute tests per the language adapter, logging raw stdout/stderr to `S/logs/<TID>.log` and appending the process exit code.
4. **Mandatory Harness Validation (Required before declaring verdicts):** Check against "Harness Failure Signals" in `00-common.md`:
   - Number of executed tests must be > 0.
   - Control test must PASS.
   - Failing tests must fail strictly due to assertion failure (mismatched actual vs expected value) or unhandled runtime exceptions emitted by target code—NOT collection errors, import errors, compilation failures, syntax errors, or harness timeouts. (If the defect itself is that the target module cannot be imported, this qualifies, provided the rationale is documented).
   - Verify that mocks have not intercepted the target code.
   - If harness validation fails, repair the harness and re-run (counts as 1 attempt). Upon reaching `ATTEMPT_LIMIT`, fall back to Step 5 or conclude INCONCLUSIVE.
5. If tests cannot physically execute: Trace execution from entry point to target location, citing `file:line` for every stage to demonstrate reachability, and document why execution was impossible.
6. Conduct self-refutation: Search for upstream validation, middleware guards, or framework-level constraints that neutralize the bug in production.
7. Conclude verdict and update `S/worklog.md` immediately.

| Verdict | Definition |
|---|---|
| CONFIRMED | Concrete evidence demonstrates defect is reachable and reproducible, verified by harness validation. |
| REFUTED | Evidence proves defect cannot manifest (e.g., verified test PASS under trigger conditions, or upstream guard identified at `file:line`). |
| INCONCLUSIVE | Neither condition could be proven. Document missing prerequisites and requirements for future resolution. |

**Evidence Levels:** E1 Reproduced (Test fails visibly with concrete output) > E2 Runtime (Demonstrated via runtime logs) > E3 Static Trace (Complete execution path traced with `file:line`).
- CONFIRMED requires E1 by default. E2/E3 is permitted only when test execution is technically blocked, with reasons documented.

**Severity Levels** (for CONFIRMED):
- **Critical:** Data loss/corruption, security vulnerabilities, or complete system crash on core paths.
- **High:** Primary feature malfunctions under normal operating conditions.
- **Medium:** Occurs in edge cases or has viable workarounds.
- **Low:** Minor cosmetic impact or extremely improbable conditions.

```text
R1-H2 -> CONFIRMED (E1) | High
- Test: S/tests/test_r1_h2_discount_rounding.py -> bug test FAIL (3/3 cases), control test PASS
- Harness: 4 tests ran, failed on AssertionError (0.12 != 0.13), exit=1
- Evidence: S/logs/r1_h2.log — <relevant output lines>
- Root Cause: <True underlying cause, not just symptom>
- Proposed Fix: <Recommendation>
```

## Phase 4 — Round Summary & Branching Decision
1. Compile round summary table (`ID | Hypothesis | Verdict | Evidence | Severity`) into `S/worklog.md` and output a concise chat summary.
2. Update Coverage Matrix indicating which Risk Areas have been evaluated.
3. Evaluate the 5 Confidence Criteria and log findings.
4. Determine the next step according to the decision table:

| Scenario | Next Action |
|---|---|
| End of Round 1 or 2 | Proceed to Phase 2 for next round. Do not stop even if confidence criteria are met (unless coverage saturation occurred). |
| End of Round 3 | Proceed to Phase 5 (Checkpoint). |
| Continuation Mode: All 5 Confidence Criteria met | Proceed to Phase 6. |
| Continuation Mode: Reached user-specified round limit or `MAX_ROUNDS` | Proceed to Phase 6 immediately. |
| Continuation Mode: Other conditions | Proceed to Phase 2 for next round. |

**Subsequent hypotheses must build upon prior results, not random guessing:**
- **Sibling Bugs:** Scan the codebase for identical anti-patterns to CONFIRMED bugs.
- **Root Cause Propagation:** Does the same root cause affect adjacent modules?
- **Upstream / Downstream Impact:** Who invokes the defective code, and where does invalid state propagate?
- **Near-Misses:** Hypotheses REFUTED by guards—is the guard completely airtight, or can it be bypassed?
- **Uninspected Areas:** Risk Areas or taxonomy categories still lacking coverage.
- **INCONCLUSIVE Follow-up:** Re-attempt proof using alternative harnesses or mocks.
- **Interaction Defects:** Asynchronous sequences, retries, double submits, and partial failures.

## Confidence Criteria
Passes only when ALL 5 items are satisfied:
- [ ] Every High and Medium Risk Area has been tested by at least 1 hypothesis.
- [ ] Last 2 consecutive rounds produced no new CONFIRMED bugs with **novel root causes** (sibling bugs sharing an existing root cause do not reset this count, but must be documented).
- [ ] No unresolved INCONCLUSIVE hypotheses with potential High or Critical severity remain.
- [ ] Every CONFIRMED bug has been scanned for sibling bugs across the codebase.
- [ ] All applicable categories in `bug-taxonomy.md` have been evaluated (or marked irrelevant with rationale).

Meeting criteria signifies: *"No further defects detected within audited scope."* Never claim *"The system is bug-free."*

## Phase 5 — Checkpoint After Round 3 (Mandatory Stop)
1. Generate draft report at `S/bug-report.md` marked with status: `Status: Interim Draft — Awaiting User Decision`.
2. Update first line of `S/worklog.md` to: `Status: Awaiting User Decision after Round 3`.
3. Present the following structured notification and **stop execution to wait for user reply**. Do NOT proceed to Round 4 autonomously:

```text
Mandatory 3 rounds completed.
- Hypotheses: N tested | Confirmed Bugs: N (Critical: a / High: b / Med: c / Low: d) | Inconclusive: N
- Highest Severity Bug: <ID — Name>
- Confidence Criteria: Passed X/5 — Unmet: <...>
- Interim Report: <path to bug-report.md>

Recommendation: <Continue | Stop> because <rationale>

How would you like to proceed?
1) Continue iterating until confident (up to <MAX_ROUNDS> rounds, then report).
2) Stop and finalize the comprehensive report now.
(You may specify particular modules or concerns to prioritize).
```

4. Upon user response:
   - **User selects 1:** Update `worklog.md` and execute Round 4 onwards autonomously without further interruptions until exit criteria in Phase 4 table are met. (If user specifies a round limit, honor it up to `MAX_ROUNDS`).
   - **User selects 2:** Proceed directly to Phase 6.
   - **User provides focus areas:** Prioritize specified areas in the subsequent round.
   - **Ambiguous response:** Prompt briefly for clarification.
5. If the user previously gave advance instructions (e.g., "Run until confident without asking"), bypass pausing, but still generate the interim draft report.

## Phase 6 — Final Report & Sandbox Verification
1. Re-generate `S/bug-report.md` following `resources/report-template.md`. Complete all sections; write "None" where data is absent. Never delete template sections.
2. Every CONFIRMED bug must include reproduction steps, root cause analysis, **unified diff of proposed fix**, side-effect analysis, and regression test reference.
3. **Sandbox Fix Verification** (Perform for all confirmed defects where feasible):
   - Duplicate project into `S/sandbox-fix/` per `00-common.md`. Replicate test files at their relative paths (`S/sandbox-fix/.bughunt/<Session_Name>/tests/`).
   - Apply the unified diff for each bug. Run the corresponding test inside `S/sandbox-fix/`: verify that the bug test turns from FAIL to PASS while the control test remains PASS.
   - Once all diffs are applied, execute the complete test suite and project baseline inside sandbox-fix to verify absence of regressions.
   - Record fix status for each bug as "Verified in Sandbox" or "Unverified — <reason>".
4. State termination rationale: User stopped / Confidence criteria met / Coverage saturated / Round limit reached. If terminated without meeting confidence criteria, explicitly list unmet points and recommended next steps.
5. Workspace Cleanup: Copy tests written inside `S/sandbox/` to `S/tests/sandbox/<original_relative_path>`. Delete `S/sandbox/`, `S/sandbox-fix/`, `S/tmp/`, and `.bughunt/.cache/`. Perform final workspace cleanliness check.
6. Report Quality Check: Validate file paths and line numbers, verify reproduction commands, sanitize secrets (mask as `sk-****`), and ensure valid Markdown table formatting.
7. Conclude in chat with summary statistics, top 3 critical defects, report file path, and ask the user which bug they would like to resolve.

## Defect Resolution (After Report Delivery & User Approval Only)
- Fix one defect at a time based on user selection, applying the sandbox-verified diff.
- Verify that the regression test in `S/tests/` transitions from FAIL to PASS and that the host project baseline passes.
- Regression tests remain in `.bughunt/` until the user explicitly requests moving them into project test directories.
- Append resolution entry to "Bugfix Log" at the end of `bug-report.md`.

## Resuming Prior Sessions
If resuming in a new conversation or following context compaction, read `worklog.md` from the latest session folder in `.bughunt/` and resume from the recorded state. Never start over or duplicate past hypotheses.

## Team Mode (Optional for Large Projects with Subagents)
When running on runtimes supporting subagents, delegate individual hypothesis verification (Phase 3) while the primary agent coordinates Phases 0–2 and 4–6. The primary agent is the sole writer of `worklog.md` and `bug-report.md`, and **must independently inspect raw logs to validate harness integrity before accepting verdicts**. See `resources/team-mode.md`.

## Absolute Prohibitions
- NEVER modify host project source code, configuration files, dependencies, or lockfiles prior to explicit user approval.
- NEVER install, upgrade, or download packages into host environments. Stop and ask if a tool requires internet fetching.
- NEVER execute destructive commands (e.g., `rm -rf` outside `.bughunt/`, `DROP`/`TRUNCATE`, `git reset --hard`, `git clean`, `git push --force`, database migrations on live instances, production deployments).
- NEVER contact production environments or execute side-effecting external APIs (SMS, payments, live webhooks).
- NEVER fabricate evidence, alter execution logs, or claim tests ran without verified execution.
- NEVER classify pure code style or linter warnings as bugs unless they produce provably incorrect runtime behavior.
- NEVER display secrets, API keys, or credentials in chat or reports.

## Warning Signs — If You Catch Yourself Thinking This, STOP:
| Rationalization | Reality |
|---|---|
| "The test failed, so I found a bug." | Validate the harness first. An ImportError or missing module also outputs FAIL. |
| "The test passed, so no bug exists." | Verify that tests executed (>0) and target functions were not mocked out. |
| "Installing one small package won't hurt." | Modifying host environment is forbidden. Use existing tools or ask the user. |
| "Out of ideas for this round; I'll make something up." | Check coverage saturation criteria or explore uninspected Risk Areas. |
| "This fix is trivial; I'll just patch the file now." | Modifying project code before approval is strictly prohibited. Use sandbox-fix. |
| "A summary in chat is sufficient." | A formal physical deliverable at `S/bug-report.md` is mandatory. |
| "Race test passed 200 runs; no race exists." | Without latency between read and write, threads rarely interleave. Introduce simulated collaborator latency per `00-common.md` before concluding. |
