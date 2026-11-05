# 00 — Common Infrastructure & Protocol (Read Every Run)

Used in conjunction with language adapters in `resources/lang/`. All commands execute with `ROOT` as the current working directory.

## 1. Session Variables
| Variable | Definition | Example |
|---|---|---|
| `S` | Session folder path (relative to ROOT) | `.bughunt/20261105-143005` |
| `SNAME` | Session folder name only | `20261105-143005` |
| `CACHE` | Central cache directory (**absolute path**) | `$PWD/.bughunt/.cache` |
| `TID` | Hypothesis test file identifier (lowercase with underscore) | `r1_h2` |

Initialize session variables once per shell:
```bash
S=.bughunt/20261105-143005; SNAME=${S##*/}; CACHE="$PWD/.bughunt/.cache"; TID=r1_h2
```
```powershell
$S = ".bughunt\20261105-143005"; $SNAME = Split-Path $S -Leaf; $CACHE = "$PWD\.bughunt\.cache"; $TID = "r1_h2"
```
> Note: Agent tool executions may spawn fresh shell sessions. Re-initialize variables whenever starting a new sub-session.

## 2. Bash ↔ PowerShell Command Translation
| Operation | Bash (Linux / macOS / Git Bash) | PowerShell (Windows) |
|---|---|---|
| Set env var for single command | `VAR=x cmd` | `$env:VAR="x"; cmd` (persists for duration of shell session) |
| Set persistent env var | `export VAR=x` | `$env:VAR="x"` |
| Current working directory | `$(pwd)` | `$PWD` |
| Create directory recursively | `mkdir -p a/b` | `New-Item -ItemType Directory -Force a\b \| Out-Null` |
| Expand wildcard for external tool | Handled natively by shell | **Not expanded by PowerShell**; use `(Get-ChildItem "pat*").FullName` |
| Execute wrapper scripts | `./gradlew`, `./vendor/bin/phpunit` | `.\gradlew.bat`, `php vendor/bin/phpunit` |
| Remove folder inside `.bughunt` | `rm -rf "$S/tmp"` | `Remove-Item -Recurse -Force "$S\tmp"` |
| Last process exit code | `$?` | `$LASTEXITCODE` |

## 3. Log Capture with Process Exit Code
```bash
<command> > "$S/logs/$TID.log" 2>&1; echo "exit=$?" >> "$S/logs/$TID.log"
```
```powershell
# Windows PowerShell 5.1: Pipe through cmd /c to ensure raw binary output (prevents NativeCommandError wrapping and encoding corruption)
cmd /c "<command> > `"$S\logs\$TID.log`" 2>&1"; "exit=$LASTEXITCODE" | Add-Content "$S\logs\$TID.log"
# Read logs with explicit UTF-8 encoding
Get-Content "$S\logs\$TID.log" -Encoding utf8
```
- In Windows PowerShell 5.1, avoid `2>&1 | Out-File` or `*>` with external CLI tools, as stderr gets wrapped in `NativeCommandError` objects and default encoding may corrupt non-ASCII characters.
- In PowerShell 7.3+, native redirection `<command> *> "$S\logs\$TID.log"` is supported.
- If paths contain spaces, escape them with internal quotes within `cmd /c` using `` `" ``.
- Command-level timeouts: On Linux/macOS, use `timeout 600 <command>` (GNU coreutils). On Windows, rely on the agent tool timeout parameter combined with in-code test timeouts.

## 4. Workspace Cleanliness Snapshots
```bash
# Git repository
git status --porcelain --ignored > "$S/logs/fs-before.txt"
# Non-git repository (GNU find; on macOS use stat -f '%N %m' instead of -printf)
find . \( -path ./.bughunt -o -path ./.git -o -name node_modules \) -prune -o -type f -printf '%p %T@\n' | sort > "$S/logs/fs-before.txt"
# Comparison at cleanup: generate fs-after.txt with identical command, then:
diff "$S/logs/fs-before.txt" "$S/logs/fs-after.txt"
```
```powershell
# Git repository
git status --porcelain --ignored | Set-Content "$S\logs\fs-before.txt" -Encoding utf8
# Non-git repository
Get-ChildItem -Recurse -File -Force | Where-Object { $_.FullName -notmatch '\\(\.bughunt|\.git|node_modules)(\\|$)' } |
  ForEach-Object { "{0}`t{1:o}" -f $_.FullName, $_.LastWriteTimeUtc } | Sort-Object | Set-Content "$S\logs\fs-before.txt" -Encoding utf8
# Comparison
Compare-Object (Get-Content "$S\logs\fs-before.txt") (Get-Content "$S\logs\fs-after.txt")
```

## 5. Sandbox Replication (Project Copies)
Baseline exclusion list: `.git`, `.bughunt`, `node_modules`, `.venv`, `venv`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, plus language-specific build folders (`target`, `bin`, `obj`). Never exclude `vendor`, as Go and PHP require vendor dependencies.

```bash
mkdir -p "$S/sandbox"
rsync -a --exclude='/.git' --exclude='/.bughunt' --exclude='node_modules' --exclude='.venv' --exclude='venv' \
  --exclude='__pycache__' ./ "$S/sandbox/"
