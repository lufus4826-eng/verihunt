# VeriHunt Report Template (English — Lazy-Load in Phase 6 Only)

> **Instructions:** Copy from below the divider to `S/bug-report.md`. Complete all 9 sections; write `"None"` if empty. **NEVER delete sections.** Check `[x]` only when actually performed. If reporting in Thai, load `resources/report-template-th.md` instead.

---

# Bug Hunt Report

## Session Metadata
- **Audit Period:** <YYYY-MM-DD HH:MM> – <YYYY-MM-DD HH:MM>
- **Session Directory (`S`):** `.bughunt/<YYYYMMDD-HHMMSS>/`
- **Project Root (ROOT):** `<path>`
- **Audit Scope:** <Entire project OR modules>
- **Scope Selection Rationale:** <...>
- **Out of Scope (Uninspected):** <List OR "None">
- **Report Status:** Final Complete
- **Termination Reason:** <User stopped after Round 3 | Confidence criteria met in Round X | Coverage saturated in Round X | Reached round limit (X rounds)>

---

## 1. Executive Summary

### 1.1 Metrics Overview
| Metric | Count | Details |
|---|---|---|
| Executed Rounds | <N> | <3 mandatory + N continuation> |
| Total Hypotheses Tested | <N> | - |
| CONFIRMED Defects | <N> | By severity below |
| REFUTED Hypotheses | <N> | Verified guards / passing tests |
| INCONCLUSIVE Hypotheses | <N> | Blocked by env / credentials |
| Sandbox-Verified Fixes | <N>/<Total CONFIRMED> | - |

### 1.2 Confirmed Defects by Severity
- **Critical:** <N> (Data loss/corruption, security vuln, core crash)
- **High:** <N> (Primary feature malfunction under normal use)
- **Medium:** <N> (Edge case or viable workaround)
- **Low:** <N> (Minor impact / improbable trigger)

### 1.3 Top 3 Highest Priority Defects
1. **<ID> — <Bug Name>** (<Severity>): <1–2 line impact summary>
2. **<ID> — <Bug Name>** (<Severity>): <...>
3. **<ID> — <Bug Name>** (<Severity>): <...>

---

## 2. Project Map & Baseline Verification

### 2.1 Technology Stack
- **System Description:** <Concise overview>
- **Language & Runtime:** <e.g., Python 3.12, Node.js 22, Go 1.22>
- **Primary Frameworks:** <e.g., FastAPI, Express, Gin>
- **External Integrations:** <DB, Redis, Broker, External APIs>

### 2.2 Critical Paths
- <Critical Flow 1>
- <Critical Flow 2>

### 2.3 Risk Areas & Coverage Matrix
| # | Risk Area | Risk Level | Rationale | Audit Status | Tested Hypotheses |
|---|---|---|---|---|---|
| 1 | <Module/Fn> | High / Med / Low | <Rationale> | Audited / Pending | <R1-H1, R2-H3> |

### 2.4 Baseline Test Results
- **Test Suite:** `<command>` -> <Results>
- **Linter / Type Checker:** `<command>` -> <Results>
- **Execution Constraints:** <"None" OR details>

### 2.5 Project Instruction Conflicts (Agent.md / Cursorrules / etc.)
| Instruction File | Prescribed Rule | Actual Action Taken | Rationale |
|---|---|---|---|
| <None OR path> | <...> | <...> | <Skill isolation rules take precedence> |

---

## 3. CONFIRMED Defects

<!-- Repeat per CONFIRMED bug, ordered: Critical -> High -> Medium -> Low -->

### <ID>: <Short Bug Title>
- **Severity:** <Critical | High | Medium | Low>
- **Evidence Level:** <E1 Reproduced | E2 Runtime | E3 Static Trace> <Reason if not E1>
- **Code Location:** [`<relative/path:line>`](<relative/path>) `<function_name>`
- **Symptom:** <Incorrect behavior>
- **Trigger Conditions:** <Input, state, concurrency, or timing>
- **Root Cause:** <True underlying cause>
- **Reproduction Command:**
  ```bash
  <Runnable command from ROOT>
  ```
- **Execution Evidence Snippet:**
  ```text
  <Targeted excerpt from S/logs/<TID>.log showing assertion fail / exception + exit=>
  ```
