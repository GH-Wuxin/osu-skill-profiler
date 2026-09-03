param(
    [ValidateSet('v010-beta8', 'v010-beta7', 'v010-beta6', 'v010-beta5', 'v010-beta4', 'v010-beta3', 'v010-beta2', 'v010-beta1', 'v096')][string]$Algorithm = 'v010-beta5',
    [string]$Python = (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe')
)
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$runtimeDir = Join-Path $repoRoot 'tmp\runtime'
$selectionFile = Join-Path $repoRoot 'tmp\runtime-release.json'
$versionByAlgorithm = @{ 'v010-beta8' = '0.10.0-beta.8'; 'v010-beta7' = '0.10.0-beta.7'; 'v010-beta6' = '0.10.0-beta.6'; 'v010-beta5' = '0.10.0-beta.5'; 'v010-beta4' = '0.10.0-beta.4'; 'v010-beta3' = '0.10.0-beta.3'; 'v010-beta2' = '0.10.0-beta.2'; 'v010-beta1' = '0.10.0-beta.1'; 'v096' = '0.9.6' }
if (-not (Test-Path -LiteralPath $Python)) { throw "Python missing: $Python" }
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
$previousAlgorithm = 'v010-beta5'
if (Test-Path -LiteralPath $selectionFile) {
    $persisted = Get-Content -LiteralPath $selectionFile -Raw | ConvertFrom-Json
    if ($versionByAlgorithm.ContainsKey([string]$persisted.algorithm)) { $previousAlgorithm = [string]$persisted.algorithm }
}
$listeners = @(Get-NetTCPConnection -LocalPort 8767 -State Listen -ErrorAction SilentlyContinue)
if ($listeners.Count) {
    $listenerIds = @($listeners.OwningProcess | Sort-Object -Unique)
    if ($listenerIds.Count -ne 1) { throw 'Refusing to stop multiple port owners' }
    $serviceProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($listenerIds[0])"
    if ($serviceProcess.Name -ne 'python.exe' -or $serviceProcess.CommandLine -notmatch 'tools[\\/]map_demand_v01[\\/]cli\.py.+bid-review-ui') {
        throw 'Port 8767 is not the expected Skill Profiler process'
    }
    $before = Invoke-RestMethod 'http://127.0.0.1:8767/api/state' -TimeoutSec 10
    $runningRelease = @($versionByAlgorithm.Keys | Where-Object { $versionByAlgorithm[$_] -eq $before.map_demand_version })
    if ($runningRelease.Count -ne 1) { throw 'Unknown running release; refusing automatic replacement' }
    $previousAlgorithm = $runningRelease[0]
    Stop-Process -Id $serviceProcess.ProcessId
    Wait-Process -Id $serviceProcess.ProcessId -Timeout 15 -ErrorAction SilentlyContinue
}

function Start-Profiler([string]$Selected) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $outLog = Join-Path $runtimeDir "$Selected-$stamp.stdout.log"
    $errLog = Join-Path $runtimeDir "$Selected-$stamp.stderr.log"
    $newProcess = Start-Process -FilePath $Python -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru `
        -ArgumentList @('-u', 'tools\map_demand_v01\cli.py', 'bid-review-ui', '--no-open', '--algorithm', $Selected) `
        -RedirectStandardOutput $outLog -RedirectStandardError $errLog
    $deadline = [DateTime]::UtcNow.AddSeconds(45)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($newProcess.HasExited) { throw "Profiler exited; inspect $errLog" }
        try {
            $state = Invoke-RestMethod 'http://127.0.0.1:8767/api/state' -TimeoutSec 2
            if ($state.map_demand_version -eq $versionByAlgorithm[$Selected]) { return $state }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    Stop-Process -Id $newProcess.Id -ErrorAction SilentlyContinue
    throw "Profiler readiness timeout; inspect $errLog"
}

try {
    $after = Start-Profiler $Algorithm
} catch {
    $failure = $_
    Write-Warning 'New release did not start; restoring the previous algorithm'
    Start-Profiler $previousAlgorithm | Out-Null
    throw $failure
}
# Persist only after health succeeds. Existing boot scripts use this selector.
$selectionTemp = "$selectionFile.$([Guid]::NewGuid().ToString('N')).tmp"
[IO.File]::WriteAllText($selectionTemp, (@{ algorithm = $Algorithm } | ConvertTo-Json -Compress))
Move-Item -LiteralPath $selectionTemp -Destination $selectionFile -Force
$after | Select-Object algorithm_id,map_demand_version,indexed_beatmaps,release | ConvertTo-Json -Depth 5