# Fallback if rsync is not installed
tar --exclude=./.git --exclude=./.bughunt --exclude=node_modules --exclude=.venv -cf - . | tar -xf - -C "$S/sandbox"
```
```powershell
robocopy . "$S\sandbox" /E /XD "$PWD\.git" "$PWD\.bughunt" node_modules .venv venv __pycache__ .pytest_cache /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with code $LASTEXITCODE" } # robocopy returns 0–7 on success
```
- **Node.js:** Do not duplicate `node_modules`. Node resolves modules by ascending parent directories, discovering `ROOT/node_modules` automatically.
- **Relative Path Dependencies:** References pointing outside ROOT (`replace ../x` in `go.mod`, `path = "../x"` in `Cargo.toml`, `ProjectReference` or Maven `<relativePath>`) will fail when nested deeper. You are permitted to modify these in the **sandbox copy** to use absolute paths.
- **Massive Repositories:** Clone only the specific modules within SCOPE along with their necessary root build manifests.

## 6. Dependency Installation & Network Prevention
| Tool / Ecosystem | Prevention Method | If Unavailable |
|---|---|---|
| npm / npx | `npx --no-install <tool>`. NEVER run `npm install`/`npm ci`/`npx` without flags. | Tool missing locally -> fallback to `node --test` or declare INCONCLUSIVE. |
| Python | NEVER run `pip install`, `uv add`, `poetry add`. | Missing pytest -> fallback to built-in `unittest`. |
| Go | `GOPROXY=off` | Module missing from local cache -> ask user. |
| Maven | `-o` (offline mode) and use standard `~/.m2`. | Missing artifacts -> ask user. |
| Gradle | `--offline` | Wrapper distribution missing locally -> ask user. |
| .NET | If project has existing `obj/`, packages exist in global cache; run `dotnet restore` in sandbox. | Never restored -> ask user before restoring. |
| Cargo (Rust) | `--offline --locked` | Crate missing from local cache -> ask user. |
| PHP | Rely on existing `vendor/`. NEVER run `composer install/update`. | Missing `vendor/` -> ask user. |

`--locked` and offline flags also guarantee that project lockfiles remain untouched.

## 7. Harness Failure Signals (NOT Evidence of Bugs)
| Runner | Valid Bug Failure | Harness Breakdown Signals (Do NOT count as bug) |
|---|---|---|
| pytest | exit 0 = Pass, exit 1 = Failed test assertions (inspect summary `N failed` & `SUBFAILED` when using subTest) | exit 2 (collection/import error), 3, 4 (file not found/bad arguments), 5 (no tests collected), test status `ERROR` (fixture/setup crash). |
| unittest | `FAILED (failures=N)` | `errors=N` stemming from import/setUp, `Ran 0 tests`. |
| node --test | `# fail N` originating from assertions | Entire file fails with `not ok` alongside `MODULE_NOT_FOUND`, `SyntaxError`, `ERR_REQUIRE_ESM` (**produces exit 1 identical to real test failures**), `# tests 0`. |
| Jest | `Tests: N failed` | `Test suite failed to run`, `No tests found`, `Cannot find module`. |
| Vitest | `Tests N failed` | `Failed to load`, `No test files found`, syntax transform error. |
| go test | `--- FAIL:` | `[build failed]`, `[setup failed]`, `no test files`, `cannot find package`. |
| Maven / Gradle | `Tests run: N, Failures: M` | `COMPILATION ERROR`, `Compilation failed`, `No tests were executed`, `No tests found for given includes`, `Could not resolve`. |
| dotnet test | `Failed: N` | `error CS`, `No test matches the given testcase filter`, `NU1101` / `NU1301`. |
| PHPUnit | `FAILURES! Tests: N, Failures: M` | `No tests executed!`, `Cannot open file`, `Class ... not found`, `Errors:` emitted from bootstrap. |
| cargo test | `test result: FAILED` | `error[E...]`, `could not compile`, `running 0 tests`, `no test target named`. |

## 8. Concurrency Testing Methodology
1. **Synchronized Release:** Use concurrency gates so all workers release simultaneously (`threading.Barrier` in Python, `CountDownLatch` in Java, closed channel in Go, `Promise.all` in JavaScript).
2. **Race Window Widening:** Without I/O between read and write, threads rarely interleave during in-memory operations. In CPython 3.13, even setting `sys.setswitchinterval(1e-6)` observed zero races over 200 iterations; introducing a fake collaborator with a 1 ms sleep reliably exposed overselling.
   - Replace external collaborators (repository, cache, HTTP client) with a fake that introduces 1–5 ms of latency. Never modify the target logic itself.
   - Document in the report how the race window was widened (real database and network operations typically exhibit far higher latencies).
3. **JavaScript:** Being single-threaded, race conditions manifest strictly across asynchronous event loop ticks when `await` intervenes between check and act. Use async fakes awaiting timers or `setImmediate`.
4. **Go:** Run with `go test -race -count=50` (requires cgo and gcc on Windows; if unavailable, rely on multi-iteration tallying).
5. **Ratio Reporting:** Report concurrency outcomes as explicit ratios, e.g., `37/200`. If an operation yields `0/N`, never immediately declare REFUTED without complementary evidence of locking, transactions, atomic variables, or database constraints.

## 9. Git Churn Hotspots (Phase 1.2)
```bash
git log --oneline -i -E --grep="fix|bug|hotfix" -20
git log --format= --name-only --since="6 months ago" | grep -v '^$' | sort | uniq -c | sort -rn | head -20
```
```powershell
git log --oneline -i -E --grep="fix|bug|hotfix" -20
git log --format= --name-only --since="6 months ago" | Where-Object { $_ } | Group-Object | Sort-Object Count -Descending | Select-Object -First 20 Count, Name
```
