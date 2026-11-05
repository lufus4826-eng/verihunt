# Team Mode (Multi-Agent Dispatch)

An optional coordination strategy for large codebases when running on agent runtimes that support subagents. Conserves the primary agent's context window and enables parallel hypothesis verification.

## Role Distribution
- **Primary Agent:** Coordinates Phases 0–2 and 4–6. Acts as the sole author of `worklog.md` and `bug-report.md`.
- **Subagents:** Investigate and prove one hypothesis per subagent (Phase 3).

## Subagent Dispatch Brief
When dispatching a subagent for a hypothesis, provide:
1. Complete hypothesis card (per Phase 2 format).
2. Explicit values for `ROOT`, `S`, `SNAME`, and `TID`.
3. Path to `SKILL.md` with instructions to read: "Supreme Principle", "Identifier & Naming Conventions", "Isolated Workspace Rules", "Phase 3 (Execution & Proof)", "Absolute Prohibitions", and "Warning Signs".
4. Path to `resources/lang/00-common.md` and the detected language adapter.
5. Pre-execution security constraints from Phase 1.3 (environment variables requiring override, sensitive services to avoid).
6. Required response format: The structured verdict block from Phase 3 (Verdict, Evidence Level, Severity, Test File, Harness Validation result, Log Path, Root Cause, Proposed Fix). Subagents must never dump raw logs into the return message.

## File Writing Boundaries for Subagents
- May write strictly to: `S/tests/*<TID>*` and `S/logs/<TID>*`.
- In sandbox environments, subagents may only add test files containing their own TID in the filename. They must never modify existing files in the sandbox copy. (If source modifications like `InternalsVisibleTo` are required, request the primary agent to make the adjustment).
- Subagents must NEVER write to `worklog.md` or `bug-report.md`.

## Verdict Acceptance Protocol
- **The primary agent MUST inspect the raw log (`S/logs/<TID>.log`) and independently validate harness integrity before accepting any CONFIRMED or REFUTED verdict.** Never accept verdicts based solely on subagent summary text.
- If harness validation data is missing or invalid, reject the subagent's response and request remediation.

## Concurrency Guidelines
- Interpreted languages without sandbox duplication (Python, JS/TS, PHP) can run subagent proofs concurrently, as each operates in its own test and log files.
- Compiled languages sharing a common sandbox (Go, Java/Kotlin, C#, Rust) must execute build and test commands sequentially to prevent output directory lock contention.
