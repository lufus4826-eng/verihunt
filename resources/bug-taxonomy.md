# Bug Taxonomy Checklist

Use in Phase 2 (hypotheses) and Phase 4/6 (confidence). Report every category as `"Audited (<ID>)"` or `"Irrelevant — <rationale>"`.

| # | Category | Inspection Targets |
|---|---|---|
| 1 | **Input & Edge Cases** | `null`/`nil`/`undefined`, empty values, boundaries, off-by-one, huge payloads, Unicode/emoji/zero-width spaces |
| 2 | **Error Handling** | Swallowed exceptions, unforwarded errors, missing timeouts/retries, retry storms, partial-fail stuck state |
| 3 | **Concurrency & Async** | Race conditions, missing `await`, deadlocks, double submits, non-idempotent retries |
| 4 | **State & Data** | Inadequate transaction scope, stale cache, cross-service drift, soft-deleted rows leaked in queries |
| 5 | **Resource Management** | Connection/FD/memory leaks, unclosed streams/sockets, unbounded queues, buffers, or loops |
| 6 | **Time & Numbers** | Timezones, DST, Buddhist/Gregorian calendars, float currency / banker's rounding, precision loss, overflow, div-by-zero |
| 7 | **Security** | SQL/cmd/template injection, auth/IDOR bypass, secret leaks in logs, open redirects, path traversal, SSRF |
| 8 | **Config & Environment** | Insecure defaults, dev/prod drift, dependency mismatches, stale feature flags |
| 9 | **API & Service Contracts** | Request/response schema drift, uncoordinated migrations, API DTO vs DB nullability mismatch |
| 10 | **Data Migration & Compatibility** | Irreversible migrations, legacy data failing new validation, mixed-version rolling deploy state |
| 11 | **Stability-Impacting Performance** | N+1 queries, blocking main thread/event loop, unbounded unpaginated queries, ReDoS regexes |
| 12 | **Localization & I18n** | Multi-byte sorting/search, slicing mid combining marks/vowels (Thai/CJK), locale digits, Buddhist Era dates, CSV/Excel UTF-8 BOM |
