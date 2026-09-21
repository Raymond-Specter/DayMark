[CmdletBinding()]
param([switch]$Install, [switch]$Start, [switch]$Pull, [switch]$DirectNetwork, [string]$Model = 'qwen3:8b')

$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$binaryDir = Join-Path $workspace 'runtime\ollama'
$exe = Join-Path $binaryDir 'ollama.exe'
$stateDir = Join-Path $workspace '.runtime'
$modelDir = Join-Path $workspace 'models\ollama'
$logDir = Join-Path $workspace 'logs'
$version = 'v0.34.2'
$expectedHash = '8f3fd071a2a2f9497b562f43502c77c2b701a99d1ee5dfda28da8c786373063b'
$baseUrl = $env:OLLAMA_BASE_URL
$envFile = Join-Path $workspace '.env'
if (-not $baseUrl -and (Test-Path -LiteralPath $envFile)) {
    foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
        if ($line -match '^\s*OLLAMA_BASE_URL\s*=(.*)$') {
            $baseUrl = $Matches[1].Trim().Trim('"').Trim("'")
            break
        }
    }
}
if (-not $baseUrl) { $baseUrl = 'http://127.0.0.1:11434' }
$endpoint = [Uri]$baseUrl
if ($endpoint.Scheme -ne 'http' -or $endpoint.Host -notin @('localhost', '127.0.0.1', '[::1]', '::1') -or $endpoint.UserInfo -or $endpoint.AbsolutePath -ne '/' -or $endpoint.Query -or $endpoint.Fragment) {
    throw 'OLLAMA_BASE_URL must be a local HTTP origin, for example http://127.0.0.1:11434.'
}
$baseUrl = $baseUrl.TrimEnd('/')

function Read-OllamaStatus {
    try { return Invoke-RestMethod "$baseUrl/api/tags" -TimeoutSec 3 }
    catch { return $null }
}

if (-not (Test-Path -LiteralPath $exe)) {
    $systemCommand = Get-Command ollama -ErrorAction SilentlyContinue
    if ($systemCommand) { Write-Host "A system Ollama exists: $($systemCommand.Source). DayMark uses its own portable install." }
    if (-not $Install) {
        Write-Host 'Project Ollama is not installed. Explicit install command:'
        Write-Host 'powershell -ExecutionPolicy Bypass -File .\scripts\setup_ollama.ps1 -Install -Start -Pull'
        return
    }
    New-Item -ItemType Directory -Path $stateDir, $binaryDir -Force | Out-Null
    $zip = Join-Path $stateDir "ollama-$version.zip"
    Write-Host "Downloading official portable Ollama $version (~1.5 GB) into $workspace. No global installation."
    if (-not (Test-Path $zip) -or (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) {
        $curlPath = (Get-Command curl.exe).Source
        $gitCurl = Join-Path $env:ProgramFiles 'Git\mingw64\bin\curl.exe'
        if (Test-Path $gitCurl) { $curlPath = $gitCurl }
        $curlOptions = @('--fail', '--location', '--retry', '3', '--continue-at', '-', '--output', $zip)
        if ($DirectNetwork) { $curlOptions += @('--noproxy', '*') }
        & $curlPath @curlOptions "https://github.com/ollama/ollama/releases/download/$version/ollama-windows-amd64.zip"
        if ($LASTEXITCODE -ne 0) { throw 'Ollama download failed. Re-run the same command to resume.' }
    }
    if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) { throw 'Ollama archive checksum mismatch. Do not extract this download.' }
    Expand-Archive -LiteralPath $zip -DestinationPath $binaryDir -Force
    if (-not (Test-Path -LiteralPath $exe)) { throw 'Archive extracted but ollama.exe is missing.' }
}

$status = Read-OllamaStatus
if ($status -and ($Start -or $Pull)) {
    $owner = Get-CimInstance Win32_Process -Filter "name='ollama.exe'" | Where-Object { $_.ExecutablePath -eq $exe -and $_.CommandLine -match '\bserve\b' }
    if (-not $owner) { throw "$baseUrl belongs to another Ollama instance. Stop it manually first; no model will be downloaded outside this project." }
}

$overrides = @{
    OLLAMA_HOST=$endpoint.Authority; OLLAMA_MODELS=$modelDir
    OLLAMA_NUM_PARALLEL='1'; OLLAMA_MAX_LOADED_MODELS='1'; OLLAMA_CONTEXT_LENGTH='8192'
    OLLAMA_FLASH_ATTENTION='1'; OLLAMA_KV_CACHE_TYPE='q8_0'; OLLAMA_NO_CLOUD='1'
    USERPROFILE=(Join-Path $stateDir 'ollama-home'); TEMP=(Join-Path $stateDir 'ollama-temp'); TMP=(Join-Path $stateDir 'ollama-temp')
    NO_PROXY='localhost,127.0.0.1'; HTTP_PROXY=''
}
$saved = @{}
if ($DirectNetwork) { $overrides.HTTPS_PROXY = ''; $overrides.NO_PROXY = '*' }
foreach ($name in $overrides.Keys) { $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    foreach ($name in $overrides.Keys) { [Environment]::SetEnvironmentVariable($name, $overrides[$name], 'Process') }
    New-Item -ItemType Directory -Path $stateDir,$modelDir,$logDir,$overrides.USERPROFILE,$overrides.TEMP -Force | Out-Null
    & $exe --version
    if (-not $status -and $Start) {
        Write-Host "Starting project Ollama. Models: $modelDir"
        $process = Start-Process -FilePath $exe -ArgumentList 'serve' -WorkingDirectory $workspace -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir 'ollama.stdout.log') -RedirectStandardError (Join-Path $logDir 'ollama.stderr.log')
        @{pid=$process.Id; started_ticks=$process.StartTime.ToUniversalTime().Ticks.ToString(); workspace=$workspace; marker=$exe; executable=$exe} | ConvertTo-Json | Set-Content (Join-Path $stateDir 'ollama.json') -Encoding UTF8
        for ($attempt=0; $attempt -lt 40; $attempt++) {
            if ($process.HasExited) { throw 'Ollama exited. Check logs/ollama.stderr.log; if Windows reserves this port, set OLLAMA_BASE_URL in .env to an available local port.' }
            $status = Read-OllamaStatus
            if ($status) { break }
            Start-Sleep -Milliseconds 500
        }
        if (-not $status) { throw 'Ollama did not start. Check logs/ollama.stderr.log.' }
    }
    if (-not $status) { Write-Host 'Ollama Offline. Start with: .\scripts\setup_ollama.ps1 -Start'; return }
    if (-not (@($status.models.name) -contains $Model)) {
        if ($Pull) {
            Write-Host "Downloading $Model into $modelDir (several GB)."
            & $exe pull $Model
            if ($LASTEXITCODE -ne 0) { throw 'Model download failed. Re-run with -Start -Pull to resume.' }
        } else { Write-Host "Model $Model is missing. Run .\scripts\setup_ollama.ps1 -Start -Pull" }
    }
    & $exe list
    & $exe ps
}
finally {
    foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
}
