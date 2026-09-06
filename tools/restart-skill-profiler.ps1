param(
    [ValidateSet('v100', 'v101-experimental', 'v010-beta9.2', 'v010-beta9.1', 'v010-beta9', 'v010-beta8', 'v010-beta7', 'v010-beta6', 'v010-beta5', 'v010-beta4', 'v010-beta3', 'v010-beta2', 'v010-beta1', 'v096')][string]$Algorithm,
    [string]$Python = (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe')
)
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$runtimeDir = Join-Path $repoRoot 'tmp\runtime'
$selectionFile = Join-Path $repoRoot 'tmp\runtime-release.json'
$cliPath = Join-Path $repoRoot 'tools\map_demand_v01\cli.py'
$Python = [IO.Path]::GetFullPath($Python)
$versionByAlgorithm = @{ 'v100' = '1.0.0'; 'v101-experimental' = '1.0.1-experimental.11'; 'v010-beta9.2' = '0.10.0-beta.9.2'; 'v010-beta9.1' = '0.10.0-beta.9.1'; 'v010-beta9' = '0.10.0-beta.9'; 'v010-beta8' = '0.10.0-beta.8'; 'v010-beta7' = '0.10.0-beta.7'; 'v010-beta6' = '0.10.0-beta.6'; 'v010-beta5' = '0.10.0-beta.5'; 'v010-beta4' = '0.10.0-beta.4'; 'v010-beta3' = '0.10.0-beta.3'; 'v010-beta2' = '0.10.0-beta.2'; 'v010-beta1' = '0.10.0-beta.1'; 'v096' = '0.9.6' }
$idByAlgorithm = @{ 'v100' = 'MAP_DEMAND_V100'; 'v101-experimental' = 'MAP_DEMAND_V101_EXPERIMENTAL'; 'v010-beta9.2' = 'MAP_DEMAND_FLOW_TARGET_SIZE_V010_BETA92'; 'v010-beta9.1' = 'MAP_DEMAND_RAW_POWERED_FRONTIER_V010_BETA91'; 'v010-beta9' = 'MAP_DEMAND_RATE_PRECISION_AREA_V010_BETA9'; 'v010-beta8' = 'MAP_DEMAND_SUPPORT_FRONTIER_V010_BETA8'; 'v010-beta7' = 'MAP_DEMAND_FULL_EVIDENCE_V010_BETA7'; 'v010-beta6' = 'MAP_DEMAND_AIM_ROUTING_V010_BETA6'; 'v010-beta5' = 'MAP_DEMAND_READING_ORDER_V010_BETA5'; 'v010-beta4' = 'MAP_DEMAND_CONTROL_EXECUTION_V010_BETA4'; 'v010-beta3' = 'MAP_DEMAND_PRECISION_BALANCE_V010_BETA3'; 'v010-beta2' = 'MAP_DEMAND_TOLERANCE_RHYTHM_V010_BETA2'; 'v010-beta1' = 'MAP_DEMAND_DECOUPLED_V010_BETA1'; 'v096' = 'MAP_DEMAND_ATOMIC_V096' }

function Resolve-RunningAlgorithm($State) {
    # Only these exact prior experiments may migrate under a shared
    # algorithm key. A version string by itself never identifies the service.
    if ($State.algorithm_id -eq 'MAP_DEMAND_V101_EXPERIMENTAL' -and
        $State.map_demand_version -in @('1.0.1-experimental.3', '1.0.1-experimental.4', '1.0.1-experimental.5', '1.0.1-experimental.6', '1.0.1-experimental.7', '1.0.1-experimental.8', '1.0.1-experimental.9', '1.0.1-experimental.10')) { return 'v101-experimental' }
    $knownRunningReleases = @($versionByAlgorithm.Keys | Where-Object {
        $versionByAlgorithm[$_] -eq $State.map_demand_version -and
        $idByAlgorithm[$_] -eq $State.algorithm_id
    })
    if ($knownRunningReleases.Count -ne 1) { throw 'Unknown running algorithm/version pair; refusing automatic replacement' }
    return $knownRunningReleases[0]
}

function Test-ProfilerCommandLine($Process, $State, [string]$Selected) {
    if ($Process.Name -ne 'python.exe' -or [string]::IsNullOrWhiteSpace($Process.ExecutablePath) -or
        [IO.Path]::GetFullPath($Process.ExecutablePath) -ne $Python) { return $false }
    $pythonToken = '(?:"' + [regex]::Escape($Python) + '"|' + [regex]::Escape($Python) + ')'
    $tail = '\s+bid-review-ui\s+--no-open\s+--algorithm\s+' + [regex]::Escape($Selected) + '\s*$'
    $absoluteCliToken = '(?:"' + [regex]::Escape($cliPath) + '"|' + [regex]::Escape($cliPath) + ')'
    if ($Process.CommandLine -match ('^\s*' + $pythonToken + '\s+-u\s+' + $absoluteCliToken + $tail)) { return $true }
    # One migration exception for the .3 service previously launched and
    # verified in this project. Relative argv alone cannot prove a repo path;
    # all future launches below use the exact absolute CLI path instead.
    if ($Selected -ne 'v101-experimental' -or $State.algorithm_id -ne 'MAP_DEMAND_V101_EXPERIMENTAL' -or
        $State.map_demand_version -ne '1.0.1-experimental.3') { return $false }
    $relativeCliToken = '(?:"tools\\map_demand_v01\\cli\.py"|tools\\map_demand_v01\\cli\.py)'
    return $Process.CommandLine -match ('^\s*' + $pythonToken + '\s+-u\s+' + $relativeCliToken + $tail)
}

function Save-ProfilerSelection([string]$Selected) {
    $selectionTemp = "$selectionFile.$([Guid]::NewGuid().ToString('N')).tmp"
    [IO.File]::WriteAllText($selectionTemp, (@{ algorithm = $Selected } | ConvertTo-Json -Compress))
    Move-Item -LiteralPath $selectionTemp -Destination $selectionFile -Force
}

if (-not (Test-Path -LiteralPath $Python)) { throw "Python missing: $Python" }
if (-not (Test-Path -LiteralPath $cliPath)) { throw "Profiler CLI missing: $cliPath" }
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
$previousAlgorithm = 'v100'
if (Test-Path -LiteralPath $selectionFile) {
    $persisted = Get-Content -LiteralPath $selectionFile -Raw | ConvertFrom-Json
    if ($versionByAlgorithm.ContainsKey([string]$persisted.algorithm)) { $previousAlgorithm = [string]$persisted.algorithm }
}
# A normal restart retains the persisted selection. Explicit -Algorithm is
# used for a release switch; a fresh installation still starts at v100.
if (-not $PSBoundParameters.ContainsKey('Algorithm')) { $Algorithm = $previousAlgorithm }
$listeners = @(Get-NetTCPConnection -LocalPort 8767 -State Listen -ErrorAction SilentlyContinue)
if ($listeners.Count) {
    $listenerIds = @($listeners.OwningProcess | Sort-Object -Unique)
    if ($listenerIds.Count -ne 1) { throw 'Refusing to stop multiple port owners' }
    $serviceProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($listenerIds[0])"
    $before = Invoke-RestMethod 'http://127.0.0.1:8767/api/state' -TimeoutSec 10
    $previousAlgorithm = Resolve-RunningAlgorithm $before
    if (-not (Test-ProfilerCommandLine $serviceProcess $before $previousAlgorithm)) {
        throw 'Port 8767 is not the expected Python/CLI/repository launch; refusing replacement'
    }
    $confirmedOwners = @(Get-NetTCPConnection -LocalPort 8767 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
    $confirmedProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($serviceProcess.ProcessId)"
    if ($confirmedOwners.Count -ne 1 -or $confirmedOwners[0] -ne $serviceProcess.ProcessId -or
        $confirmedProcess.CreationDate -ne $serviceProcess.CreationDate) { throw 'Port owner changed during verification; refusing replacement' }
    Stop-Process -Id $serviceProcess.ProcessId
    Wait-Process -Id $serviceProcess.ProcessId -Timeout 15 -ErrorAction SilentlyContinue
}

function Start-Profiler([string]$Selected) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $outLog = Join-Path $runtimeDir "$Selected-$stamp.stdout.log"
    $errLog = Join-Path $runtimeDir "$Selected-$stamp.stderr.log"
    $newProcess = Start-Process -FilePath $Python -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru `
        -ArgumentList @('-u', ('"' + $cliPath + '"'), 'bid-review-ui', '--no-open', '--algorithm', $Selected) `
        -RedirectStandardOutput $outLog -RedirectStandardError $errLog
    $deadline = [DateTime]::UtcNow.AddSeconds(45)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($newProcess.HasExited) { throw "Profiler exited; inspect $errLog" }
        try {
            $state = Invoke-RestMethod 'http://127.0.0.1:8767/api/state' -TimeoutSec 2
            $readyOwners = @(Get-NetTCPConnection -LocalPort 8767 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
            if ($readyOwners.Count -eq 1 -and $readyOwners[0] -eq $newProcess.Id -and
                $state.algorithm_id -eq $idByAlgorithm[$Selected] -and
                $state.map_demand_version -eq $versionByAlgorithm[$Selected]) { return $state }
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
    # Restarting the same experiment key executes the current files, so it
    # cannot restore a prior in-memory implementation after an upgrade.
    $recoveryAlgorithm = if ($previousAlgorithm -eq 'v101-experimental') { 'v100' } else { $previousAlgorithm }
    if ($previousAlgorithm -eq 'v101-experimental') {
        Write-Warning 'Requested release failed. Starting frozen v100 recovery; the previous experimental code is not being restored.'
    } else {
        Write-Warning "Requested release failed. Starting recovery algorithm $recoveryAlgorithm."
    }
    try {
        Start-Profiler $recoveryAlgorithm | Out-Null
        Save-ProfilerSelection $recoveryAlgorithm
        Write-Warning "Recovery is healthy; persisted selection is now $recoveryAlgorithm. The requested restart still failed."
    } catch {
        throw "Requested restart failed ($($failure.Exception.Message)); recovery $recoveryAlgorithm also failed ($($_.Exception.Message))."
    }
    throw $failure
}
# Persist only after health succeeds. Existing boot scripts use this selector.
Save-ProfilerSelection $Algorithm
$after | Select-Object algorithm_id,map_demand_version,indexed_beatmaps,release | ConvertTo-Json -Depth 5
