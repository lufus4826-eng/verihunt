# Rust Adapter

## 1. Core Principles
- Always use `S/sandbox/` (exclude `/target` during sandbox copy) and redirect `CARGO_TARGET_DIR` to the central cache folder to accelerate rebuilds within the session.
- Always include `--offline --locked` on every cargo invocation: guarantees zero network downloading of crates and prevents any changes to `Cargo.lock`.
- **Testing Public APIs:** Add integration tests at `S/sandbox/tests/bughunt_<TID>.rs` (In Cargo workspaces, place inside the specific crate's `tests/` directory and append `-p <crate_name>`).
- **Testing Private Functions:** Append an inline test module to the target source file in the **sandbox copy**: `#[cfg(test)] mod bughunt_<TID> { use super::*; ... }`, then invoke via `--lib bughunt_<TID>`.
- Relative path dependencies (`path = "../x"`) in `Cargo.toml` pointing outside ROOT can be rewritten to absolute paths in the **sandbox copy**.

## 2. Executing Hypothesis Tests
```bash
CARGO_TARGET_DIR="$CACHE/cargo-target" cargo test --offline --locked --manifest-path "$S/sandbox/Cargo.toml" \
  --test bughunt_${TID} > "$S/logs/$TID.log" 2>&1; echo "exit=$?" >> "$S/logs/$TID.log"
# For private unit tests: replace --test bughunt_${TID} with --lib bughunt_${TID}
```
```powershell
$env:CARGO_TARGET_DIR = "$CACHE\cargo-target"
cmd /c "cargo test --offline --locked --manifest-path `"$S\sandbox\Cargo.toml`" --test bughunt_$TID > `"$S\logs\$TID.log`" 2>&1"; "exit=$LASTEXITCODE" | Add-Content "$S\logs\$TID.log"
```
- Integer overflow defects: Test both in standard debug mode and with `--release` (release profiles disable `overflow-checks` by default, wrapping around silently instead of panicking).

## 3. Baseline Commands (Runnable from ROOT because target dir is redirected to cache)
```bash
CARGO_TARGET_DIR="$CACHE/cargo-target" cargo test --offline --locked
CARGO_TARGET_DIR="$CACHE/cargo-target" cargo clippy --offline --locked
```

## 4. Example (`S/sandbox/tests/bughunt_r1_h7.rs`)
```rust
// ID: R1-H7 | TID: r1_h7
// Target: src/billing.rs:parse_amount (public API)
// Run: cargo test --offline --locked --manifest-path .bughunt/<SNAME>/sandbox/Cargo.toml --test bughunt_r1_h7
use my_crate::billing::parse_amount;

#[test]
fn control_parses_plain_amount() {
    assert_eq!(parse_amount("12.50"), Ok(1250));
}

#[test]
fn rejects_amount_that_overflows_instead_of_panicking() {
    // Desired behavior: returns Err rather than panicking on unwrap or arithmetic overflow
    let result = std::panic::catch_unwind(|| parse_amount("99999999999999999999.99"));
    assert!(matches!(result, Ok(Err(_))), "expected Err, got panic or Ok: {:?}", result.map(|r| r.is_ok()));
}
```

## 5. Common Rust Pitfalls & Bug Patterns
- **Panics on `.unwrap()` / `.expect()`:** Triggered when inputs yield `None` or `Err` in production (parsing, slicing, lock poisoning).
- **Silent integer overflow in release mode:** Debug builds panic, but release builds wrap silently. Truncating integer casts using `as` (`u64 as u32`, `f64 as i32`) drop upper bits without warning.
- **Holding `std::sync::Mutex` guards across `.await` points:** Triggers deadlocks or prevents future sends; use `tokio::sync::Mutex` or restructure to drop guards before await.
- **Lock ordering deadlocks:** Acquiring multiple mutexes in non-deterministic order across threads.
- **Blocking operations in async executors:** Calling `std::thread::sleep` or synchronous file/network I/O inside tokio worker threads starves the runtime.
- **Memory leaks via reference cycles:** Using `Rc<RefCell<T>>` or `Arc<Mutex<T>>` with circular references.
- **String slicing on byte boundaries:** Slicing UTF-8 strings (`&s[..n]`) across multi-byte character boundaries panics at runtime (common with Thai, CJK, and emojis).
