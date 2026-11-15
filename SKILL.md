---
name: verihunt
description: Use when asked to hunt bugs, audit system stability, find edge-case defects, or perform codebase QA reviews across Python, JS/TS, Go, Java/Kotlin, C#, PHP, or Rust with real test reproductions and verified fixes. (ใช้เมื่อผู้ใช้ขอให้หาบัค ไล่บัค ตรวจความเสถียร หรือ audit ทั้งระบบหรือทั้งโมดูล และต้องการบัคที่พิสูจน์ด้วยการรันจริงพร้อมรายงานวิธีแก้ ไม่ใช้กับบัคเดี่ยวที่รู้สาเหตุแล้ว — bug hunt, find bugs, stability audit, QA review, hardening)
---

# VeriHunt

Goal: Find defects **empirically proven via real test execution** (not speculation). Deliver `S/bug-report.md` with regression tests and sandbox-verified unified diffs without modifying host code, configs, or environment during inspection.

**Supreme Principle:** A test FAIL caused by harness/environment breakdown is NOT a bug. A test PASS that never executes target code is NOT correctness. Obeying the letter of rules while violating intent is a violation.

## Default Parameters (User prompt overrides)
`MIN_ROUNDS=3` (mandatory unless Phase 2 Coverage Saturation) | `MAX_ROUNDS=10` | `HYPOTHESES_PER_ROUND=3-7` | `ATTEMPT_LIMIT=3` (harness repairs before Step 5/`INCONCLUSIVE`) | `SCOPE=Entire project` (`>=50k` LOC -> Phase 1.4) | `ROOT=Project root` (all cmds run from `ROOT`) | `S=.bughunt/<YYYYMMDD-HHMMSS>/` | `BH=<skill_dir>/scripts/bh.py` (resolve `<skill_dir>` from this file's dir) | **Report Language:** Auto-match user prompt language (Thai if prompted in Thai, English if prompted in English; keep standard technical terms like *race condition*, *off-by-one*, *deadlock*, *memory leak*, *IDOR*, *SQL injection* in English). Write user-facing chat, `S/worklog.md`, Phase 5 prompt, and `S/bug-report.md` in the matched language.

## Token Efficiency Rules (Mandatory)
1. **Grep-First & Ranged Reads:** Locate symbols via `rg`/`grep`/`Select-String` first, then `read_file` with `StartLine`/`EndLine` (`<=150` lines/call). Never dump whole source files, never re-read unchanged lines already in context, and **never** use shell `Get-Content`/`cat`/`type`/`Select-String` to dump source files or `.bughunt/logs/*.log`.
2. **CLI-First (`scripts/bh.py`):** Use `python "<BH>"` (`init`, `recon`, `run`, `round`, `check`, `log`, `sandbox`) for setup, recon, test runs, log digests, worklog updates, and sandboxes. Rely on `bh.py`'s `<=12`-line digest; **never** read full `S/logs/*.log` (read only specific failure lines via `StartLine`/`EndLine` for Phase 6 snippets). Avoid ad-hoc `python -c`/`node -e` probes when reading or a test suffices.
3. **Batch Round Execution:** In Phase 3, trace target paths, write **all** round test files in parallel tool calls in one turn, then run `python "<BH>" round --s "$S" --round N` once. Repair only `HARNESS_BROKEN`/`TIMEOUT`/`EXEC_ERROR` (or failed `control`) tests.
4. **Append-Only Worklog:** Never rewrite or re-read full `S/worklog.md`. Update line-1 `Status:` and append entries via `python "<BH>" log --s "$S" --status "..." --entry "..."` (repeatable `--entry` or `--entry-file`).
5. **Lazy-Load Heavy Docs & Single Final Report:** Read **ONLY** `resources/report-template-th.md` (if Thai) or `resources/report-template.md` (if English) **in Phase 6** (never load both!). At Phase 5 checkpoint, write a compact `<=25`-line interim summary to `S/bug-report.md` (not the 9-section template). Read `resources/team-mode.md` ONLY in Phase 1.4 when dispatching subagents.

## Reference Files (Lazy-Load by Phase)
- `scripts/bh.py` — Cross-platform helper CLI.
- `resources/lang/00-common.md` — Phase 1: offline rules, §3 harness signals, §4 concurrency methodology, §5 sandbox notes.
- `resources/lang/<lang>.md` — Phase 1: load **only** matching language(s) (`python`, `js-ts`, `go`, `jvm`, `dotnet`, `php`, `rust`).
- `resources/bug-taxonomy.md` — Phase 2: 12-category defect checklist.
- `resources/report-template.md` — **Phase 6 ONLY (English):** full 9-section report structure.
- `resources/report-template-th.md` — **Phase 6 ONLY (Thai):** full Thai 9-section report structure.
- `resources/team-mode.md` — **Phase 1.4 ONLY**: large-repo multi-agent rules.

## ID & Naming Conventions (`bh.py round` auto-discovery)
- **ID** (reports/msgs): `R{round}-H{index}` (`R1-H2`; cross-session: `<Session_Dir>/R1-H2`) | **TID** (files): `r{round}_h{index}`.
- **Tests:** `S/tests/test_<TID>_<name>.<ext>` (Python/JS/TS) | `S/tests/BugHuntR{round}H{index}<Name>Test.php` (PHP) | inside `S/sandbox/`: `bughunt_<TID>_test.go`, `BugHuntR{round}H{index}<Name>Test.java|.kt`, `BugHuntR{round}H{index}<Name>Tests.cs`, `tests/bughunt_<TID>.rs`.
- **Logs:** `S/logs/<TID>.log` (`<TID>_fix.log` in Phase 6).

## Core Rules & Isolated Workspace
1. Execute Phases `0 -> 6` sequentially; never skip, reorder, or collapse phases.
2. Run Rounds 1–3 without prompting; STOP at Phase 5 checkpoint after Round 3. In continuation mode, run Round 4..`MAX_ROUNDS` until Confidence Criteria or limit is met. Never prompt outside checkpoints unless `ROOT` ambiguous, missing creds/perms, internet download needed, Phase 1.3 safety unverified, or Absolute Prohibitions triggered.
3. Prefix round updates with `== Round X ==` (EN) or `== รอบที่ X ==` (TH) (continuation: `== Round X/<MAX_ROUNDS> ==` / `== รอบที่ X/<MAX_ROUNDS> ==`). Log verdicts immediately via `bh.py log`. Physical `S/bug-report.md` is mandatory (chat/artifacts don't count).
4. **Isolation (`.bughunt/`):** All agent files live strictly in `.bughunt/.cache/` and `S/` (`bug-report.md`, `worklog.md`, `tests/`, `logs/`, `tmp/`, `sandbox/`, `sandbox-fix/`). Never write tests in host test dirs, never install/download packages, redirect/disable caches (`bh.py` does this automatically), duplicate Go/JVM/C#/Rust into `S/sandbox/` (relative path fixes permitted in sandbox copy only), and put SQLite/test DBs in `S/tmp/` only (or use in-memory/mocks).
5. **Cleanliness:** `bh.py init` snapshots `fs-before.txt`; `bh.py sandbox --mode clean` cleans temp/cache/sandbox dirs, removes safe untracked `__pycache__`/`.pytest_cache` outside `.bughunt/`, and diffs `fs-after.txt`. Document any remaining external files. Warn that `.bughunt/` shouldn't be committed (logs may hold sensitive traces); add to `.git/info/exclude` only with explicit user approval. **NEVER** run `git checkout|restore|reset|stash|clean`.

## Phase 0 — Locate ROOT & Project Instructions
1. Resolve `ROOT` from workspace/cwd (ask if ambiguous).
2. Case-insensitive search at `ROOT`/SCOPE (`bh.py recon` checks these) for `agent.md`, `agents.md`, `gemini.md`, `claude.md`, `.cursorrules`, `.github/copilot-instructions.md`, `CONTRIBUTING.md` (skip `.git`, `node_modules`, `.venv`, `venv`, `vendor`, `target`, `.bughunt`).
3. If found: read (ranged) and extract 3–5 bullets (build/test cmds, conventions, forbidden areas, external deps). If none: print `"No agent instruction file found — skipping Phase 0"` (EN) or `"ไม่พบไฟล์คำสั่งสำหรับ agent — ข้ามขั้นนี้"` (TH) and proceed (never create them).
4. Precedence: `Absolute Prohibitions & Isolation > Project Instructions > Skill Defaults`. Record divergences under `"Project Instruction Conflicts"` (EN) or `"ข้อขัดแย้งกับไฟล์คำสั่งของโปรเจกต์"` (TH).

## Phase 1 — Exploration & Workspace Prep
- **1.1 Setup:** Run `python "<BH>" init --root .` -> get JSON `{S, SNAME, CACHE, ROOT, snapshot, prior_sessions}`. If prior sessions exist, inspect only latest `bug-report.md`/`worklog.md` (ranged): skip unchanged `REFUTED` items (`git log --since`/mtime) and re-run prior `CONFIRMED` tests (restoring `<Prev_S>/tests/sandbox/` into fresh `S/sandbox/` if needed) -> record `"Fixed"`/`"Still Active"` (EN) or `"แก้แล้ว"`/`"ยังอยู่"` (TH).
- **1.2 Recon:** Run `python "<BH>" recon --root .` (`<=35`-line map: languages, manifests, entrypoints, tests, LOC, TODOs, git churn/fixes). Read README/manifests/configs/`.env.example` (ranged `<=150`L). Read `resources/lang/00-common.md` and ONLY matching `resources/lang/<lang>.md`. Map entry points, data flows, external integrations, and untested modules.
- **1.3 Baseline & Pre-Execution Security Check:** Before running ANY test, inspect configs, `.env`, `conftest.py`/test hooks, and import-time side effects (`load_dotenv()`, eager DB pools). Override external/live targets to `S/tmp/` or mocks via env vars; if non-production safety is uncertain, STOP and ask user (in Report Language). Run existing suite/linters/type-checkers via `python "<BH>" run --s "$S" --tid baseline -- <cmd>` (inside `S/sandbox/` via `--cwd "$S/sandbox"` for JVM/C#). If blocked (missing services, downloads, >10m), scope to Risk Areas and document why.
- **1.4 Large Codebases (`>=50k` LOC / monorepo):** If `SCOPE` unset, focus on critical paths, notify user in 1 line (no wait), list out-of-scope modules in report. Partition Risk Areas (1–2 modules/round); load `resources/team-mode.md` if using subagents.
- **Output -> Project Map:** Append Project Map (summary, stack/versions, modules, critical paths, baseline cmd/results, Risk Areas H/M/L = Coverage Matrix) via `bh.py log --s "$S" --status "In Progress - Round 1"` (TH: `"กำลังทำรอบที่ 1"`) and summarize briefly in chat (matching Report Language).

## Phase 2 — Formulate Hypotheses
Load `resources/bug-taxonomy.md`. Formulate `HYPOTHESES_PER_ROUND` (3–7) ordered by `Probability x Impact`, tied to inspected source code (`path:line -> fn`):
`R{r}-H{i}: <Name> | Loc: <path:line->fn> | Priority: Prob H|M|L x Imp H|M|L | Hyp: <mechanism> | Trigger: <input/state/timing> | Impact: <...> | Rationale: <anomaly/git/baseline> | Proof: <target assert + control>`
- Invalid: *"Billing has bugs."* | Valid: *"R1-H2: `apply_discount()` (`app/billing/discount.py:57`) uses banker's `round(x,2)`; `0.125` gives `0.12` not `0.13`. Proof: half-cents vs `ROUND_HALF_UP` + whole-cent control."*
- Never repeat `worklog.md` hypotheses or pad without evidence (<3 qualified is fine).
- **Coverage Saturation:** If `0` meaningful hypotheses remain AND all High/Med Risk Areas tested AND all applicable `bug-taxonomy.md` categories evaluated -> log `"Coverage Saturated"` (TH: `"coverage อิ่มตัว"`) + evidence -> go to Phase 5 (or Phase 6 in continuation), even before `MIN_ROUNDS`. Otherwise cannot claim saturation.

## Phase 3 — Execution & Proof (Batch Round)
Complete ALL hypotheses in the round (never stop on first bug).
1. **Trace Path:** Grep + ranged `read_file` (`<=150`L) along full execution path; never infer from signatures/comments.
2. **Batch Write Tests:** Write all round test files in **parallel tool calls in one turn**. Every test MUST: import & invoke real project code (never copy logic), assert desired correct behavior (FAIL=bug, PASS=fixed), include `>=1` passing `control` test (`test_control_*`/`Control_*`), include header (`ID`, `TID`, `Target`, `Run`), mock ONLY external services (never target logic), and enforce timeouts. Concurrency: follow `00-common.md` §4 (barrier/latch, 1–5 ms collaborator latency, 50–200 runs, `k/N` ratio).
3. **Batch Execute:** Run `python "<BH>" round --s "$S" --round N` (or `bh.py run --s "$S" --tid <TID> -- <cmd>` for custom args).
4. **Harness Validation:** Digest must show `ran > 0`, `control: PASS`, zero §7 signals (`ALL_PASS` or `VALID_BUG_FAIL`), and no target mocks. Repair ONLY failed harnesses (`--tids ...` or `bh.py run`) up to `ATTEMPT_LIMIT=3`; at limit, use Step 5 or declare `INCONCLUSIVE`.
5. **Static Fallback (when unrunnable):** Trace entry -> target citing `file:line` per hop; document blocker.
6. **Self-Refutation:** Search upstream validation, middleware guards, or framework constraints neutralizing the bug.
7. **Verdict & Log:** `CONFIRMED` (reachable + reproducible + valid harness) | `REFUTED` (verified PASS under trigger, or guard at `file:line`) | `INCONCLUSIVE` (missing prereqs). **Evidence:** `E1` Reproduced (required for `CONFIRMED` unless execution technically blocked with documented reason) > `E2` Runtime > `E3` Static trace. **Severity:** `Critical` (data loss/security/core crash) | `High` (core feature broken) | `Medium` (edge case/workaround) | `Low` (minor/rare). Append verdicts via `bh.py log --s "$S" --status "In Progress - Round N"` (TH: `"กำลังทำรอบที่ N"`) `--entry "..."` (`ID -> VERDICT (E1) | Severity | Test | Harness | Log | Root Cause | Fix`).

## Phase 4 — Round Summary & Branching
1. Append round table (`ID | Hypothesis | Verdict | Evidence | Severity`), Coverage Matrix updates, and 5 Confidence Criteria status via `bh.py log`; summarize concisely in chat (matching Report Language).
2. **Decision:** R1/R2 -> Phase 2 (no early stop except Saturation) | R3 -> Phase 5 | Continuation: 5/5 Confidence met OR round limit/`MAX_ROUNDS` -> Phase 6; else -> Phase 2.
3. **Chaining Next Round:** Sibling Bugs (same anti-pattern codebase-wide), Root Cause Propagation, Upstream/Downstream Impact, Near-Misses (bypassable guard?), Uninspected Risk/Taxonomy Areas, `INCONCLUSIVE` Follow-up, Interaction Defects (async ordering/retries/double-submit/partial fail).

## Confidence Criteria (All 5 Must Pass)
- [ ] Every High/Med Risk Area tested by `>=1` hypothesis.
- [ ] Last 2 consecutive rounds found no new `CONFIRMED` bugs with **novel root causes** (siblings sharing an existing root cause don't reset count, must be documented).
- [ ] No unresolved High/Critical `INCONCLUSIVE` hypotheses.
- [ ] Every `CONFIRMED` bug scanned for sibling bugs codebase-wide.
- [ ] All applicable `bug-taxonomy.md` categories evaluated (or marked irrelevant with rationale).
Passing = *"No further defects detected within audited scope."* (TH: *"ไม่พบบัคเพิ่มภายในขอบเขตที่ตรวจ"*) — NEVER claim *"The system is bug-free."* / *"ระบบไม่มีบัค"*.

## Phase 5 — Checkpoint After Round 3 (Mandatory Stop)
1. Write a **compact interim summary** (`<=25` lines, matching Report Language) to `S/bug-report.md` (`Status: Interim Draft — Awaiting User Decision` / `สถานะรายงาน: ฉบับระหว่างทาง — รอผู้ใช้ตัดสินใจ`, metrics, top bugs, compact `ID | Verdict | Evidence | Severity | Summary` table, Confidence `X/5`) — **do NOT load `report-template*.md` yet**.
2. Run `python "<BH>" log --s "$S" --status "Awaiting User Decision after Round 3"` (TH: `"รอผู้ใช้ตัดสินใจหลังรอบที่ 3"`).
3. Output ONLY the prompt matching Report Language and **STOP for user reply** (if user pre-authorized continuation e.g. `"run until confident without asking"` / `"วนจนมั่นใจเลย ไม่ต้องถาม"`, still write compact interim draft and proceed):
```text
# English:
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
```text
# Thai (ภาษาไทย):
ครบ 3 รอบบังคับแล้ว
- สมมติฐาน: N ข้อ | บัคที่ยืนยัน: N (Critical a / High b / Medium c / Low d) | ยังสรุปไม่ได้: N
- บัคที่ร้ายแรงที่สุด: <ID — ชื่อ>
- เกณฑ์ความมั่นใจ: ผ่าน X/5 — ข้อที่ยังไม่ผ่าน: <...>
- รายงานฉบับระหว่างทาง: <path ของ bug-report.md>

คำแนะนำ: <วนต่อ | หยุด> เพราะ <เหตุผล>

ต้องการให้ทำต่ออย่างไร
1) วนต่อจนกว่าจะมั่นใจ (ทำต่อได้ถึงรอบที่ <MAX_ROUNDS> แล้วรายงาน)
2) หยุด และทำรายงานฉบับสมบูรณ์
ระบุจุดที่อยากให้เน้นเพิ่มได้
```
4. Reply: `1` -> update status & run R4..`MAX_ROUNDS` autonomously until Phase 4 exit (honor custom limit `<=MAX_ROUNDS`); `2` -> Phase 6; focus areas -> prioritize; ambiguous -> clarify briefly (in Report Language).

## Phase 6 — Final Report & Sandbox Verification
1. **Lazy-load ONLY the matching report template now:** `resources/report-template-th.md` (if Thai) or `resources/report-template.md` (if English) — never load both.
2. **Sandbox Fix Verification** (for all `CONFIRMED` bugs where feasible): `bh.py sandbox --s "$S" --mode fix` -> apply unified diffs in `S/sandbox-fix/` -> `bh.py round --s "$S" --all --fix` (all `CONFIRMED` tests turn FAIL->PASS, controls stay PASS) -> run project baseline in `S/sandbox-fix/` (`bh.py run --s "$S" --tid baseline_fix --cwd "$S/sandbox-fix" -- <cmd>`) for regression check -> mark `"Verified in Sandbox"`/`"Unverified — <reason>"` (TH: `"ยืนยันใน sandbox"`/`"ยังไม่ยืนยัน — <เหตุผล>"`).
3. Write `S/bug-report.md` completely **once** per the loaded template (all 9 sections; `"None"`/`"ไม่มี"` if empty; never delete sections). Include repro cmd, root cause, unified diff, side-effects, sibling audit, regression test link, targeted failure snippet (`StartLine`/`EndLine` from `S/logs/<TID>.log`), termination rationale, and any unmet confidence criteria.
4. **Cleanup:** Run `bh.py sandbox --s "$S" --mode clean` (run `gradlew --stop` first if Gradle used). Report any remaining external files; remind user `.bughunt/` shouldn't be committed (logs may hold sensitive traces) & offer `.git/info/exclude` with explicit approval.
5. **Quality Check & Handoff:** Validate paths/lines, runnable repro cmds, secret masking (`sk-****`), and Markdown tables/fences. Summarize metrics, top 3 bugs, `S/bug-report.md` path in chat (matching Report Language), and ask which bug to fix.

## Defect Resolution (Post-Report & Explicit User Approval Only)
Fix one bug at a time using sandbox-verified diff -> verify `S/tests/` test turns FAIL->PASS & host baseline passes -> keep tests in `.bughunt/` unless asked -> append Section 9 `"Bugfix Log"` (TH: `"บันทึกการแก้ไข (Bugfix Log)"`) in `S/bug-report.md`.

## Resuming Prior Sessions & Team Mode
- **Resume:** Read latest `S/worklog.md` status/tail only and continue from recorded state; never restart or duplicate hypotheses.
- **Team Mode (`>=50k` LOC):** Primary handles Phases 0–2, 4–6, `worklog.md`, `bug-report.md` (translating user-facing outputs to Report Language), and validates verdicts via `bh.py check` without full log/source re-reads. Load `resources/team-mode.md`.

## Absolute Prohibitions
- NEVER modify host source code, configs, dependencies, or lockfiles before explicit user approval.
- NEVER install, upgrade, or download packages; ask user (in Report Language) if internet fetch is required.
- NEVER run destructive commands (`rm -rf` / `Remove-Item -Recurse` outside `.bughunt/`, `DROP`/`TRUNCATE`, `git reset --hard`, `git clean`, `git push --force`, live DB migrations, prod deploys).
- NEVER contact production or trigger side-effecting external APIs (SMS, payments, webhooks).
- NEVER fabricate evidence, alter logs, or claim unexecuted tests.
- NEVER classify pure style/lint warnings as bugs unless causing wrong runtime behavior.
- NEVER expose secrets, API keys, or credentials in chat or reports.

## Warning Signs — STOP & Correct Course
| Rationalization | Reality |
|---|---|
| "Test failed -> bug found." | Check `bh.py` digest first; `ImportError`/missing module also fails. |
| "Test passed -> no bug." | Confirm `ran > 0` and target logic was not mocked. |
| "One small package won't hurt." | Modifying host env is forbidden; use existing tools or ask user. |
| "Out of ideas; I'll invent one." | Check Coverage Saturation or uninspected Risk/Taxonomy areas. |
| "Trivial fix; I'll patch now." | Never edit host code pre-approval; verify in `sandbox-fix`. |
| "Chat summary is enough." | Physical `S/bug-report.md` is mandatory. |
| "Race passed 200x -> safe." | Widen race window with 1–5 ms collaborator latency (`00-common.md` §4) first. |
