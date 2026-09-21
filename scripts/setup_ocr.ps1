[CmdletBinding()]
param([switch]$DirectNetwork)

$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$modelDir = Join-Path $workspace 'models\tesseract'
$files = @{
    'chi_sim.traineddata' = @('https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/chi_sim.traineddata', 'a5fcb6f0db1e1d6d8522f39db4e848f05984669172e584e8d76b6b3141e1f730')
    'eng.traineddata' = @('https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/eng.traineddata', '7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2')
}
New-Item -ItemType Directory -Path $modelDir -Force | Out-Null
$curl = (Get-Command curl.exe -ErrorAction Stop).Source
foreach ($name in $files.Keys) {
    $destination = Join-Path $modelDir $name
    $expected = $files[$name][1]
    if ((Test-Path -LiteralPath $destination) -and (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -eq $expected) { continue }
    $options = @('--fail', '--location', '--retry', '3', '--output', $destination)
    if ($DirectNetwork) { $options += @('--noproxy', '*') }
    & $curl @options $files[$name][0]
    if ($LASTEXITCODE -ne 0 -or (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
        throw "OCR model download or checksum verification failed: $name"
    }
}
$tesseract = Get-Command tesseract -ErrorAction SilentlyContinue
if (-not $tesseract) { $tesseractPath = Join-Path $env:ProgramFiles 'Tesseract-OCR\tesseract.exe'; if (Test-Path $tesseractPath) { $tesseract = $tesseractPath } }
$pdftoppm = Get-Command pdftoppm -ErrorAction SilentlyContinue
if (-not $pdftoppm) { $pdftoppmPath = Join-Path $env:LOCALAPPDATA 'Programs\MiKTeX\miktex\bin\x64\pdftoppm.exe'; if (Test-Path $pdftoppmPath) { $pdftoppm = $pdftoppmPath } }
if (-not $tesseract -or -not $pdftoppm) {
    Write-Warning 'OCR language models are ready, but Tesseract OCR or pdftoppm is not installed on this computer.'
} else {
    Write-Host "OCR is ready. Models: $modelDir"
}
