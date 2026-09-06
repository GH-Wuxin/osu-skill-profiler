"""Run restart selection in a temporary repo with all service operations mocked.

These tests execute the real PowerShell selection/persistence path. They do
not start Python services, inspect real port owners, stop processes, or write
the user's runtime selector. Historical release tests cover registration;
the Python release selector is also covered by Experimental101IntegrationTests.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
from map_demand_v01 import release

POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")

HARNESS = r'''
param([string]$CasePath)
$ErrorActionPreference = 'Stop'
$taskFixture = Get-Content -LiteralPath $CasePath -Raw | ConvertFrom-Json
$global:TaskReleaseMap = $taskFixture.releases
$global:TaskLaunchedAlgorithm = $null
$global:TaskLaunchCount = 0

# Explicitly mask every process/network side effect reachable from restart.
function Get-NetTCPConnection {
    param($LocalPort, $State, $ErrorAction)
    if ($global:TaskLaunchCount -gt 0) { [pscustomobject]@{ OwningProcess = 7654321 } }
}
function Get-CimInstance { throw 'Process inspection is forbidden in this selection test' }
function Stop-Process { throw 'Stopping a process is forbidden in this selection test' }
function Wait-Process { throw 'Waiting for a process is forbidden in this selection test' }
function Start-Sleep { throw 'Readiness should resolve through the deterministic mock' }
function Start-Process {
    param($FilePath, $WorkingDirectory, $WindowStyle, [switch]$PassThru,
          $ArgumentList, $RedirectStandardOutput, $RedirectStandardError)
    $global:TaskLaunchCount += 1
    $global:TaskLaunchedAlgorithm = $ArgumentList[-1]
    if ($WindowStyle -ne 'Hidden' -or $ArgumentList[2] -ne 'bid-review-ui') {
        throw 'Unexpected launch contract'
    }
    [pscustomobject]@{ Id = 7654321; HasExited = $false }
}
function Invoke-RestMethod {
    param($Uri, $TimeoutSec)
    $taskRelease = $global:TaskReleaseMap.PSObject.Properties[$global:TaskLaunchedAlgorithm].Value
    if ($null -eq $taskRelease) { throw 'Unexpected selected algorithm' }
    [pscustomobject]@{
        algorithm_id = $taskRelease.algorithm_id
        map_demand_version = $taskRelease.version
        indexed_beatmaps = 0
        release = $null
    }
}

$taskArguments = @{ Python = $taskFixture.python }
if ($null -ne $taskFixture.explicit_algorithm) {
    $taskArguments.Algorithm = $taskFixture.explicit_algorithm
}
$taskOutput = & $taskFixture.restart_path @taskArguments
$taskState = ($taskOutput -join "`n") | ConvertFrom-Json
$taskSaved = Get-Content -LiteralPath $taskFixture.selection_path -Raw | ConvertFrom-Json
[pscustomobject]@{
    launched = $global:TaskLaunchedAlgorithm
    launch_count = $global:TaskLaunchCount
    saved = $taskSaved.algorithm
    algorithm_id = $taskState.algorithm_id
    version = $taskState.map_demand_version
} | ConvertTo-Json -Compress
'''


@unittest.skipUnless(POWERSHELL, "PowerShell is required for the Windows restart entrypoint")
class RestartSelectionTests(unittest.TestCase):
    def assert_selection(self, *, persisted, explicit, expected):
        actual_selector = ROOT / "tmp" / "runtime-release.json"
        actual_before = actual_selector.read_bytes() if actual_selector.is_file() else None
        with tempfile.TemporaryDirectory(prefix="profiler-restart-selection-") as temporary:
            directory = Path(temporary)
            # Spaces exercise the real quoted absolute CLI launch argument.
            repo = directory / "repo with spaces"
            tools = repo / "tools"
            (tools / "map_demand_v01").mkdir(parents=True)
            (tools / "map_demand_v01" / "cli.py").write_text("# never executed\n", encoding="utf-8")
            restart = tools / "restart-skill-profiler.ps1"
            shutil.copyfile(ROOT / "tools" / restart.name, restart)
            selector = repo / "tmp" / "runtime-release.json"
            if persisted is not None:
                selector.parent.mkdir()
                selector.write_text(json.dumps({"algorithm": persisted}), encoding="utf-8")
            case = directory / "case.json"
            case.write_text(json.dumps({
                "restart_path": str(restart), "selection_path": str(selector),
                "python": sys.executable, "explicit_algorithm": explicit,
                "releases": {key: {"algorithm_id": model.ALGORITHM_ID, "version": model.MAP_DEMAND_VERSION}
                             for key, model in release.RUNTIME_ALGORITHMS.items()},
            }), encoding="utf-8")
            harness = directory / "selection-harness.ps1"
            harness.write_text(HARNESS, encoding="utf-8-sig")
            completed = subprocess.run(
                [POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", str(harness), "-CasePath", str(case)],
                text=True, capture_output=True, timeout=20, cwd=directory,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual(result["launched"], expected)
            self.assertEqual(result["saved"], expected)
            self.assertEqual(result["launch_count"], 1)
            self.assertEqual(result["algorithm_id"], release.RUNTIME_ALGORITHMS[expected].ALGORITHM_ID)
            self.assertEqual(result["version"], release.RUNTIME_ALGORITHMS[expected].MAP_DEMAND_VERSION)
        actual_after = actual_selector.read_bytes() if actual_selector.is_file() else None
        self.assertEqual(actual_after, actual_before, "The real runtime selector must remain untouched")

    def test_fresh_restart_falls_back_to_v100(self):
        self.assert_selection(persisted=None, explicit=None, expected="v100")

    def test_normal_restart_retains_persisted_experiment_or_historical_release(self):
        for selected in ("v101-experimental", "v010-beta9.2"):
            with self.subTest(selected=selected):
                self.assert_selection(persisted=selected, explicit=None, expected=selected)

    def test_explicit_stable_selection_overrides_persisted_experiment(self):
        self.assert_selection(persisted="v101-experimental", explicit="v100", expected="v100")

    def test_explicit_experiment_overrides_persisted_historical_release(self):
        self.assert_selection(persisted="v010-beta9.2", explicit="v101-experimental", expected="v101-experimental")

    def test_unknown_persisted_key_uses_restart_fallback(self):
        self.assert_selection(persisted="unknown-release", explicit=None, expected="v100")


if __name__ == "__main__":
    unittest.main()
