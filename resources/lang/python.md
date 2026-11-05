# Python Adapter

## 1. Pre-execution Environment Setup
```bash
export PYTHONDONTWRITEBYTECODE=1   # Prevent creating __pycache__ inside host repository
export PYTHONUTF8=1                # Prevent UnicodeEncodeError when logs contain multi-byte text (critical on Windows)
```
```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"; $env:PYTHONUTF8 = "1"
```
- Utilize the project's existing virtual environment if available (e.g., `.venv/bin/python`, `.venv\Scripts\python.exe`, `poetry run python`, `uv run --no-sync python`).
- **Always invoke pytest via `python -m pytest`**: Invoking `pytest` directly does not add ROOT to `sys.path`, leading to collection crashes (`from app...` -> exit code 2).
- Always include `-p no:cacheprovider` to prevent `.pytest_cache` directories from appearing in the project.

## 2. Executing Hypothesis Tests
```bash
python -m pytest "$S"/tests/test_${TID}_*.py -p no:cacheprovider -v > "$S/logs/$TID.log" 2>&1; echo "exit=$?" >> "$S/logs/$TID.log"
```
```powershell
$files = (Get-ChildItem "$S\tests\test_${TID}_*.py" | ForEach-Object { '"' + $_.FullName + '"' }) -join ' '
cmd /c "python -m pytest $files -p no:cacheprovider -v > `"$S\logs\$TID.log`" 2>&1"; "exit=$LASTEXITCODE" | Add-Content "$S\logs\$TID.log"
```
**Fallback if pytest is not installed:** The test template below is written using `unittest.TestCase`, allowing direct Python execution. (Set `PYTHONPATH` to ROOT; because `.bughunt` starts with a dot, `python -m unittest <path>` cannot parse module paths):
```bash
PYTHONPATH=. python "$S/tests/test_${TID}_x.py" -v > "$S/logs/$TID.log" 2>&1; echo "exit=$?" >> "$S/logs/$TID.log"
```
```powershell
$env:PYTHONPATH = "."; cmd /c "python `"$S\tests\test_${TID}_x.py`" -v > `"$S\logs\$TID.log`" 2>&1"; "exit=$LASTEXITCODE" | Add-Content "$S\logs\$TID.log"
```

## 3. Important Pytest Configuration Checks
- **`addopts`** in `pytest.ini` / `pyproject.toml` / `setup.cfg`: If configured with `--cov`, `--junitxml`, or `--html`, override via `-o addopts=""` and manually supply required test plugins (e.g., `-p pytest_django`, `--import-mode=importlib`), or append `--no-cov`.
- **`conftest.py` loading:** Root-level `conftest.py` will be discovered automatically. Ensure that fixtures marked `autouse=True` do not connect to live databases or external services.
- **Django:** Set `DJANGO_SETTINGS_MODULE` pointing to test settings (or use `--ds=`) and configure in-memory SQLite.
- **Timeouts:** If `pytest-timeout` is available, append `--timeout=60`. Otherwise, enforce timeouts in test code (`future.result(timeout=...)`, `thread.join(timeout=...)`).
- **Async:** Use `pytest-asyncio` or `anyio` if configured; otherwise wrap asynchronous calls in `asyncio.run()`.

## 4. Baseline Commands
```bash
python -m pytest -p no:cacheprovider -q
python -m mypy --cache-dir "$CACHE/mypy" .        # If mypy is used
ruff check --no-cache .                           # If ruff is used
python -m flake8 .                                # flake8 does not write caches
```

## 5. Example: Logic Defect (`S/tests/test_r1_h2_discount_rounding.py`)
```python
# ID: R1-H2 | TID: r1_h2
# Target: app/billing/discount.py:apply_discount
# Run: python -m pytest .bughunt/<SNAME>/tests/test_r1_h2_discount_rounding.py -p no:cacheprovider -v
import unittest
from decimal import Decimal

from app.billing.discount import apply_discount  # Invoke real project implementation


