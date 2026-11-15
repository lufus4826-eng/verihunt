# Java / Kotlin (JVM) Adapter

## 1. Core Principles
- Always use `S/sandbox/` (`python "<BH>" sandbox --s "$S" --mode create`) for both hypothesis tests and baseline checks; JVM builds write `target/`, `build/`, `.gradle/`.
- `bh.py sandbox` auto-excludes `target` and root `build`/`out` when `pom.xml`/`build.gradle*` exists (pass `--exclude <dir>` if nested `build`/`out` aren't source packages).
- File/class naming: `src/test/java/<pkg>/BugHuntR1H4<ShortName>Test.java` (or `.kt`); match package for package-private access and end with `Test` for Surefire/Gradle filters. Match JUnit 5 (`org.junit.jupiter.api.*`) or JUnit 4 (`org.junit.Test`).
- **Offline enforcement:** Maven `-o` (uses `~/.m2`; never set empty `maven.repo.local`); Gradle `--offline`. Use `mvnw`/`gradlew` if present; ask user if wrapper needs downloading a distribution.
- **PowerShell 5.1 note:** `bh.py` launches tools directly without shell splitting on `-Dkey=value` dots.
- **Spring Boot:** Avoid full `@SpringBootTest` hitting real DBs; test services directly, use test slices, or mock data sources after checking `application-test.*`.

## 2. Executing Hypothesis Tests & Baseline (`bh.py`)
- **Batch round:** `python "<BH>" round --s "$S" --round N` (auto-runs `mvn -o -B ... -Dtest=BugHuntR{N}H{M}*` or `gradlew --offline test --tests *BugHuntR{N}H{M}*`).
- **Single Maven (multi-module add `-pl <mod> -am`):** `python "<BH>" run --s "$S" --tid <TID> -- mvn -o -B -f "$S/sandbox/pom.xml" test -Dtest=BugHuntR1H4* -Dsurefire.failIfNoSpecifiedTests=false -DfailIfNoTests=false`
- **Single Gradle:** `python "<BH>" run --s "$S" --tid <TID> -- "$S/sandbox/gradlew" -p "$S/sandbox" test --offline --tests "*BugHuntR1H4*"`
- **Baseline (in sandbox):** `python "<BH>" run --s "$S" --tid baseline -- mvn -o -B -f "$S/sandbox/pom.xml" test` (or `gradlew -p "$S/sandbox" check --offline`).
- **Cleanup note:** `bh.py sandbox --mode clean` archives `surefire-reports/*BugHunt*.txt` and `TEST-*BugHunt*.xml` into `S/logs/` automatically; run `gradlew --stop` before cleanup if Gradle daemon ran.

## 3. Example JUnit 5 (`S/sandbox/src/test/java/com/app/billing/BugHuntR1H4DiscountTest.java`)
```java
// ID: R1-H4 | TID: r1_h4 | Target: com.app.billing.DiscountService#applyRate
// Run: mvn -o -B -f .bughunt/<SNAME>/sandbox/pom.xml test -Dtest='BugHuntR1H4*'
package com.app.billing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import java.math.BigDecimal;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.*;

class BugHuntR1H4DiscountTest {
    private final DiscountService service = new DiscountService();

    @Test void control_wholeNumberRate() {
        BigDecimal actual = service.applyRate(new BigDecimal("100.00"), new BigDecimal("0.5"));
        assertEquals(0, new BigDecimal("50.00").compareTo(actual), "got " + actual); // compareTo ignores scale
    }
    @Test @Timeout(value = 2, unit = TimeUnit.SECONDS) void halfCentRoundsUp() {
        BigDecimal actual = service.applyRate(new BigDecimal("1.25"), new BigDecimal("0.10"));
        assertEquals(0, new BigDecimal("0.13").compareTo(actual), "got " + actual);
    }
}
```

## 4. Common Java / Kotlin Pitfalls
- **`new BigDecimal(0.1)` precision loss:** Use `new BigDecimal("0.1")` or `BigDecimal.valueOf(0.1)`; use `compareTo` (not `equals`, which checks scale).
- **`==` on `String` / boxed `Integer`:** Fails outside `-128..127` cache.
- **Unchecked `Optional.get()`:** Raises `NoSuchElementException`.
- **Spring `@Transactional` self-invocation:** Bypassed proxy runs without transaction.
- **`ConcurrentModificationException`:** Mutating collection inside `for-each`.
- **Null unboxing:** Arithmetic on `null` boxed wrapper throws `NullPointerException`.
- **Thread-unsafe shared utilities:** Unsynchronized `SimpleDateFormat` or `HashMap`.
- **Kotlin platform types (`String!`):** Runtime NPE from Java interop.
- **Resource leaks:** Missing `try-with-resources` on connections, result sets, or streams.
