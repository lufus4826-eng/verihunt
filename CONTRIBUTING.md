# Contributing to Bug Hunter

Thank you for your interest in contributing to **Bug Hunter**!

## Core Philosophy (Do Not Violate)

1. **Proof by Execution:** Every hypothesis must be proven with real test runs in an isolated workspace. No speculative claims.
2. **Zero Footprint:** Nothing should ever modify the host project code, lockfiles, or installed environment during inspection. All test runs and artifacts must reside inside `.bughunt/` or `.bughunt/<session>/sandbox/`.
3. **Cross-Platform Compatibility:** Every test runner command must support both **Linux/macOS (Bash)** and **Windows (PowerShell)**.
4. **False-Positive Prevention:** Every test script must include a control test, and harness integrity must be checked before concluding verdicts.

## How to Contribute

### 1. Adding / Enhancing a Language Adapter
Language adapters live in `resources/lang/<language>.md`. If you're adding support for a new language (e.g., Ruby, Swift, Elixir) or improving an existing one:
- Ensure cache isolation flags are documented (no cache artifacts in project root).
- Provide dual syntax: **Bash** and **PowerShell**.
- Include a minimal runnable test template showing:
  - Header with ID, Target, and exact run command.
  - A passing control test.
  - An edge-case assertion that fails on the defect.
- List common language-specific pitfalls (memory leaks, async pitfalls, precision loss, etc.).

### 2. Improving Bug Taxonomy
Taxonomy items live in `resources/bug-taxonomy.md`. Suggestions should focus on reproducible defect categories that affect production stability across multiple programming stacks.

### 3. Reporting Issues or False Positives
Please open an issue describing:
- Target language & test runner version.
- OS environment (Windows / macOS / Linux).
- Expected verdict vs Actual verdict.
- Relevant snippet from `S/logs/<TID>.log`.

---

# แนวทางการร่วมพัฒนา (ภาษาไทย)

1. **ห้ามเปลี่ยนกติกาหลัก:** การหาบัคต้องพิสูจน์ด้วยการรันจริง (Proof by Execution) มี control test และไม่แตะโค้ดหรือ dependency ของโปรเจกต์
2. **รองรับทั้งสอง OS:** คำสั่งที่เสนอต้องมีทั้ง Bash (Linux/macOS) และ PowerShell (Windows)
3. **ส่ง Pull Request:** หากเพิ่มภาษาใหม่ ให้สร้างไฟล์ใน `resources/lang/<ภาษา>.md` และอัปเดตตารางใน `resources/lang/00-common.md` และ `README.md`
