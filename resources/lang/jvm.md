# Java / Kotlin (JVM) Adapter

## 1. Core Principles
- Always utilize `S/sandbox/` for both test execution and baseline checks; JVM build tools inherently generate `target/`, `build/`, and `.gradle/` into the source tree.
- Additional exclusions during sandbox copy: `target`, `build`, `.gradle`, `out`, `.idea`. (If actual source folders are named `build` or `out`, exclude them only at the module root level rather than globally).
- File and class naming: `src/test/java/<package>/BugHuntR1H4<ShortName>Test.java` (Kotlin: `src/test/kotlin/.../BugHuntR1H4<ShortName>Test.kt`). Place in the identical package to test package-private members. End names with `Test` to match default Surefire/Gradle filters.
- Match project JUnit version (JUnit 5: `org.junit.jupiter.api.*` / JUnit 4: `org.junit.Test`).
- **Enforce Offline Execution:** Maven `-o` (use standard `~/.m2`; never set `maven.repo.local` to an empty directory, as it forces re-downloading all dependencies). Gradle `--offline`. Use wrapper scripts (`mvnw` / `gradlew`) when present; if the wrapper requires downloading a new distribution, ask user.
- **PowerShell Syntax:** Arguments like `-Dkey=value` containing dots can be parsed incorrectly in PowerShell 5.1; execute via `cmd /c` (per `00-common.md`) or wrap in quotes.
- **Spring Boot:** Avoid heavy `@SpringBootTest` that boots external databases. Test services in isolation, use test slices, or mock data sources. Inspect `application-test.*` before execution.

## 2. Executing Hypothesis Tests
**Maven**
```bash
mvn -o -B -f "$S/sandbox/pom.xml" test -Dtest='BugHuntR1H4*' -Dsurefire.failIfNoSpecifiedTests=false -DfailIfNoTests=false \
  > "$S/logs/$TID.log" 2>&1; echo "exit=$?" >> "$S/logs/$TID.log"
# Multi-module repositories: append -pl <module_name> -am
```
```powershell
cmd /c "mvn -o -B -f `"$S\sandbox\pom.xml`" test -Dtest=BugHuntR1H4* -Dsurefire.failIfNoSpecifiedTests=false -DfailIfNoTests=false > `"$S\logs\$TID.log`" 2>&1"; "exit=$LASTEXITCODE" | Add-Content "$S\logs\$TID.log"
```
**Gradle**
```bash
"$S/sandbox/gradlew" -p "$S/sandbox" test --offline --tests '*BugHuntR1H4*' > "$S/logs/$TID.log" 2>&1; echo "exit=$?" >> "$S/logs/$TID.log"
```
```powershell
cmd /c "`"$S\sandbox\gradlew.bat`" -p `"$S\sandbox`" test --offline --tests *BugHuntR1H4* > `"$S\logs\$TID.log`" 2>&1"; "exit=$LASTEXITCODE" | Add-Content "$S\logs\$TID.log"
```
- Detailed assertion failure traces are frequently redirected to XML/text report files. Copy relevant reports to `S/logs/` before deleting the sandbox: Maven `target/surefire-reports/*BugHunt*.txt`, Gradle `build/test-results/test/TEST-*BugHunt*.xml`.
- During cleanup, issue `gradlew --stop` to terminate lingering background Gradle daemons.

## 3. Baseline Commands (Executed Inside Sandbox)
```bash
mvn -o -B -f "$S/sandbox/pom.xml" test
"$S/sandbox/gradlew" -p "$S/sandbox" check --offline
```

## 4. Example JUnit 5 (`S/sandbox/src/test/java/com/app/billing/BugHuntR1H4DiscountTest.java`)
```java
// ID: R1-H4 | TID: r1_h4
// Target: com.app.billing.DiscountService#applyRate
// Run: mvn -o -B -f .bughunt/<SNAME>/sandbox/pom.xml test -Dtest='BugHuntR1H4*'
package com.app.billing;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

class BugHuntR1H4DiscountTest {
    private final DiscountService service = new DiscountService();

    @Test
    void control_wholeNumberRate() {
        BigDecimal actual = service.applyRate(new BigDecimal("100.00"), new BigDecimal("0.5"));
        // Use compareTo because BigDecimal.equals checks scale (10.00 does not equal 10.000)
        assertEquals(0, new BigDecimal("50.00").compareTo(actual), "got " + actual);
    }

    @Test
    @Timeout(value = 2, unit = TimeUnit.SECONDS)
    void halfCentRoundsUp() {
        BigDecimal actual = service.applyRate(new BigDecimal("1.25"), new BigDecimal("0.10"));
        assertEquals(0, new BigDecimal("0.13").compareTo(actual), "got " + actual);
    }
}
```

## 5. Common Java / Kotlin Pitfalls & Bug Patterns
- **`new BigDecimal(0.1)` precision bug:** Converts IEEE double representation to imprecise decimal (`0.10000000000000000555...`). Use `new BigDecimal("0.1")` or `BigDecimal.valueOf(0.1)`. Remember `BigDecimal.equals` checks scale.
- **Identity `==` with `String` or boxed `Integer`:** Boxed integers outside cached range (-128 to 127) fail reference equality.
- **Unchecked `Optional.get()`:** Calling `.get()` without prior `.isPresent()` check raises `NoSuchElementException`.
- **Spring `@Transactional` self-invocation:** Calling a transactional method from within the same class bypasses the CGLIB proxy, running without a database transaction.
- **`ConcurrentModificationException`:** Modifying collections during an active for-each loop.
- **Null unboxing:** Attempting arithmetic on a `null` boxed wrapper throws runtime `NullPointerException`.
- **Thread-unsafe utilities:** Sharing non-synchronized `SimpleDateFormat` or standard `HashMap` across multiple concurrent threads.
- **Kotlin platform types:** Values received from Java (`String!`) lack null-safety enforcement, triggering unexpected NPEs at runtime.
- **Resource leaks:** Omitting try-with-resources blocks on database connections, result sets, or streams.
