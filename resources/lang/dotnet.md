# C# (.NET) Adapter

## 1. Core Principles
- Always use `S/sandbox/` (`python "<BH>" sandbox --s "$S" --mode create`; auto-excludes `bin`, `obj`, `.vs`, `TestResults`).
- Add tests into an existing test project in the sandbox (`S/sandbox/tests/App.Tests/BugHunt/BugHuntR1H5DiscountTests.cs`), matching xUnit/NUnit/MSTest. SDK-style `.csproj` picks up new `.cs` files automatically.
- If zero test projects exist, creating one requires NuGet packages; ask user or use E3 static trace.
- **`internal` members:** Add `InternalsVisibleTo` inside the **sandbox copy** (`AssemblyInfo.cs` or `.csproj`).
- **Restore:** If `obj/` exists in `ROOT`, global NuGet cache has packages -> run `dotnet restore "$S/sandbox/<App>.sln"` in sandbox. If never restored, ask user first. `bh.py` auto-sets `DOTNET_CLI_TELEMETRY_OPTOUT=1` and `DOTNET_NOLOGO=1`.

## 2. Executing Hypothesis Tests & Baseline (`bh.py`)
- **Restore once after sandbox creation:** `python "<BH>" run --s "$S" --tid restore_sb -- dotnet restore "$S/sandbox/<App>.sln"`
- **Batch round:** `python "<BH>" round --s "$S" --round N` (auto-runs `dotnet test <csproj> --no-restore --filter FullyQualifiedName~BugHuntR{N}H{M} --logger console;verbosity=normal`).
- **Baseline (in sandbox):**
  - `python "<BH>" run --s "$S" --tid baseline_build -- dotnet build "$S/sandbox/<App>.sln" --no-restore`
  - `python "<BH>" run --s "$S" --tid baseline -- dotnet test "$S/sandbox/<App>.sln" --no-restore`

## 3. Example xUnit (`S/sandbox/tests/App.Tests/BugHunt/BugHuntR1H5DiscountTests.cs`)
```csharp
// ID: R1-H5 | TID: r1_h5 | Target: App.Billing.DiscountService.ApplyRate
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
    [InlineData(1.25, 0.13)]  // Math.Round defaults to MidpointRounding.ToEven (0.12)
    [InlineData(2.25, 0.23)]
    public void HalfCentRoundsAwayFromZero(double total, double expected) =>
        Assert.Equal((decimal)expected, _service.ApplyRate((decimal)total, 0.10m));
}
```

## 4. Common C# Pitfalls
- **`Math.Round` default:** Banker's rounding (`MidpointRounding.ToEven`); using `double` for money instead of `decimal`.
- **`async void` outside event handlers:** Exceptions escape unhandled and crash process.
- **`.Result` / `.Wait()` on Task:** Deadlocks under synchronization contexts (ASP.NET classic/UI).
- **Multiple `IEnumerable` enumeration:** Re-runs LINQ deferred queries or diverges on changing state.
- **Unmanaged `IDisposable` leaks:** Missing `using` on streams/`DbContext` (**except `HttpClient`**: reuse via `IHttpClientFactory`, never dispose per request).
- **`DateTime` Kind mismatch:** Mixing `DateTime.Now`, `UtcNow`, and `Unspecified`.
- **EF Core:** N+1 lazy loading, missed `SaveChangesAsync`, detached entity tracking bugs.
- **Non-thread-safe collections:** Shared `Dictionary`/`List` across threads instead of `ConcurrentDictionary`.
- **Struct copy mutation:** Mutating struct returned by property getter modifies an ephemeral copy.
