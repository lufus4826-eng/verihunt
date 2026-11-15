# Contributing to VeriHunt

Thank you for your interest in contributing to **VeriHunt** (`verihunt`, formerly `bug-hunter`)!

## Core Philosophy (Do Not Violate)

1. **Proof by Execution:** Every hypothesis must be proven with real test runs in an isolated workspace. No speculative claims.
2. **Zero Footprint:** Nothing should ever modify the host project code, lockfiles, or installed environment during inspection. All test runs and artifacts must reside inside `.bughunt/` or `.bughunt/<session>/sandbox/`.
3. **Cross-Platform Compatibility:** All helper engine logic in `scripts/bh.py` and runner guidance in `resources/lang/` must work on both **Linux/macOS (Bash)** and **Windows (PowerShell)** using Python standard library only.
4. **False-Positive Prevention:** Every test script must include a control test (`test_control_*` / `Control_*`), and harness integrity (`bh.py` §7 signal checks) must be verified before concluding verdicts.
5. **Token Efficiency:** Keep skill prompts concise, preserve lazy-loading boundaries (`report-template.md` / `report-template-th.md` in Phase 6 only, `team-mode.md` in Phase 1.4 only), and route verbose runner outputs through `scripts/bh.py`.

## How to Contribute

### 1. Adding / Enhancing a Language Adapter
Language adapters live in `resources/lang/<language>.md`. If you're adding support for a new language (e.g., Ruby, Swift, Elixir) or improving an existing one:
- Ensure cache isolation flags are documented and wired into `scripts/bh.py` if needed (no cache artifacts in project root).
- Provide cross-platform `bh.py` examples and any OS-specific notes (Bash & PowerShell).
- Include a minimal runnable test template showing:
  - Header with `ID`, `TID`, `Target`, and exact `Run` command.
  - A passing control test.
  - An edge-case assertion that fails on the defect.
- List common language-specific pitfalls (memory leaks, async pitfalls, precision loss, etc.).

### 2. Improving `scripts/bh.py` Engine or Bug Taxonomy
- `scripts/bh.py` must stay **Python 3 standard library only** (no third-party `pip` dependencies).
- Keep CLI digests compact (`<=12` lines for `run`/`check`, `<=35` lines for `recon`) and verify changes with `python -B scripts/bh.py --help` and unit/integration tests before submitting.
- Taxonomy items live in `resources/bug-taxonomy.md`. Suggestions should focus on reproducible defect categories that affect production stability across multiple programming stacks.
- If updating report templates, keep both `resources/report-template.md` (English) and `resources/report-template-th.md` (Thai) aligned across all 9 sections.

### 3. Reporting Issues or False Positives
Please open an issue describing:
- Target language & test runner version.
- OS environment (Windows / macOS / Linux).
- Expected verdict vs Actual verdict (and `bh.py` digest output).
- Relevant snippet from `S/logs/<TID>.log`.

---

# แนวทางการร่วมพัฒนา (ภาษาไทย)

1. **ห้ามเปลี่ยนกติกาหลัก:** การหาบัคต้องพิสูจน์ด้วยการรันจริง (Proof by Execution) มี control test และไม่แตะโค้ดหรือ dependency ของโปรเจกต์
2. **รองรับทั้ง Windows และ Linux/macOS:** คำสั่งใน `resources/lang/` และฟังก์ชันใน `scripts/bh.py` ต้องใช้ได้ทั้งบน Windows (PowerShell) และ Linux/macOS (Bash) โดยใช้ Python standard library เท่านั้น
3. **รักษาความประหยัดโทเคนและโครงสร้าง Lazy-Load:** คงหลักการโหลด `report-template.md` / `report-template-th.md` เฉพาะ Phase 6 และส่งออกผลลัพธ์แบบกระชับผ่าน `scripts/bh.py`
4. **ส่ง Pull Request:** หากเพิ่มภาษาใหม่ ให้สร้างไฟล์ใน `resources/lang/<ภาษา>.md`, เพิ่มตัวแยกผลลัพธ์ใน `scripts/bh.py` (ถ้ามี) และอัปเดตตารางใน `README.md`
