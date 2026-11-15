# Team Mode (Multi-Agent Dispatch — Lazy-Loaded for >=50k LOC)

Optional strategy for large codebases when runtime supports subagents.

## Role Distribution & Persistent Workers
- **Primary Agent:** Runs Phases 0–2 and 4–6; sole writer of `S/worklog.md` and `S/bug-report.md`.
- **Persistent Module Workers (Mandatory Pattern):** Spawn **1 worker per module/risk-area** and reuse it across rounds (via `send_message` on persistent-agent runtimes) rather than spawning cold single-hypothesis subagents every round (eliminates repeated recon and source re-reads).

## Non-Polling & Digest Verification Guardrails (Mandatory)
1. **Never Poll:** NEVER call `manage_subagents`, `manage_task`, `schedule`, or sleep loops to check worker progress. After dispatching workers, end your turn (or perform independent non-conflicting work) and wait for reactive wakeup notifications.
2. **Zero Skill Reloads:** Do NOT tell subagents to read `SKILL.md`, `00-common.md`, or adapters. Provide the compact inline brief below instead.
3. **Deterministic Verdict Verification (No Source/Log Re-Read Spam):**
   - Primary MUST independently verify harness integrity before accepting `CONFIRMED` or `REFUTED`.
   - Run `python "<BH>" check --s "$S" --tid <TID>` (or `--round N`) to verify `ran > 0`, `control: PASS`, and zero §7 breakdown signals.
   - Read ONLY the test file's assertions/control test (`StartLine`/`EndLine` <=150L) if needed to confirm target code is invoked without mocks replacing target logic.
   - **Do NOT** dump full `S/logs/<TID>.log` or re-read already-verified project source files repeatedly; reject and ask the worker to fix if `bh.py check` shows `HARNESS_BROKEN` or missing control test.

## Compact Subagent Dispatch Brief Template
Send ONLY this compact brief per task (~25 lines):
```text
Task: Prove hypothesis <ID> (TID=<TID>) in Phase 3.
Paths: ROOT=<ROOT> | S=<S> | SNAME=<SNAME> | BH=<BH>
Hypothesis Card: <ID: Name | Loc: path:line->fn | Mechanism | Trigger | Proof Plan>
Security Overrides: <Env vars to force S/tmp/ or mocks; forbidden live endpoints>
Language/Concurrency Rules: <filename pattern, offline/sandbox flags, 1-5ms race latency if async/race>
Rules:
1. Read ONLY needed target lines via grep + ranged read_file (<=150 lines); never dump whole files.
2. Write test strictly inside <S>/tests/ (or <S>/sandbox/... for Go/JVM/C#/Rust) naming TID (<TID>).
   Must import real project code, assert desired behavior (FAIL=bug, PASS=fixed), include >=1 control test (`test_control_*`/`Control_*`), mock external services only, and use timeouts.
3. Execute via: python "<BH>" run --s "<S>" --tid "<TID>" -- <cmd>
   Repair up to 3 attempts only if digest shows HARNESS_BROKEN/TIMEOUT/EXEC_ERROR/control!=PASS.
   Perform self-refutation check for upstream guards (`file:line`).
4. Write ONLY <S>/tests/*<TID>* and <S>/logs/<TID>*. NEVER touch host files, worklog.md, or bug-report.md (nor existing sandbox source files; ask primary if e.g. InternalsVisibleTo is needed).
5. Return ONLY this <15-line verdict (NO raw logs):
   ID: <ID> | TID: <TID> | Verdict: CONFIRMED|REFUTED|INCONCLUSIVE | Evidence: E1|E2|E3 | Severity: Crit|High|Med|Low
   Test: <path> | Digest: ran=X passed=Y failed=Z control=PASS|FAIL exit=N
   Root Cause / Guard: <1-2 lines with file:line>
   Proposed Fix: <concise diff/recommendation or "None">
```

## Concurrency Guidelines
- **Interpreted / non-sandbox languages (Python, JS/TS, PHP):** Workers may run tests concurrently (isolated test and log files).
- **Compiled shared-sandbox languages (Go, Java/Kotlin, C#, Rust):** Serialize build/test executions (or run `bh.py round --parallel 1`) to avoid build output lock contention.
