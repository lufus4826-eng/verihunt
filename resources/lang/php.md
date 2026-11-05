# PHP Adapter

## 1. Core Principles
- **Filename must match class name** (Enforced by PHPUnit 10+): `S/tests/BugHuntR1H6<ShortName>Test.php` and `class BugHuntR1H6<ShortName>Test extends TestCase`.
- Execute from project ROOT via `php vendor/bin/phpunit` (compatible across Linux, macOS, and Windows). When executed from ROOT, `phpunit.xml` or `phpunit.xml.dist` will be discovered automatically, loading standard autoloaders. If no configuration exists, append `--bootstrap vendor/autoload.php`.
- Always include `--do-not-cache-result --no-coverage` to avoid writing cache files or coverage reports into the repository.
- Rely solely on existing `vendor/`. Never run `composer install` or `composer update`. If `vendor/` is missing, ask the user.
- **Frameworks (Laravel / Symfony):** Inspect `<php><env .../>` in `phpunit.xml` and `.env.testing`. Traits like `RefreshDatabase` execute migrations against the configured database; ensure it is strictly SQLite/in-memory. Test classes can extend `Tests\TestCase` via the project autoloader.

## 2. Executing Hypothesis Tests
```bash
php vendor/bin/phpunit --do-not-cache-result --no-coverage "$S/tests/BugHuntR1H6DiscountTest.php" \
  > "$S/logs/$TID.log" 2>&1; echo "exit=$?" >> "$S/logs/$TID.log"
```
```powershell
cmd /c "php vendor/bin/phpunit --do-not-cache-result --no-coverage `"$S\tests\BugHuntR1H6DiscountTest.php`" > `"$S\logs\$TID.log`" 2>&1"; "exit=$LASTEXITCODE" | Add-Content "$S\logs\$TID.log"
```
- Certain PHPUnit versions accept only a single target path argument. Execute files individually or point to the directory `S/tests/`.

## 3. Baseline Commands
```bash
php vendor/bin/phpunit --do-not-cache-result --no-coverage
php vendor/bin/phpstan analyse --memory-limit=1G # phpstan writes cache to OS temp
php vendor/bin/psalm --no-cache                  # If psalm is used
```

## 4. Example (`S/tests/BugHuntR1H6DiscountTest.php`)
```php
<?php
// ID: R1-H6 | TID: r1_h6
// Target: App\Billing\DiscountService::applyRate
// Run: php vendor/bin/phpunit --do-not-cache-result --no-coverage .bughunt/<SNAME>/tests/BugHuntR1H6DiscountTest.php
declare(strict_types=1);

use App\Billing\DiscountService;
use PHPUnit\Framework\TestCase;

final class BugHuntR1H6DiscountTest extends TestCase
{
    public function testControlNoRoundingNeeded(): void
    {
        $this->assertSame('10.00', (new DiscountService())->applyRate('100.00', '0.10'));
    }

    public function testCouponCodeComparisonIsStrict(): void
    {
        // If code uses ==, strings like "0e123" and "0e456" are coerced as scientific notation and evaluate equal (magic hash bug)
        $this->assertFalse((new DiscountService())->isValidCoupon('0e1234', '0e5678'));
    }
}
```

## 5. Common PHP Pitfalls & Bug Patterns
- **Loose equality (`==` vs `===`):** `"0e123" == "0e456"` is true (scientific notation coercion); `0 == "a"` evaluated to true in PHP < 8.
- **`in_array` / `array_search` lacking strict flag:** Defaults to non-strict comparison (`strict: false`).
- **`strpos()` returning 0:** Evaluating `if (strpos($s, 'x'))` fails when the needle is at index 0. Must use `!== false`.
- **References in `foreach ($arr as &$item)`:** Failing to `unset($item)` after loop completion leads to subsequent loops corrupting the final array element.
- **`array_merge` reindexing numeric keys:** Numeric keys are renumbered starting from 0. Use `+` union or `array_replace` if preserving keys.
- **Mutable `DateTime` objects:** Method calls like `->modify()` mutate the instance in place. Use `DateTimeImmutable`.
- **Floating-point currency math & unconfigured default timezones.**
- **SQL injection via string interpolation** instead of prepared statements; passing user input into `unserialize()`.
- **Exceptions thrown inside `finally` blocks:** Discards the original exception that was in flight.
