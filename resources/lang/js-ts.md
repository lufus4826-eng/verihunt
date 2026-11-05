# JavaScript / TypeScript Adapter

## 1. Core Principles
- **Relative path from `S/tests/` to ROOT is `../../../`** (`tests` -> `S` -> `.bughunt` -> `ROOT`). Example: `require('../../../src/auth/token')`.
- **Inspect `"type"` in `package.json`:** If `"type": "module"` (ESM), use `import` syntax in `.mjs` or `.js` files. If CommonJS, use `require` or name test files `.mjs` when using `import`.
- **Always invoke CLI tools with `npx --no-install`:** Prevents npx from silently downloading packages from npm when tools are missing locally.
- Runner selection hierarchy:
  1. Project's configured runner (Jest / Vitest / Mocha) when code requires transformations (TypeScript, JSX, path aliases).
  2. Built-in `node --test` (Node 18+) for pure JavaScript. Requires no extra dependencies and writes zero disk caches.
- TypeScript: Use the project's runner or `npx --no-install tsx --test`. Node 23.6+ can execute `.ts` files directly via `node --test` provided they do not use enums, namespaces, or path aliases.
- Use `--test-reporter=tap` to produce clean, plain ASCII logs containing parseable `# tests N` and `# fail N` metrics for harness validation.

## 2. Executing Hypothesis Tests
**node --test**
```bash
node --test --test-reporter=tap "$S"/tests/test_${TID}_*.test.*js > "$S/logs/$TID.log" 2>&1; echo "exit=$?" >> "$S/logs/$TID.log"
```
```powershell
$files = (Get-ChildItem "$S\tests\test_${TID}_*.test.*js" | ForEach-Object { '"' + $_.FullName + '"' }) -join ' '
cmd /c "node --test --test-reporter=tap $files > `"$S\logs\$TID.log`" 2>&1"; "exit=$LASTEXITCODE" | Add-Content "$S\logs\$TID.log"
```
> Notice: `node --test` flags `MODULE_NOT_FOUND` as `not ok` with an exit code of 1, **identical to legitimate assertion failures**. Always inspect logs before deciding verdicts.

**Jest** — Reuse project configuration for transforms/aliases while isolating cache and overriding roots:
```bash
npx --no-install jest --ci --coverage=false --cacheDirectory="$CACHE/jest" --roots="$PWD/$S/tests" \
  > "$S/logs/$TID.log" 2>&1; echo "exit=$?" >> "$S/logs/$TID.log"
```
- Filenames matching `test_<TID>_x.test.js` align with Jest's default `testMatch`. To isolate a specific file, append the pattern `test_${TID}_`.
- If `No tests found` occurs: Inspect `testMatch`, `testRegex`, and `testPathIgnorePatterns` in project configs. If needed, create `S/jest.bughunt.config.cjs` that requires the base config and overrides conflicting matchers. If code requires no transform, fall back to `node --test`.

**Vitest** — `mergeConfig` concatenates arrays (combining existing and new includes); explicitly assign `include` after merging:
```ts
// S/vitest.bughunt.config.mts
import { defineConfig, mergeConfig } from 'vitest/config'
import base from '../../vitest.config'   // Or '../../vite.config' based on project
const cfg = mergeConfig(base, defineConfig({
  cacheDir: '.bughunt/.cache/vitest',
  test: { coverage: { enabled: false } },
}))
cfg.test.include = ['.bughunt/<SNAME>/tests/**/*.test.?(c|m)[jt]s?(x)']
export default cfg
```
```bash
npx --no-install vitest run --config "$S/vitest.bughunt.config.mts" > "$S/logs/$TID.log" 2>&1; echo "exit=$?" >> "$S/logs/$TID.log"
```

**Mocha**
```bash
npx --no-install mocha --no-config --timeout 10000 "$S"/tests/test_${TID}_*.test.*js > "$S/logs/$TID.log" 2>&1; echo "exit=$?" >> "$S/logs/$TID.log"
```

## 3. Baseline Commands
- **Inspect `scripts` in `package.json` first:** Run `npm test` as specified. Do not append runner-specific flags across mismatched runners (e.g., `--cacheDirectory` is invalid for Mocha or Vitest).
- If Jest: `npx --no-install jest --ci --coverage=false --cacheDirectory="$CACHE/jest"`
- If Vitest: `npx --no-install vitest run --coverage.enabled=false`
```bash
npx --no-install eslint --cache --cache-location "$CACHE/eslint/" .
npx --no-install tsc --noEmit # If incremental build enabled, append --tsBuildInfoFile "$CACHE/tsbuildinfo"
```

## 4. Example (`S/tests/test_r1_h1_token_expiry.test.js`)
```javascript
// ID: R1-H1 | TID: r1_h1
// Target: src/auth/token.js:isTokenExpired, src/checkout/service.js:createCheckout
// Run: node --test --test-reporter=tap .bughunt/<SNAME>/tests/test_r1_h1_token_expiry.test.js
const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const { isTokenExpired } = require('../../../src/auth/token');      // tests -> S -> .bughunt -> ROOT
const { createCheckout } = require('../../../src/checkout/service');

