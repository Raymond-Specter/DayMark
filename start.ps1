[CmdletBinding()]
param([switch]$NoBrowser)

$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath($PSScriptRoot)
$runtimePath = Join-Path $workspace '.runtime'
$logPath = Join-Path $workspace 'logs'
$pythonPath = Join-Path $workspace '.venv\Scripts\python.exe'
$nextPath = Join-Path $workspace 'frontend\node_modules\next\dist\bin\next'
$backendPath = Join-Path $workspace 'backend'
$frontendPath = Join-Path $workspace 'frontend'

function Test-ServiceHealth([string]$Name) {
    try {
        if ($Name -eq 'backend') {
            $result = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 3
            return ($result.status -eq 'ok' -and $result.service -eq 'personal-planning')
        }
        $result = Invoke-WebRequest -Uri 'http://127.0.0.1:3000' -UseBasicParsing -TimeoutSec 5
        return ($result.StatusCode -eq 200 -and $result.Content -match 'Personal Planning|今日|Today')
    }
    catch { return $false }
}

function Assert-PortAvailable([int]$Port) {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Port)
    try { $listener.Start() }
    catch { throw "Port $Port is already in use by another or unhealthy service. Check logs before restarting; no process has been stopped." }
    finally { $listener.Stop() }
}

function Start-PlanningService([string]$Name, [string]$Executable, [string[]]$Arguments, [string]$Directory, [int]$Port, [string]$Marker) {
    if (Test-ServiceHealth $Name) {
        Write-Host "$Name is already healthy."
        return
    }
    Assert-PortAvailable $Port
    if ($Name -eq 'backend') {
        Push-Location $workspace
        try {
            & $pythonPath -m alembic -c (Join-Path $workspace 'backend\alembic.ini') upgrade head
            if ($LASTEXITCODE -ne 0) { throw 'Database migration failed. The backend was not started.' }
        }
        finally { Pop-Location }
    }
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WorkingDirectory $Directory -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logPath "$Name.stdout.log") -RedirectStandardError (Join-Path $logPath "$Name.stderr.log")
    @{
        pid = $process.Id
        started_ticks = $process.StartTime.ToUniversalTime().Ticks.ToString()
        workspace = $workspace
        marker = $Marker
        executable = $Executable
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimePath "$Name.json") -Encoding UTF8
    $deadline = (Get-Date).AddSeconds(60)
    do {
        if (Test-ServiceHealth $Name) {
            Write-Host "$Name started on http://127.0.0.1:$Port"
            return
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "$Name did not become healthy. Read $logPath\$Name.stderr.log and $logPath\$Name.stdout.log. Run .\stop.ps1 before retrying."
}

if (-not (Test-Path -LiteralPath $pythonPath) -or -not (Test-Path -LiteralPath $nextPath) -or -not (Test-Path -LiteralPath (Join-Path $frontendPath '.next\BUILD_ID'))) {
    throw 'The application has not been built. Run .\setup.ps1 first.'
}
$nodePath = (Get-Command node -ErrorAction Stop).Source
New-Item -ItemType Directory -Path $runtimePath, $logPath -Force | Out-Null
Start-PlanningService 'backend' $pythonPath @('-m', 'uvicorn', 'app.main:app', '--app-dir', ('"' + $backendPath + '"'), '--host', '127.0.0.1', '--port', '8000') $workspace 8000 'app.main:app'
Start-PlanningService 'frontend' $nodePath @(('"' + $nextPath + '"'), 'start', '--hostname', '127.0.0.1', '--port', '3000') $frontendPath 3000 $nextPath
if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:3000' }
Write-Host 'Personal Planning System is ready. Closing this terminal does not stop it. Use .\stop.ps1 to stop these services.'
