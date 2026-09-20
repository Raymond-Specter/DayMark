[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath($PSScriptRoot)
$runtimePath = Join-Path $workspace '.runtime'

foreach ($serviceName in @('frontend', 'backend')) {
    $statePath = Join-Path $runtimePath "$serviceName.json"
    if (-not (Test-Path -LiteralPath $statePath)) {
        Write-Host "No managed $serviceName process is recorded."
        continue
    }
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    if ([IO.Path]::GetFullPath($state.workspace) -ne $workspace) { throw "Refusing to stop ${serviceName}: its recorded workspace differs." }
    $process = Get-Process -Id $state.pid -ErrorAction SilentlyContinue
    if (-not $process) {
        Remove-Item -LiteralPath $statePath
        Write-Host "$serviceName has already stopped."
        continue
    }
    if ($process.StartTime.ToUniversalTime().Ticks.ToString() -ne [string]$state.started_ticks) {
        throw "Refusing to stop ${serviceName}: the process ID has been reused."
    }
    $allProcesses = @(Get-CimInstance Win32_Process)
    $rootProcess = $allProcesses | Where-Object ProcessId -eq $state.pid
    if (-not $rootProcess -or -not $rootProcess.CommandLine -or -not $rootProcess.CommandLine.Contains($workspace) -or -not $rootProcess.CommandLine.Contains($state.marker)) {
        throw "Refusing to stop ${serviceName}: the command line does not identify this application."
    }

    # The Windows virtual-environment launcher may have a child Python process.
    $managedIds = [Collections.Generic.List[int]]::new()
    $managedIds.Add([int]$state.pid)
    for ($index = 0; $index -lt $managedIds.Count; $index++) {
        foreach ($child in @($allProcesses | Where-Object ParentProcessId -eq $managedIds[$index])) {
            if ($child.CommandLine -and $child.CommandLine.Contains($workspace) -and $child.CommandLine.Contains($state.marker)) {
                $managedIds.Add([int]$child.ProcessId)
            }
        }
    }
    for ($index = $managedIds.Count - 1; $index -ge 0; $index--) {
        $processToStop = Get-Process -Id $managedIds[$index] -ErrorAction SilentlyContinue
        $recordedProcess = $allProcesses | Where-Object ProcessId -eq $managedIds[$index]
        if ($processToStop -and $recordedProcess -and [Math]::Abs(($processToStop.StartTime - $recordedProcess.CreationDate).TotalSeconds) -lt 1) {
            Stop-Process -Id $processToStop.Id
            $processToStop.WaitForExit(10000) | Out-Null
        }
    }
    Remove-Item -LiteralPath $statePath
    Write-Host "$serviceName stopped. Data is retained."
}