describe('R1-H1: token boundary', () => {
  it('control: valid non-expired token must pass', () => {
    assert.equal(isTokenExpired({ exp: 1700000010 }, 1700000000), false);
  });

  it('token with exp timestamp equal to current time must be treated as expired', () => {
    // If implementation uses `exp < now` instead of `exp <= now`, this test FAILS
    assert.equal(isTokenExpired({ exp: 1700000000 }, 1700000000), true);
  });
});

describe('R1-H1b: double submit concurrency', () => {
  // Asynchronous fake gateway: introduces event-loop tick between check and act
  const makeGateway = () => ({
    charges: 0,
    async charge() { await new Promise((r) => setImmediate(r)); this.charges += 1; },
  });

  it('control: single submission results in single charge', async () => {
    const gateway = makeGateway();
    await createCheckout({ gateway }).submit('order-1');
    assert.equal(gateway.charges, 1);
  });

  it('submitting the same order concurrently must execute only one charge', async () => {
    const gateway = makeGateway();
    const svc = createCheckout({ gateway });
    await Promise.all([svc.submit('order-1'), svc.submit('order-1')]);
    assert.equal(gateway.charges, 1, `charged ${gateway.charges} times`);
  });
});
```

## 5. Common JS/TS Pitfalls & Bug Patterns
- **Missing `await` & async inside `forEach`:** `arr.forEach(async x => ...)` does not await promises; errors escape as unhandled rejections.
- **Floating-point inaccuracies:** `0.1 + 0.2 !== 0.3`. Financial logic must use integer cents or dedicated decimal libraries.
- **Integers exceeding 2^53:** IDs from databases or JSON exceeding `Number.MAX_SAFE_INTEGER` lose precision silently.
- **Loose equality (`==` vs `===`):** `"" == 0` evaluates to true; `null == undefined` evaluates to true.
- **Unchecked optional chaining:** `obj?.prop.nested` throws `TypeError` when `obj` is truthy but `prop` is `undefined`.
- **Default string sorting in `Array.prototype.sort()`:** `[10, 9, 1].sort()` yields `[1, 10, 9]`.
- **Date constructor pitfalls:** Month index starts at 0; `new Date('2024-01-01')` parses as UTC, whereas `new Date('2024-01-01T00:00')` parses in local time.
- **Shallow copying:** `{ ...state }` or `Object.assign` mutates inner references in deeply nested structures.
- **Prototype pollution:** Unsanitized recursive object merging assigning into `__proto__`, `constructor`, or `prototype`.
- **Listener / interval / stream leaks:** Missing `removeEventListener`, `clearInterval`, or stream drain listeners on teardown.
