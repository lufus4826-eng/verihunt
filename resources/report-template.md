# Bug Hunt Report Template

> **Instructions for Agent:** Copy the structure starting below the divider line to generate `S/bug-report.md`. Fill in all sections thoroughly. **NEVER delete any section.** If a section contains no data, explicitly write "None". Items enclosed in `<...>` indicate placeholder fields. Check checkboxes `[x]` only when actions have actually been performed. (If user prompt requested a Thai report, translate headers/body accordingly while keeping this exact structure).

---

# Bug Hunt Report

## Session Metadata
- **Audit Period:** <YYYY-MM-DD HH:MM> – <YYYY-MM-DD HH:MM>
- **Session Directory (`S`):** `.bughunt/<YYYYMMDD-HHMMSS>/`
- **Project Root (ROOT):** `<path to host project>`
- **Audit Scope:** <Entire project OR specific modules>
- **Scope Selection Rationale:** <User specified / Selected critical paths due to codebase size / ...>
- **Out of Scope (Uninspected):** <List of excluded modules OR "None">
- **Report Status:** <Final Complete | Interim Draft — Awaiting User Decision>
- **Termination Reason:** <Awaiting User Decision | User stopped after Round 3 | Confidence criteria met in Round X | Coverage saturated in Round X | Reached round limit (X rounds)>

---

## 1. Executive Summary

### 1.1 Metrics Overview
| Metric | Count | Details |
|---|---|---|
| Executed Rounds | <N> | <Mandatory 3 rounds + N continuation rounds> |
| Total Hypotheses Tested | <N> | - |
| CONFIRMED Defects | <N> | Categorized by severity below |
| REFUTED Hypotheses | <N> | Verified guards or correct handling confirmed |
| INCONCLUSIVE Hypotheses | <N> | Blocked by missing credentials or environments |
| Sandbox-Verified Fixes | <N>/<Total CONFIRMED> | - |

### 1.2 Confirmed Defects by Severity
- **Critical:** <N> (Data loss/corruption, security vulnerabilities, or complete system crash on core paths)
- **High:** <N> (Core features malfunctioning under standard operations)
- **Medium:** <N> (Manifests in edge cases or has viable workarounds)
- **Low:** <N> (Minor impact or improbable trigger conditions)

### 1.3 Top 3 Highest Priority Defects
1. **<ID> — <Bug Name>** (<Severity>): <Summary of symptom and business impact in 1–2 lines>
2. **<ID> — <Bug Name>** (<Severity>): <...>
3. **<ID> — <Bug Name>** (<Severity>): <...>

---

## 2. Project Map & Baseline Verification

### 2.1 Technology Stack
- **System Description:** <Concise system overview>
- **Language & Runtime:** <e.g., Python 3.12, Node.js 22, Go 1.22>
- **Primary Frameworks:** <e.g., FastAPI, Express, Gin, Spring Boot>
- **External Integrations:** <DB, Redis, Message Queues, External APIs>

### 2.2 Critical Paths
- <Critical Flow 1>
- <Critical Flow 2>

### 2.3 Risk Areas & Coverage Matrix
| # | Risk Area | Risk Level | Rationale | Audit Status | Tested Hypotheses |
|---|---|---|---|---|---|
| 1 | <Module / Function> | High / Med / Low | <Rationale> | Audited / Pending | <R1-H1, R2-H3> |

### 2.4 Baseline Test Results
- **Test Suite:** `<command>` -> <All passed / Fail N cases (cause)>
- **Linter / Type Checker:** `<command>` -> <Results>
- **Execution Constraints:** <e.g., Missing local DB, skipped commands requiring external downloads>

### 2.5 Project Instruction Conflicts (Agent.md / Cursorrules / etc.)
| Instruction File | Prescribed Rule | Actual Action Taken | Rationale |
|---|---|---|---|
| <None OR file path> | <...> | <...> | <Skill isolation rules take precedence> |

---

## 3. CONFIRMED Defects

<!-- Duplicate this sub-section for every CONFIRMED bug, ordered: Critical -> High -> Medium -> Low -->

### <ID>: <Short Bug Title>
- **Severity:** <Critical | High | Medium | Low>
- **Evidence Level:** <E1 Reproduced | E2 Runtime | E3 Static Trace> <If not E1, document justification>
- **Code Location:** [`<relative/path/file.ext:line>`](<relative/path/file.ext>) function `<function_name>`
- **Symptom:** <Detailed description of incorrect behavior>
- **Trigger Conditions:** <Input, state, concurrency, or timing sequence triggering defect>
- **Root Cause:** <True underlying cause, not just external symptom>
- **Reproduction Command:**
  ```bash
  <Runnable command from project ROOT>
  ```
