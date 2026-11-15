# JavaScript / TypeScript Adapter

## 1. Core Principles
- **Relative path from `S/tests/` to `ROOT` is `../../../`** (`tests` -> `S` -> `.bughunt` -> `ROOT`), e.g. `require('../../../src/auth/token')`.
- **Check `"type"` in `package.json`:** `"module"` (ESM) -> `import` in `.mjs`/`.js`; CommonJS -> `require` (or `.mjs` for `import`).
- **Always use `npx --no-install <tool>`** to prevent silent npm downloads.
- **Runner selection:** (1) Project's Jest / Vitest / Mocha when TS/JSX/path-aliases need transforms; (2) built-in `node --test --test-reporter=tap` (Node 18+, zero cache/deps) for plain JS. TS: project runner, `npx --no-install tsx --test`, or Node 23.6+ `node --test` (if no enums/namespaces/path-aliases).
- **Critical `node --test` trap:** `MODULE_NOT_FOUND` / `SyntaxError` / `ERR_REQUIRE_ESM` exits `1` just like an assertion failure! `bh.py` checks TAP + error signals automatically.

## 2. Executing Hypothesis Tests (`bh.py`)
- **Batch (`node --test` default, or auto-detects `S/vitest.bughunt.config.mts` / `S/jest.bughunt.config.cjs`):** `python "<BH>" round --s "$S" --round N [--runner node|jest|vitest|mocha]`
- **Single run:**
  - `node --test`: `python "<BH>" run --s "$S" --tid <TID> -- node --test --test-reporter=tap "$S/tests/test_${TID}_x.test.js"`
  - **Jest:** `python "<BH>" run --s "$S" --tid <TID> --runner jest -- npx --no-install jest --ci --coverage=false --cacheDirectory="$CACHE/jest" --roots="$PWD/$S/tests" test_${TID}_`
    - If `No tests found`, check `testMatch`/`testRegex`/`testPathIgnorePatterns` and write `S/jest.bughunt.config.cjs` extending the base config with `--config`.
  - **Vitest** (`mergeConfig` appends arrays, so overwrite `cfg.test.include` after merging):
    ```ts
    // S/vitest.bughunt.config.mts
    import { defineConfig, mergeConfig } from 'vitest/config'
    import base from '../../vitest.config' // or '../../vite.config'
    const cfg = mergeConfig(base, defineConfig({ cacheDir: '.bughunt/.cache/vitest', test: { coverage: { enabled: false } } }))
    cfg.test.include = ['.bughunt/<SNAME>/tests/**/*.test.?(c|m)[jt]s?(x)']
    export default cfg
    ```
    Run: `python "<BH>" run --s "$S" --tid <TID> --runner vitest -- npx --no-install vitest run --config "$S/vitest.bughunt.config.mts"`
  - **Mocha:** `python "<BH>" run --s "$S" --tid <TID> --runner mocha -- npx --no-install mocha --no-config --timeout 10000 "$S/tests/test_${TID}_x.test.js"`

## 3. Baseline Commands (via `bh.py run --s "$S" --tid baseline -- ...`)
Inspect `package.json` `scripts` first; never pass Jest flags (e.g. `--cacheDirectory`) to Vitest/Mocha:
- `npm test` | `npx --no-install jest --ci --coverage=false --cacheDirectory="$CACHE/jest"` | `npx --no-install vitest run --coverage.enabled=false`
- `npx --no-install eslint --cache --cache-location "$CACHE/eslint/" .`
- `npx --no-install tsc --noEmit --tsBuildInfoFile "$CACHE/tsbuildinfo"` (if incremental)

## 4. Example (`S/tests/test_r1_h1_token_expiry.test.js`)
```javascript
// ID: R1-H1 | TID: r1_h1 | Target: src/auth/token.js:isTokenExpired, src/checkout/service.js:createCheckout
// Run: node --test --test-reporter=tap .bughunt/<SNAME>/tests/test_r1_h1_token_expiry.test.js
const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const { isTokenExpired } = require('../../../src/auth/token');
const { createCheckout } = require('../../../src/checkout/service');

describe('R1-H1: token boundary & double submit', () => {
  it('control: valid token passes', () => {
    assert.equal(isTokenExpired({ exp: 1700000010 }, 1700000000), false);
  });
  it('token expiring at exact now is expired', () => {
    assert.equal(isTokenExpired({ exp: 1700000000 }, 1700000000), true);
  });
  // Async fake yields event-loop tick between check and act
  const makeGw = () => ({ charges: 0, async charge() { await new Promise((r) => setImmediate(r)); this.charges += 1; } });
  it('control: single submit charges once', async () => {
    const gw = makeGw(); await createCheckout({ gateway: gw }).submit('o1'); assert.equal(gw.charges, 1);
  });
  it('concurrent submits charge only once', async () => {
    const gw = makeGw(); const svc = createCheckout({ gateway: gw });
    await Promise.all([svc.submit('o1'), svc.submit('o1')]);
    assert.equal(gw.charges, 1, `charged ${gw.charges} times`);
  });
});
```

## 5. Common JS/TS Pitfalls
- **Missing `await` / `arr.forEach(async ...)`:** Promises aren't awaited; unhandled rejections escape.
- **Floating point:** `0.1 + 0.2 !== 0.3`; use integer cents or decimal library.
- **Safe integer overflow:** IDs `> 2^53 - 1` (`Number.MAX_SAFE_INTEGER`) lose precision silently.
- **Loose equality (`==`):** `"" == 0` and `null == undefined` are `true`.
- **Partial optional chaining:** `obj?.prop.nested` throws when `obj` exists and `prop` is `undefined`.
- **`Array.prototype.sort()`:** `[10, 9, 1].sort()` sorts lexicographically (`[1, 10, 9]`).
- **`Date` pitfalls:** Months are 0-indexed; `new Date('2024-01-01')` is UTC while `'2024-01-01T00:00'` is local time.
- **Shallow copy:** `{ ...state }` / `Object.assign` leaks nested object mutations.
- **Prototype pollution:** Unsanitized recursive merge writing `__proto__`/`constructor`/`prototype`.
- **Resource leaks:** Missing `removeEventListener`, `clearInterval`, or stream teardown.