class TestR1H2DiscountRounding(unittest.TestCase):
    def test_control_no_rounding_needed(self):
        # Control: whole-cent calculation must pass (validates harness integrity and function wiring)
        self.assertEqual(apply_discount(total=Decimal("100.00"), rate=Decimal("0.10")), Decimal("10.00"))

    def test_half_cent_rounds_up(self):
        # Desired commercial accounting behavior: round half up (ROUND_HALF_UP)
        cases = [("1.25", "0.13"), ("0.05", "0.01"), ("2.25", "0.23")]
        for total, expected in cases:
            with self.subTest(total=total):
                self.assertEqual(apply_discount(total=Decimal(total), rate=Decimal("0.10")), Decimal(expected))


if __name__ == "__main__":
    unittest.main()
```
> **Inspect the log summary line:** When using `subTest` on modern pytest versions, the main test function may report `PASSED` even when inner subtests encounter `SUBFAILED(...)`. Confirm verdicts via the bottom summary line (`1 failed, 2 passed, exit=1`).

## 6. Example: Race Condition (`S/tests/test_r2_h1_reserve_race.py`)
```python
# ID: R2-H1 | TID: r2_h1
# Target: app/inventory.py:Inventory.reserve (check stock -> deduct without transaction lock)
# Run: python -m pytest .bughunt/<SNAME>/tests/test_r2_h1_reserve_race.py -p no:cacheprovider -v
import threading
import time
import unittest

from app.inventory import Inventory


class SlowRepo:
    """Simulated collaborator introducing latency during read to widen the race window (mimics DB latency)."""

    def __init__(self, stock):
        self.data = {"A": stock}

    def get_stock(self, sku):
        value = self.data[sku]
        time.sleep(0.001)  # 1ms latency window
        return value

    def set_stock(self, sku, value):
        self.data[sku] = value


def _worker(inv, barrier, results):
    barrier.wait()  # Synchronized release
    results.append(inv.reserve("A", 1))


class TestR2H1ReserveRace(unittest.TestCase):
    def test_control_single_thread(self):
        inv = Inventory(SlowRepo(stock=1))
        self.assertTrue(inv.reserve("A", 1))
        self.assertFalse(inv.reserve("A", 1))

    def test_no_oversell_under_concurrency(self):
        runs, threads, oversold = 100, 8, 0
        for _ in range(runs):
            inv, results = Inventory(SlowRepo(stock=1)), []
            barrier = threading.Barrier(threads)
            workers = [threading.Thread(target=_worker, args=(inv, barrier, results)) for _ in range(threads)]
            for t in workers:
                t.start()
            for t in workers:
                t.join(timeout=5)
            if sum(results) > 1:  # Stock was 1, but multiple threads successfully reserved
                oversold += 1
        self.assertEqual(oversold, 0, f"oversell in {oversold}/{runs} runs")


if __name__ == "__main__":
    unittest.main()
```
> Note: Pass parameters via worker `args` rather than closure captures to avoid late-binding pitfalls inside test code.

## 7. Common Python Pitfalls & Bug Patterns
- **Mutable default arguments:** `def add(item, items=[])` shares state across calls.
- **Banker's rounding in financial calculations:** `round()` rounds to nearest even, and `float` introduces IEEE 754 precision issues (`0.1 + 0.2 != 0.3`). Use `Decimal` with `ROUND_HALF_UP`.
- **Late binding in closures:** `[lambda: i for i in range(5)]` captures variable references, resolving to 4 for all lambdas.
- **Shallow copying:** `dict.copy()` or `list[:]` on nested collections mutates the original data when inner items change.
- **Missing `await`:** Leaves coroutine unexecuted and silently returns a coroutine object.
- **Bare `except:` or `except Exception: pass`:** Swallows critical errors including `KeyboardInterrupt` or database timeouts.
- **Resource leaks:** Opening files, sockets, or database sessions without `with` context managers.
- **Injection:** Unsanitized f-strings in raw SQL queries or `subprocess.run(..., shell=True)` with user input.
- **Naive vs Aware datetime mismatches:** Comparing naive and aware datetimes raises `TypeError`; `datetime.utcnow()` yields naive UTC.
- **Mutating collections during iteration:** `RuntimeError: dictionary changed size during iteration` or silently skipped elements.
- **Identity `is` vs Equality `==`:** Comparing strings or numbers using `is` relies on CPython interning and fails on arbitrary values.