- **Execution Evidence Snippet:**
  ```text
  <Concrete excerpt from S/logs/<TID>.log showing failed assertion or target exception with exit code>
  ```
- **Harness Validation:** Ran <N> tests | Control test: PASS | Failed with: <AssertionError / Target Exception> | No mocks intercepting target code
- **Regression Test:** [`<S>/tests/<test_file>`](<S>/tests/<test_file>) — FAIL before fix / PASS after fix in sandbox
- **Proposed Fix (Unified Diff):**
  ```diff
  --- a/<path/to/file>
  +++ b/<path/to/file>
  @@ -<start>,<count> +<start>,<count> @@
    <context lines>
  -<original code>
  +<fixed code>
  ```
- **Fix Verification Status:** <Verified in Sandbox — bug test PASS, control PASS | Unverified — <rationale>>
- **Side Effects & Regression Risks:** <Potential impact on callers or adjacent modules>
- **Sibling Bug Audit:** <Identical anti-pattern search results across codebase (ID) OR "Scanned, none found">

---

## 4. REFUTED Hypotheses
| ID | Code Location | Suspected Issue | Refutation Rationale (Guard / Test Result) | Evidence Level |
|---|---|---|---|---|
| <ID> | <file:line> | <...> | <e.g., Guarded by middleware input validation at line 42> | E1 / E3 |

---

## 5. INCONCLUSIVE Hypotheses
| ID | Code Location | Suspected Issue | Potential Severity | Impasse / Blocker | Prerequisites to Resolve |
|---|---|---|---|---|---|
| <ID> | <file:line> | <...> | <High/...> | <e.g., Requires AWS cloud IAM permissions> | <...> |

---

## 6. Confidence Criteria Evaluation
| Criterion | Status | Evaluation Details |
|---|---|---|
| 1. Every High/Med Risk Area tested by >= 1 hypothesis | Pass / Fail | <...> |
| 2. Last 2 consecutive rounds produced no novel root-cause bugs | Pass / Fail | <e.g., Rounds 4–5 found only sibling bugs of R2-H1> |
| 3. No unresolved High/Critical INCONCLUSIVE hypotheses | Pass / Fail | <...> |
| 4. Every CONFIRMED bug scanned for sibling bugs | Pass / Fail | <...> |
| 5. All applicable taxonomy categories evaluated | Pass / Fail | <See section 6.1> |

**Overall Confidence Verdict:** <Passed 5/5 — No further defects detected within audited scope | Passed X/5 — Unmet: ...>

### 6.1 Bug Taxonomy Coverage
| Category | Audit Status |
|---|---|
| 1. Input & Edge Cases | <Audited (R1-H1) / Irrelevant — rationale> |
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
- **Snapshot Method:** <git status --porcelain --ignored | file list + timestamps> -> `<S>/logs/fs-before.txt`, `<S>/logs/fs-after.txt`
- **Comparison Result:** <Zero unexpected files outside .bughunt/ | Deleted agent-created artifacts: ...>
- **Remaining External Files (Unremovable):** <List OR "None">
- **Cleaned Temporary Folders:**
  - [ ] `<S>/tmp/`
  - [ ] `<S>/sandbox/` (if instantiated)
  - [ ] `<S>/sandbox-fix/` (if instantiated)
  - [ ] `.bughunt/.cache/`
- **Notice:** Directory `.bughunt/` should not be committed (logs may contain sensitive data). <Added to .git/info/exclude with user approval | Pending>
- **Deliverables Retained:** `<S>/bug-report.md`, `<S>/worklog.md`, `<S>/tests/`, `<S>/logs/`

---

## 8. Next Steps & Recommendations
<Recommended hypotheses or modules for subsequent audits, unresolved INCONCLUSIVE items, or out-of-scope areas recommended for dedicated sessions>

---

## 9. Bugfix Log
> Updated only when the user explicitly authorizes production fixes.

| Timestamp | ID | Patched File | Regression Test Status | Host Baseline Suite | Status |
|---|---|---|---|---|---|
| <None OR YYYY-MM-DD> | <ID> | <file> | <PASS (`<S>/tests/...`)> | <All Passed / Fail N> | <Complete / Pending> |
