# Rust Adapter

## 1. Core Principles
- Always use `S/sandbox/` (`python "<BH>" sandbox --s "$S" --mode create`; auto-excludes `/target`). `bh.py` redirects `CARGO_TARGET_DIR` to `.bughunt/.cache/cargo-target`.
- Always pass `--offline --locked` on every `cargo` command (blocks crate downloads and lockfile edits).
- **Public APIs:** Integration test at `S/sandbox/tests/bughunt_<TID>.rs` (Cargo workspaces: inside crate's `tests/` + `-p <crate>`).
- **Private functions:** Append inline `#[cfg(test)] mod bughunt_<TID> { use super::*; ... }` in the **sandbox copy** and run `--lib bughunt_<TID>`.
- Rewrite external relative `path = "../x"` dependencies in `S/sandbox/Cargo.toml` to absolute paths if needed.

## 2. Executing Hypothesis Tests & Baseline (`bh.py`)
- **Batch round:** `python "<BH>" round --s "$S" --round N` (auto-runs `cargo test --offline --locked --manifest-path "$S/sandbox/Cargo.toml" --test bughunt_<TID>`).
- **Private unit tests / `--release` overflow check:**
  - `python "<BH>" run --s "$S" --tid <TID> -- cargo test --offline --locked --manifest-path "$S/sandbox/Cargo.toml" --lib bughunt_<TID>`
  - Integer overflow: test debug AND `--release` (`release` disables `overflow-checks`, wrapping silently).
- **Baseline (from `ROOT` since `CARGO_TARGET_DIR` is redirected):**
  - `python "<BH>" run --s "$S" --tid baseline -- cargo test --offline --locked`
  - `python "<BH>" run --s "$S" --tid baseline_clippy -- cargo clippy --offline --locked`

## 3. Example (`S/sandbox/tests/bughunt_r1_h7.rs`)
```rust
// ID: R1-H7 | TID: r1_h7 | Target: src/billing.rs:parse_amount
// Run: cargo test --offline --locked --manifest-path .bughunt/<SNAME>/sandbox/Cargo.toml --test bughunt_r1_h7
use my_crate::billing::parse_amount;

#[test]
fn control_parses_plain_amount() { assert_eq!(parse_amount("12.50"), Ok(1250)); }

#[test]
fn rejects_overflow_instead_of_panicking() {
    let res = std::panic::catch_unwind(|| parse_amount("99999999999999999999.99"));
    assert!(matches!(res, Ok(Err(_))), "expected Err, got {:?}", res.map(|r| r.is_ok()));
}
```

## 4. Common Rust Pitfalls
- **`.unwrap()` / `.expect()` panics** on `None`/`Err` inputs or poisoned locks.
- **Silent integer overflow in `--release` & truncating `as` casts** (`u64 as u32`, `f64 as i32`).
- **Holding `std::sync::Mutex` across `.await`** or inconsistent multi-lock ordering (deadlocks).
- **Blocking in async runtime:** `std::thread::sleep` or sync I/O starving tokio workers.
- **Reference cycles:** `Rc<RefCell<T>>` / `Arc<Mutex<T>>` memory leaks.
- **Byte-index string slicing (`&s[..n]`):** Panics across multi-byte UTF-8 boundaries (Thai, CJK, emoji).