- **Harness Validation:** Ran <N> tests | Control: PASS | Failed: <AssertionError / Exception> | No target mocks
- **Regression Test:** [`<S>/tests/<file>`](<S>/tests/<file>) — FAIL before fix / PASS after fix in sandbox
- **Proposed Fix (Unified Diff):**
  ```diff
  --- a/<path/to/file>
  +++ b/<path/to/file>
  @@ -<start>,<count> +<start>,<count> @@
    <context>
  -<old>
  +<new>
  ```
- **Fix Verification Status:** <Verified in Sandbox — bug test PASS, control PASS | Unverified — <reason>>
- **Side Effects & Regression Risks:** <Caller/module impact>
- **Sibling Bug Audit:** <Matched locations (ID) OR "Scanned, none found">

---

## 4. REFUTED Hypotheses
| ID | Code Location | Suspected Issue | Refutation Rationale (Guard / Test Result) | Evidence Level |
|---|---|---|---|---|
| <ID> | <file:line> | <...> | <...> | E1 / E3 |

---

## 5. INCONCLUSIVE Hypotheses
| ID | Code Location | Suspected Issue | Potential Severity | Impasse / Blocker | Prerequisites to Resolve |
|---|---|---|---|---|---|
| <ID> | <file:line> | <...> | <...> | <...> | <...> |

---

## 6. Confidence Criteria Evaluation
| Criterion | Status | Evaluation Details |
|---|---|---|
| 1. Every High/Med Risk Area tested by >=1 hypothesis | Pass / Fail | <...> |
| 2. Last 2 consecutive rounds produced no novel root-cause bugs | Pass / Fail | <...> |
| 3. No unresolved High/Critical INCONCLUSIVE hypotheses | Pass / Fail | <...> |
| 4. Every CONFIRMED bug scanned for sibling bugs | Pass / Fail | <...> |
| 5. All applicable taxonomy categories evaluated | Pass / Fail | <See 6.1> |

**Overall Confidence Verdict:** <Passed 5/5 — No further defects detected within audited scope | Passed X/5 — Unmet: ...>

### 6.1 Bug Taxonomy Coverage
| Category | Audit Status |
|---|---|
| 1. Input & Edge Cases | <Audited (ID) / Irrelevant — rationale> |
| 2. Error Handling | <...> |
| 3. Concurrency & Async | <...> |
| 4. State & Data | <...> |
| 5. Resources | <...> |
| 6. Time & Numbers | <...> |
| 7. Security | <...> |
| 8. Config & Environment | <...> |
| 9. Contracts | <...> |
| 10. Data Migration & Compatibility | <...> |
| 11. Stability Performance | <...> |
| 12. Localization & I18n | <...> |

---

## 7. Workspace Cleanliness Log
- **Snapshot Method:** <git status --porcelain --ignored | file timestamps> -> `<S>/logs/fs-before.txt`, `<S>/logs/fs-after.txt`
- **Comparison Result:** <Zero unexpected files outside .bughunt/ | Cleaned artifacts: ...>
- **Remaining External Files (Unremovable):** <List OR "None">
- **Cleaned Temporary Folders:**
  - [ ] `<S>/tmp/`
  - [ ] `<S>/sandbox/` (if instantiated)
  - [ ] `<S>/sandbox-fix/` (if instantiated)
  - [ ] `.bughunt/.cache/`
- **Notice:** `.bughunt/` should not be committed (logs may contain sensitive traces). <Added to .git/info/exclude with user approval | Pending>
- **Deliverables Retained:** `<S>/bug-report.md`, `<S>/worklog.md`, `<S>/tests/`, `<S>/logs/`

---

## 8. Next Steps & Recommendations
<Follow-up modules, unresolved INCONCLUSIVE items, or out-of-scope recommendations>

---

## 9. Bugfix Log
> Updated only when the user explicitly authorizes production fixes.

| Timestamp | ID | Patched File | Regression Test Status | Host Baseline Suite | Status |
|---|---|---|---|---|---|
| <None OR YYYY-MM-DD> | <ID> | <file> | <PASS (`<S>/tests/...`)> | <All Passed / Fail N> | <Complete / Pending> |
