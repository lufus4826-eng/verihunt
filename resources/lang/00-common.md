# 00 — Common Infrastructure & Protocol

Used with `resources/lang/<lang>.md`. Execute commands from `ROOT`; resolve `<BH>` as `<skill_dir>/scripts/bh.py`.

## 1. Helper CLI (`scripts/bh.py`)
Use `bh.py` for setup, recon, isolated runs, digests, worklog updates, and sandboxes (auto-redirects caches to `.bughunt/.cache/` and enforces offline/no-pyc/UTF-8/no-color env vars):

- `python "<BH>" init [--root .]` -> creates `S/{tests,logs,tmp}` + `.cache`, writes `fs-before.txt`, inits `worklog.md`, prints 1-line JSON `{S, SNAME, CACHE, ROOT, snapshot, prior_sessions}`.
- `python "<BH>" recon [--root .]` -> `<=35`-line map (instructions, languages, manifests, entrypoints, tests, LOC, TODOs, git churn/fixes).
- `python "<BH>" run --s "$S" --tid <TID> [--runner r] [--cwd dir] [--timeout 600] [--log-suffix suf] -- <cmd...>` -> logs raw output + `exit=<code>` to `S/logs/<TID>.log`, prints `<=12`-line digest (`ALL_PASS|VALID_BUG_FAIL|HARNESS_BROKEN|TIMEOUT|EXEC_ERROR`).
- `python "<BH>" round --s "$S" (--round N | --all) [--tids a,b] [--fix] [--runner r] [--parallel 1] [--cmd-template TPL]` -> discovers & runs round tests (`test_r{N}_h*`, `BugHuntR{N}H*`, `bughunt_r{N}_h*`); `--fix` uses `S/sandbox-fix` & `_fix.log`.
- `python "<BH>" check --s "$S" (--tid <TID> | --round N | --all)` -> parses existing logs without re-running (Team Mode verdict check).
- `python "<BH>" log --s "$S" [--status "..."] [--entry "..." | --entry-file path]` -> updates `worklog.md` line-1 `Status:` + appends text. (Prefer repeatable `--entry` or `--entry-file` over stdin pipes on Windows PowerShell).
- `python "<BH>" sandbox --s "$S" --mode create|fix|clean [--exclude dir] [--force]` -> creates `S/sandbox`, sets up `S/sandbox-fix` + replicated tests, or cleans temp/cache/sandbox dirs + archives sandbox tests/JVM XML + writes/diffs `fs-after.txt` + auto-removes untracked `__pycache__`/`.pytest_cache`.

If ever running raw shell commands outside `bh.py` on Windows PowerShell 5.1, wrap via `cmd /c "<cmd> > log 2>&1"` to prevent `NativeCommandError`/encoding issues; never dump logs or source via `Get-Content`.

## 2. Dependency & Network Prevention
| Ecosystem | Prevention | If Missing |
|---|---|---|
| npm / npx | `npx --no-install <tool>`. NEVER `npm install`/`npm ci`/unflagged `npx` | `node --test` or `INCONCLUSIVE` |
| Python | NEVER `pip install`, `uv add`, `poetry add` | Built-in `unittest` |
| Go | `GOPROXY=off` (auto-set) | Ask user |
| Maven | `-o` offline (uses `~/.m2`; never set empty `maven.repo.local`) | Ask user |
| Gradle | `--offline` | Ask user |
| .NET | Existing `obj/` means NuGet cached (`dotnet restore` in sandbox) | Ask user before restoring |
| Cargo | `--offline --locked` (locks `Cargo.lock` too) | Ask user |
| PHP | Use existing `vendor/`. NEVER `composer install/update` | Ask user |

## 3. Harness Failure Signals (§7 — Reference for `bh.py` & Audit)
Valid bug failure ONLY if `ran > 0`, `control: PASS`, and failure is an assertion or unhandled target exception (never these signals):
- **pytest:** Valid: `exit=1`, `N failed`/`SUBFAILED` | Broken: `exit=2,3,4,5`, `ERROR` (fixture/setup), collection/import/syntax error, `no tests ran`.
- **unittest:** Valid: `FAILED (failures=N)` | Broken: `errors=N` from import/`setUp`/`setUpClass`, `Ran 0 tests`.
- **node --test:** Valid: `# fail N` from assertions | Broken: `not ok` with `MODULE_NOT_FOUND`/`SyntaxError`/`ERR_REQUIRE_ESM` (**also exits 1!**), `# tests 0`.
- **Jest / Vitest / Mocha:** Valid: `Tests: N failed` / `N failing` | Broken: `Test suite failed to run`, `Failed to load`, `No tests found`, `Cannot find module`, transform/syntax error.
- **go test:** Valid: `--- FAIL:` / `DATA RACE` | Broken: `[build failed]`, `[setup failed]`, `no test files`, `cannot find package`.
- **Maven / Gradle:** Valid: `Tests run: N, Failures: M` / `N failed` | Broken: `COMPILATION ERROR`, `Compilation failed`, `No tests were executed/found`, `Could not resolve`.
- **dotnet test:** Valid: `Failed: N` | Broken: `error CS`, `No test matches the given testcase filter`, `NU1101`/`NU1301`.
- **PHPUnit:** Valid: `FAILURES! Tests: N, Failures: M` | Broken: `No tests executed!`, `Cannot open file`, `Class ... not found`, bootstrap/parse errors.
- **cargo test:** Valid: `test result: FAILED` | Broken: `error[E...]`, `could not compile`, `running 0 tests`, `no test target named`.

## 4. Concurrency Testing Methodology
1. **Synchronized Release:** Release workers simultaneously (`threading.Barrier`, `CountDownLatch`, closed Go channel, `Promise.all`).
2. **Race Window Widening:** Pure in-memory reads/writes rarely interleave (CPython 3.13 with `sys.setswitchinterval(1e-6)` hit 0/200 races until a 1 ms fake collaborator sleep exposed oversell). Replace external collaborators (repo/cache/HTTP) with 1–5 ms latency fakes; never edit target logic; document widening in report.
3. **JS:** Races cross `await` points; use async fakes (`setImmediate`/timer).
4. **Go:** `go test -race -count=50` (needs cgo/gcc on Windows; else tally multi-run overshoots).
5. **Ratios:** Report `k/N` (e.g., `37/200`). Never mark `0/N` as `REFUTED` without proving lock/TX/atomic/unique constraint at `file:line`.

## 5. Sandbox Notes
- **Never exclude `vendor`** (Go/PHP need it). `bh.py sandbox` keeps `vendor` and skips `.git`, `.bughunt`, `node_modules`, `.venv`, `venv`, caches, and manifest build dirs (`target`, `bin`, `obj`, root `build`/`out`).
- **Node.js:** Omit `node_modules`; Node resolves `ROOT/node_modules` upward.
- **Relative Path Deps:** Rewriting external `replace ../x` (`go.mod`), `path = "../x"` (`Cargo.toml`), `ProjectReference`, or Maven `<relativePath>` to absolute paths is allowed inside `S/sandbox/`.
- **Massive Repos:** Copy scoped modules + root manifests (or `--exclude`).
