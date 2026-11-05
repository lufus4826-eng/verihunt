# Bug Taxonomy Checklist

Applicable across all languages (language-specific patterns reside in `lang/<language>.md`). Used during Phase 2 hypothesis generation and Phase 4 confidence validation. Every category must be documented in the final report as either "Tested (<ID>)" or "Irrelevant — <rationale>".

| # | Category | Common Inspection Targets |
|---|---|---|
| 1 | **Input & Edge Cases** | null/nil/undefined, empty strings/collections, boundary values, off-by-one, oversized payloads, Unicode/emoji/special characters, zero-width spaces |
| 2 | **Error Handling** | Swallowed exceptions (silent catch), unforwarded errors, missing timeouts/retries, unbounded retry storms, partial failure leading to corrupted or stuck state |
| 3 | **Concurrency & Async** | Race conditions, missing `await`, deadlocks, double submits, non-idempotent operations, retry-induced duplicate processing |
| 4 | **State & Data** | Inadequate transaction scope, stale cache without invalidation, cross-service data divergence, soft-deleted records improperly included in queries |
| 5 | **Resource Management** | Connection/file descriptor/memory leaks, unclosed streams or sockets, unbounded queues, buffers, or loops |
| 6 | **Time & Numbers** | Timezone offsets, daylight saving transitions, Buddhist/Gregorian calendar mismatches, floating-point math in financial calculations, precision loss, integer overflow/underflow, division by zero |
| 7 | **Security** | Injections (SQL, command, template), authorization/access control bypass (IDOR), secret leaks in logs/traces, unvalidated redirects, path traversal, SSRF |
| 8 | **Configuration & Environment** | Insecure defaults, dev vs prod drift, dependency version mismatches, stale feature flags |
| 9 | **API & Service Contracts** | Request/response schema divergence, uncoordinated schema migrations, nullable mismatches between API DTO and database schema |
| 10 | **Data Migration & Compatibility** | Irreversible migrations, legacy records failing newer validation logic, rolling deployments where mixed versions read shared state |
| 11 | **Stability-Impacting Performance** | N+1 query patterns, heavy blocking tasks on the main thread/event loop, unbounded queries lacking pagination, catastrophic regex backtracking (ReDoS) |
| 12 | **Localization & Internationalization (I18n)** | Sorting/searching multi-byte text, word breaking across vowels/accents (e.g., Thai/CJK), locale-specific digits, Buddhist era (B.E.) dates, CSV/Excel encoding issues (UTF-8 BOM) |
