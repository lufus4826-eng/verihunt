# Go Adapter

## 1. Core Principles
- Go requires `*_test.go` files to reside in the exact package directory being tested. Therefore, tests must be added inside `S/sandbox/` (see sandbox cloning in `00-common.md`; **never exclude `vendor/`**).
- Naming convention: `S/sandbox/<pkg_path>/bughunt_<TID>_test.go`; test function: `TestR1H3_<ShortName>`.
- Use `package <original_name>` (white-box) to test unexported functions or internal state, or `package <original_name>_test` (black-box) for public APIs.
- The sandbox contains its own `go.mod`. Therefore, **running `go test ./<S>/sandbox/...` from ROOT fails**. You must invoke via `go -C <sandbox>` (Go 1.20+) or `cd` into the sandbox.
- Redirect cache with `GOCACHE` and disable network fetching with `GOPROXY=off`. Always include `-count=1` to bypass cached test results.
- If `go.mod` contains relative `replace` directives pointing outside ROOT, patch them in the sandbox copy: `go -C "$S/sandbox" mod edit -replace=<module>=<absolute_path>`.
- If ROOT is part of a parent `go.work` workspace and the sandbox is detached, set `GOWORK=off`.

## 2. Executing Hypothesis Tests
```bash
GOCACHE="$CACHE/go-build" GOPROXY=off go -C "$S/sandbox" test -count=1 -v -run 'TestR1H3' ./pkg/auth/ \
  > "$S/logs/$TID.log" 2>&1; echo "exit=$?" >> "$S/logs/$TID.log"
# Go < 1.20 fallback
(cd "$S/sandbox" && GOCACHE="$CACHE/go-build" GOPROXY=off go test -count=1 -v -run 'TestR1H3' ./pkg/auth/) > "$S/logs/$TID.log" 2>&1
```
```powershell
$env:GOCACHE = "$CACHE\go-build"; $env:GOPROXY = "off"
cmd /c "go -C `"$S\sandbox`" test -count=1 -v -run TestR1H3 ./pkg/auth/ > `"$S\logs\$TID.log`" 2>&1"; "exit=$LASTEXITCODE" | Add-Content "$S\logs\$TID.log"
```
- Concurrency defects: Append `-race -count=50` (requires cgo and gcc on Windows; if unavailable, rely on multi-iteration tallying). When race detector triggers, the log records `WARNING: DATA RACE` and `race detected during execution of test`.

## 3. Baseline Commands (Runnable from ROOT because `./...` ignores directories starting with `.`)
```bash
GOCACHE="$CACHE/go-build" GOPROXY=off go test -count=1 ./...
GOCACHE="$CACHE/go-build" GOPROXY=off go vet ./...
GOLANGCI_LINT_CACHE="$CACHE/golangci-lint" GOCACHE="$CACHE/go-build" golangci-lint run # If used
```

## 4. Example (`S/sandbox/pkg/auth/bughunt_r1_h3_test.go`)
```go
// ID: R1-H3 | TID: r1_h3
// Target: pkg/auth/token.go:ValidateToken, pkg/auth/session.go:Store.Touch
// Run: go -C .bughunt/<SNAME>/sandbox test -count=1 -race -v -run TestR1H3 ./pkg/auth/
package auth

import (
	"sync"
	"testing"
	"time"
)

func TestR1H3_Control_ValidTokenPasses(t *testing.T) {
	now := time.Now()
	if !ValidateToken(&Token{ExpiresAt: now.Add(time.Minute)}, now) {
		t.Fatal("control: valid non-expired token must pass")
	}
}

func TestR1H3_ExpiredAtBoundaryRejected(t *testing.T) {
	now := time.Now()
	// Desired behavior: token expiring at the exact current second must be rejected
	if ValidateToken(&Token{ExpiresAt: now}, now) {
		t.Fatal("token with ExpiresAt == now must be rejected")
	}
}

func TestR1H3_ConcurrentTouchKeepsAllUpdates(t *testing.T) {
	store := NewStore()
	const workers = 100
	start := make(chan struct{})
	var wg sync.WaitGroup
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start // Synchronized worker release
			store.Touch("session-123")
		}()
	}
	close(start)
	wg.Wait()
	if got := store.HitCount("session-123"); got != workers {
		t.Fatalf("lost updates: got %d, want %d", got, workers)
	}
}
```

## 5. Common Go Pitfalls & Bug Patterns
- **Goroutine leaks:** Blocked on channels with no sender/receiver, or ignoring `ctx.Done()`.
- **Data races on maps/slices:** Concurrent map read/write without `sync.RWMutex` causes unrecoverable `fatal error: concurrent map writes`.
- **Nil interface vs Nil pointer:** An interface wrapping a typed nil pointer evaluates as non-nil (`val != nil` is true).
- **Slice header re-allocation & aliasing:** `append` unexpectedly mutating the underlying array shared by other slices.
- **`defer` inside loops:** Deferred cleanup functions (like `file.Close()`) do not execute until the enclosing function returns, exhausting file descriptors.
- **Loop variable capture in closures (Go < 1.22):** Goroutines capture variable reference, reading the final element repeatedly.
- **Ignored errors:** Discarding return values (`x, _ := f()`) or failing to check errors returned by `Close()` or `Commit()`.
- **Unclosed `resp.Body` in `http.Client`:** Causes connection leaks; clients lacking explicit timeouts hang indefinitely.
- **Context not propagated or canceled:** Background tasks continue consuming CPU/DB connections after HTTP client disconnects.
