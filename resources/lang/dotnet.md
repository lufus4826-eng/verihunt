# C# (.NET) Adapter

## 1. Core Principles
- Always use `S/sandbox/` because .NET builds write `bin/` and `obj/` into source directories. Additional exclusions during sandbox cloning: `bin`, `obj`, `.vs`, `TestResults`.
- **Add test classes into an existing test project in the sandbox copy** (e.g., `S/sandbox/tests/App.Tests/BugHunt/BugHuntR1H5DiscountTests.cs`). SDK-style `.csproj` projects automatically include new `.cs` files. Align with the test framework already used (xUnit, NUnit, MSTest).
- If the repository has zero test projects, creating one requires downloading test framework NuGet packages; if not cached locally, ask the user or rely on E3 static traces.
- `internal` members: If `InternalsVisibleTo` is missing for the test project, add it to the **sandbox copy** of `AssemblyInfo.cs` or `.csproj`.
- Restoring packages: If the host project already contains `obj/`, packages exist in the global NuGet cache; run `dotnet restore` inside the sandbox. If never restored before, ask the user first.
- Set telemetry opt-out: `DOTNET_CLI_TELEMETRY_OPTOUT=1` and `DOTNET_NOLOGO=1`.

## 2. Executing Hypothesis Tests
```bash
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
dotnet restore "$S/sandbox/<App>.sln"
dotnet test "$S/sandbox/tests/App.Tests/App.Tests.csproj" --no-restore --filter "FullyQualifiedName~BugHuntR1H5" \
  --logger "console;verbosity=normal" > "$S/logs/$TID.log" 2>&1; echo "exit=$?" >> "$S/logs/$TID.log"
```
```powershell
$env:DOTNET_CLI_TELEMETRY_OPTOUT = "1"; $env:DOTNET_NOLOGO = "1"
dotnet restore "$S\sandbox\<App>.sln"
cmd /c "dotnet test `"$S\sandbox\tests\App.Tests\App.Tests.csproj`" --no-restore --filter FullyQualifiedName~BugHuntR1H5 --logger `"console;verbosity=normal`" > `"$S\logs\$TID.log`" 2>&1"; "exit=$LASTEXITCODE" | Add-Content "$S\logs\$TID.log"
```

## 3. Baseline Commands (Executed Inside Sandbox)
```bash
dotnet build "$S/sandbox/<App>.sln" --no-restore
dotnet test "$S/sandbox/<App>.sln" --no-restore
```

## 4. Example xUnit (`S/sandbox/tests/App.Tests/BugHunt/BugHuntR1H5DiscountTests.cs`)
```csharp
// ID: R1-H5 | TID: r1_h5
// Target: App.Billing.DiscountService.ApplyRate
// Run: dotnet test .bughunt/<SNAME>/sandbox/tests/App.Tests/App.Tests.csproj --filter FullyQualifiedName~BugHuntR1H5
using App.Billing;
using Xunit;

public class BugHuntR1H5DiscountTests
{
    private readonly DiscountService _service = new();

    [Fact]
    public void Control_NoRoundingNeeded() =>
        Assert.Equal(10.00m, _service.ApplyRate(100.00m, 0.10m));

    [Theory]
    [InlineData(1.25, 0.13)]   // Math.Round defaults to MidpointRounding.ToEven (yielding 0.12)
    [InlineData(2.25, 0.23)]
    public void HalfCentRoundsAwayFromZero(double total, double expected) =>
        Assert.Equal((decimal)expected, _service.ApplyRate((decimal)total, 0.10m));
}
```

## 5. Common C# Pitfalls & Bug Patterns
- **`Math.Round` default behavior:** Defaults to banker's rounding (`MidpointRounding.ToEven`); using `double` for currency causes precision loss compared to `decimal`.
- **`async void` outside event handlers:** Exceptions escape unhandled, crashing the host process.
- **`.Result` or `.Wait()` on Task:** Induces deadlocks when invoked from contexts with synchronization contexts (e.g., UI or ASP.NET classic).
- **Multiple enumeration of `IEnumerable`:** LINQ deferred execution re-executes database queries or produces divergent results if underlying state changes.
- **Unmanaged resource leaks (`IDisposable`):** Failing to wrap streams or `DbContext` in `using` declarations. (Conversely, **do NOT instantiate and dispose `HttpClient` per request**; reuse via `IHttpClientFactory` to prevent socket exhaustion).
- **DateTime kind confusion:** Mixing `DateTime.Now` with `DateTime.UtcNow`, or leaving `DateTimeKind.Unspecified`.
- **Entity Framework Core pitfalls:** N+1 queries from lazy loading, forgotten `SaveChangesAsync`, or detached entity tracking bugs.
- **Non-thread-safe collections:** Accessing standard `Dictionary` or `List` across multiple threads instead of `ConcurrentDictionary`.
- **Struct mutation on copies:** Invoking mutating methods on struct properties returned from property getters mutates an ephemeral copy.
