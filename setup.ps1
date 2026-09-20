[CmdletBinding()]
param([switch]$DirectNetwork)

$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath($PSScriptRoot)
$pythonPath = Join-Path $workspace '.venv\Scripts\python.exe'
$frontendPath = Join-Path $workspace 'frontend'
$runtimePath = Join-Path $workspace '.runtime'
$certificatePath = Join-Path $runtimePath 'system-ca.pem'
$requirementsPath = Join-Path $workspace 'backend\requirements-lock.txt'
if (-not (Test-Path -LiteralPath $requirementsPath)) { $requirementsPath = Join-Path $workspace 'backend\requirements.txt' }

if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Node.js is required. Install Node.js 22 or newer, then reopen PowerShell.' }
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'npm.cmd was not found in PATH.' }
if (-not (Test-Path -LiteralPath $pythonPath)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { throw 'Python 3.10 or newer is required.' }
    & $pythonCommand.Source -m venv (Join-Path $workspace '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Creating the Python virtual environment failed.' }
}

$previousNoProxy = $env:NO_PROXY
if ($DirectNetwork) { $env:NO_PROXY = '*' }
Push-Location $workspace
try {
    New-Item -ItemType Directory -Path $runtimePath -Force | Out-Null
    # Keep TLS verification enabled while honoring this computer's Windows CAs.
    $certificateCode = @'
import pathlib
import ssl
import sys
from pip._vendor import certifi

bundle = pathlib.Path(certifi.where()).read_text(encoding="ascii")
seen = set()
for store in ("ROOT", "CA"):
    for certificate, encoding, trust in ssl.enum_certificates(store):
        if encoding == "x509_asn" and certificate not in seen and (trust is True or ssl.Purpose.SERVER_AUTH.oid in trust):
            seen.add(certificate)
            bundle += "\n" + ssl.DER_cert_to_PEM_cert(certificate)
pathlib.Path(sys.argv[1]).write_text(bundle, encoding="ascii")
'@
    $certificateCode | & $pythonPath - $certificatePath
    if ($LASTEXITCODE -ne 0) { throw 'Could not prepare the Windows certificate trust bundle.' }

    Write-Host 'Installing backend dependencies...'
    & $pythonPath -m pip install --index-url 'https://pypi.org/simple' --cert $certificatePath -r $requirementsPath
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }

    Write-Host 'Applying database migrations...'
    & $pythonPath -m alembic -c (Join-Path $workspace 'backend\alembic.ini') upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed. See the error above.' }

    Push-Location $frontendPath
    try {
        Write-Host 'Installing frontend dependencies...'
        if (Test-Path -LiteralPath 'package-lock.json') { & npm.cmd ci } else { & npm.cmd install }
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
        Write-Host 'Building the production frontend...'
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend production build failed.' }
    }
    finally { Pop-Location }
}
finally {
    Pop-Location
    if ($DirectNetwork) {
        if ($null -eq $previousNoProxy) { Remove-Item Env:NO_PROXY -ErrorAction SilentlyContinue } else { $env:NO_PROXY = $previousNoProxy }
    }
}

Write-Host 'Setup complete. Run .\start.ps1 to open Personal Planning System.'
