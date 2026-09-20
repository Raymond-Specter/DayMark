[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath($PSScriptRoot)
$pythonPath = Join-Path $workspace '.venv\Scripts\python.exe'
$sourcePath = Join-Path $workspace 'data\planner.db'
$backupPath = Join-Path $workspace 'data\backups'
if ($env:DATABASE_URL) { throw 'DATABASE_URL is set. This script backs up the default local database only; unset it or back up the configured database explicitly.' }
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run .\setup.ps1 first.' }
if (-not (Test-Path -LiteralPath $sourcePath)) { throw 'The database does not exist yet. Run .\setup.ps1 first.' }
New-Item -ItemType Directory -Path $backupPath -Force | Out-Null
$destinationPath = Join-Path $backupPath ('planner-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.db')

# SQLite's online backup API includes committed WAL data without stopping the app.
$backupCode = @'
import pathlib
import sqlite3
import sys

source = pathlib.Path(sys.argv[1]).resolve()
destination = pathlib.Path(sys.argv[2]).resolve()
if destination.exists():
    raise SystemExit("Backup destination already exists; refusing to overwrite it.")
with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src:
    with sqlite3.connect(destination) as dst:
        src.backup(dst)
        result = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise SystemExit("Backup integrity check failed: " + result)
print(str(destination))
'@
$backupCode | & $pythonPath - $sourcePath $destinationPath
if ($LASTEXITCODE -ne 0) { throw 'Database backup failed. See the error above.' }
Write-Host 'Online backup complete and verified.'
