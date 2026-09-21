[CmdletBinding()]
param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
try { & (Join-Path $PSScriptRoot 'setup_ollama.ps1') -Start }
catch { Write-Warning "AI is unavailable: $($_.Exception.Message). Planning services will still start." }
& (Join-Path $workspace 'start.ps1') -NoBrowser:$NoBrowser
