# Python Adapter

## 1. Execution & Isolation (`bh.py` auto-sets `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUTF8=1`)
- Prefer project venv (`.venv`, `venv`, `poetry run`, `uv run --no-sync`). `bh.py round` auto-detects `.venv` and prefers `python -m pytest -p no:cacheprovider -v`, falling back to `python -m unittest discover` when `pytest` is absent.
- **Always invoke pytest via `python -m pytest`** (direct `pytest` omits `ROOT` from `sys.path`, causing `exit=2` import errors) and pass `-p no:cacheprovider` to block `.pytest_cache`.
- Batch run: `python "<BH>" round --s "$S" --round N`
- Single run (custom flags): `python "<BH>" run --s "$S" --tid <TID> -- python -m pytest "$S/tests/test_${TID}_x.py" -p no:cacheprovider -v`
- `unittest` fallback (direct file if needed, since `.bughunt` starts with a dot): `PYTHONPATH=. python "$S/tests/test_${TID}_x.py" -v`

## 2. Pytest Config & Environment Checks
- **`addopts`** (`pytest.ini`/`pyproject.toml`/`setup.cfg`): If `--cov`, `--junitxml`, or `--html` writes to `ROOT`, override with `-o addopts=""` + required plugins (`-p pytest_django`, `--import-mode=importlib`) or `--no-cov`.
- **Root `conftest.py`:** Discovered automatically under `ROOT`. Audit `autouse=True` fixtures before running to ensure zero live DB/API connections.
- **Django:** Point `DJANGO_SETTINGS_MODULE` (or `--ds=`) to test settings using in-memory SQLite.
- **Timeouts & Async:** Use `--timeout=60` if `pytest-timeout` is installed; otherwise enforce `future.result(timeout=...)` / `thread.join(timeout=...)`. Use `pytest-asyncio`/`anyio` if configured, or `asyncio.run()`.
- **`subTest` warning:** On modern pytest, outer tests can show `PASSED` despite `SUBFAILED(...)`; `bh.py` checks summary counts (`N failed`) + `SUBFAILED`.

## 3. Baseline Commands (via `bh.py run --s "$S" --tid baseline -- ...`)
```text
python -m pytest -p no:cacheprovider -q
python -m mypy --cache-dir "$CACHE/mypy" .        # bh.py sets MYPY_CACHE_DIR automatically
ruff check --no-cache .
python -m flake8 .
```

## 4. Examples (`S/tests/test_r1_h2_discount_rounding.py` & `test_r2_h1_reserve_race.py`)
```python
# ID: R1-H2 | TID: r1_h2 | Target: app/billing/discount.py:apply_discount
# Run: python -m pytest .bughunt/<SNAME>/tests/test_r1_h2_discount_rounding.py -p no:cacheprovider -v
import unittest
from decimal import Decimal
from app.billing.discount import apply_discount

class TestR1H2DiscountRounding(unittest.TestCase):
    def test_control_no_rounding(self):
        self.assertEqual(apply_discount(total=Decimal("100.00"), rate=Decimal("0.10")), Decimal("10.00"))

    def test_half_cent_rounds_up(self):
        for total, expected in [("1.25", "0.13"), ("0.05", "0.01"), ("2.25", "0.23")]:
            with self.subTest(total=total):
                self.assertEqual(apply_discount(total=Decimal(total), rate=Decimal("0.10")), Decimal(expected))

if __name__ == "__main__":
    unittest.main()
```
```python
# ID: R2-H1 | TID: r2_h1 | Target: app/inventory.py:Inventory.reserve
# Run: python -m pytest .bughunt/<SNAME>/tests/test_r2_h1_reserve_race.py -p no:cacheprovider -v
import threading, time, unittest
from app.inventory import Inventory

class SlowRepo:
    def __init__(self, stock): self.data = {"A": stock}
    def get_stock(self, sku):
        v = self.data[sku]; time.sleep(0.001); return v  # Widen race window (1ms) without altering target logic
    def set_stock(self, sku, v): self.data[sku] = v

def _worker(inv, barrier, results):  # Pass state via args (avoids loop closure late-binding bug)
    barrier.wait()
    results.append(inv.reserve("A", 1))

class TestR2H1ReserveRace(unittest.TestCase):
    def test_control_single_thread(self):
        inv = Inventory(SlowRepo(1))
        self.assertTrue(inv.reserve("A", 1))
        self.assertFalse(inv.reserve("A", 1))

    def test_no_oversell_under_concurrency(self):
        runs, threads, oversold = 100, 8, 0
        for _ in range(runs):
            inv, results, barrier = Inventory(SlowRepo(1)), [], threading.Barrier(threads)
            ws = [threading.Thread(target=_worker, args=(inv, barrier, results)) for _ in range(threads)]
            for t in ws: t.start()
            for t in ws: t.join(timeout=5)
            if sum(results) > 1: oversold += 1
        self.assertEqual(oversold, 0, f"oversell in {oversold}/{runs} runs")
```

## 5. Common Python Pitfalls
- **Mutable defaults:** `def add(item, items=[])` shares state across calls.
- **Banker's rounding / floats:** `round()` rounds to even; `float` fails `0.1 + 0.2 == 0.3`. Use `Decimal` + `ROUND_HALF_UP`.
- **Late binding in closures:** `[lambda: i for i in range(5)]` all return `4`.
- **Shallow copy:** `dict.copy()` / `list[:]` mutates nested objects.
- **Missing `await`:** Unawaited coroutine silently returns coroutine object.
- **Swallowed errors:** Bare `except:` or `except Exception: pass` hides failures/`KeyboardInterrupt`.
- **Resource leaks:** Missing `with` around files, sockets, or DB sessions.
- **Injection:** Raw f-string SQL or `subprocess.run(..., shell=True)` with user input.
- **Naive vs aware `datetime`:** `TypeError` on comparison; `datetime.utcnow()` is naive.
- **Mutating while iterating:** `RuntimeError` or skipped items on `dict`/`list`.
- **`is` vs `==`:** `is` checks identity (fails beyond interned small ints/strings).
