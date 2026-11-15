# Go Adapter

## 1. Core Principles
- Go requires `*_test.go` inside the package directory; duplicate project to `S/sandbox/` via `python "<BH>" sandbox --s "$S" --mode create` (**never excludes `vendor/`**).
- Naming: `S/sandbox/<pkg_path>/bughunt_<TID>_test.go`; functions `TestR1H3_<ShortName>` (control: `TestR1H3_Control_<Name>`).
- Use `package <name>` (white-box) for unexported symbols or `package <name>_test` (black-box) for public APIs.
- Running `go test ./<S>/sandbox/...` from `ROOT` fails because sandbox has its own `go.mod`; use `go -C "$S/sandbox"` (Go 1.20+) or `--cwd "$S/sandbox"`.
- `bh.py` sets `GOCACHE` and `GOPROXY=off`. Always pass `-count=1` to bypass cached test passes.
- Relative `replace ../x` in `go.mod`: patch inside sandbox copy via `go -C "$S/sandbox" mod edit -replace=<mod>=<abs_path>`. If a parent `go.work` interferes, set `GOWORK=off`.

## 2. Executing Hypothesis Tests (`bh.py`)
- **Batch round:** `python "<BH>" round --s "$S" --round N` (auto-runs `go -C <sandbox> test -count=1 -v -run TestR{N}H{M} ./<pkg>/`).
- **Concurrency (`-race -count=50`):** `python "<BH>" run --s "$S" --tid <TID> -- go -C "$S/sandbox" test -count=1 -race -count=50 -v -run TestR1H3 ./pkg/auth/` (Windows `-race` requires cgo+gcc; fallback to multi-iteration tallying). Race detector emits `WARNING: DATA RACE`.

## 3. Baseline Commands (run from `ROOT` — `./...` skips dot-dirs like `.bughunt`)
- `python "<BH>" run --s "$S" --tid baseline -- go test -count=1 ./...`
- `python "<BH>" run --s "$S" --tid baseline_vet -- go vet ./...` (`golangci-lint run` if used; `bh.py` sets `GOLANGCI_LINT_CACHE`)

## 4. Example (`S/sandbox/pkg/auth/bughunt_r1_h3_test.go`)
```go
// ID: R1-H3 | TID: r1_h3 | Target: pkg/auth/token.go:ValidateToken, session.go:Store.Touch
// Run: go -C .bughunt/<SNAME>/sandbox test -count=1 -race -v -run TestR1H3 ./pkg/auth/
package auth

import (
	"sync"
	"testing"
	"time"
)

func TestR1H3_Control_ValidTokenPasses(t *testing.T) {
	if !ValidateToken(&Token{ExpiresAt: time.Now().Add(time.Minute)}, time.Now()) {
		t.Fatal("control: valid token must pass")
	}
}

func TestR1H3_ExpiredAtBoundaryRejected(t *testing.T) {
	now := time.Now()
	if ValidateToken(&Token{ExpiresAt: now}, now) { t.Fatal("ExpiresAt == now must reject") }
}

func TestR1H3_ConcurrentTouch(t *testing.T) {
	store, start, workers := NewStore(), make(chan struct{}), 100
	var wg sync.WaitGroup
	for i := 0; i < workers; i++ {
		wg.Add(1); go func() { defer wg.Done(); <-start; store.Touch("s1") }()
	}
	close(start); wg.Wait()
	if got := store.HitCount("s1"); got != workers { t.Fatalf("lost updates: %d/%d", got, workers) }
}
```

## 5. Common Go Pitfalls
- **Goroutine leaks:** Blocked on channels or ignoring `ctx.Done()`.
- **Map/slice data races:** Concurrent map read/write without `sync.RWMutex` crashes with `fatal error: concurrent map writes`.
- **Typed nil in interface:** Interface wrapping typed nil pointer evaluates `val != nil`.
- **Slice aliasing:** `append` mutating shared backing array.
- **`defer` in loops:** Cleanup waits until function return, exhausting FDs/connections.
- **Loop var capture (Go < 1.22):** Goroutines observe final loop value.
- **Ignored errors:** `_ := f()` or unchecked `Close()`/`Commit()` errors.
- **Unclosed `resp.Body` / missing HTTP timeouts:** Leaks connections or hangs indefinitely.
- **Uncanceled/unpropagated `context.Context`:** Orphaned work after request cancel.
