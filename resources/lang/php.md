# PHP Adapter

## 1. Core Principles
- **Filename must match class name** (PHPUnit 10+): `S/tests/BugHuntR1H6<ShortName>Test.php` with `class BugHuntR1H6<ShortName>Test extends TestCase`.
- Run from `ROOT` via `php vendor/bin/phpunit` (discovers `phpunit.xml`/`phpunit.xml.dist`; add `--bootstrap vendor/autoload.php` if absent).
- Always pass `--do-not-cache-result --no-coverage` to prevent root cache/coverage files.
- Rely strictly on existing `vendor/`. NEVER run `composer install/update`; ask user if `vendor/` is missing.
- **Laravel / Symfony:** Inspect `<php><env .../>` in `phpunit.xml` and `.env.testing` first. Traits like `RefreshDatabase` migrate the configured DB — verify it is SQLite/in-memory only.

## 2. Executing Hypothesis Tests & Baseline (`bh.py`)
- **Batch round:** `python "<BH>" round --s "$S" --round N` (auto-runs `php vendor/bin/phpunit --do-not-cache-result --no-coverage <file>` per TID, handling PHPUnit versions that accept only 1 path).
- **Single run:** `python "<BH>" run --s "$S" --tid <TID> -- php vendor/bin/phpunit --do-not-cache-result --no-coverage "$S/tests/BugHuntR1H6DiscountTest.php"`
- **Baseline:** `python "<BH>" run --s "$S" --tid baseline -- php vendor/bin/phpunit --do-not-cache-result --no-coverage` (plus `phpstan analyse --memory-limit=1G` or `psalm --no-cache` if used).

## 3. Example (`S/tests/BugHuntR1H6DiscountTest.php`)
```php
<?php
// ID: R1-H6 | TID: r1_h6 | Target: App\Billing\DiscountService::applyRate
// Run: php vendor/bin/phpunit --do-not-cache-result --no-coverage .bughunt/<SNAME>/tests/BugHuntR1H6DiscountTest.php
declare(strict_types=1);

use App\Billing\DiscountService;
use PHPUnit\Framework\TestCase;

final class BugHuntR1H6DiscountTest extends TestCase
{
    public function testControlNoRoundingNeeded(): void {
        $this->assertSame('10.00', (new DiscountService())->applyRate('100.00', '0.10'));
    }
    public function testCouponCodeComparisonIsStrict(): void {
        $this->assertFalse((new DiscountService())->isValidCoupon('0e1234', '0e5678')); // == treats 0e* as 0
    }
}
```

## 4. Common PHP Pitfalls
- **Loose `==` vs `===`:** `"0e123" == "0e456"` is `true` (magic hash); `0 == "a"` in PHP < 8.
- **`in_array` / `array_search` without `strict: true`.**
- **`strpos()` returning `0`:** `if (strpos($s, 'x'))` fails at index 0; use `!== false`.
- **Reference leak in `foreach ($arr as &$item)`:** Missing `unset($item)` corrupts last element in later loops.
- **`array_merge` reindexing numeric keys:** Use `+` union or `array_replace` to preserve keys.
- **Mutable `DateTime`:** `->modify()` mutates shared instance; prefer `DateTimeImmutable`.
- **Float currency math & unset default timezone.**
- **SQL string interpolation & `unserialize()` on untrusted input.**
- **Exceptions in `finally`:** Silently discards the original in-flight exception.
