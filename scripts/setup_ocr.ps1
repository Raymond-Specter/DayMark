[CmdletBinding()]
param([switch]$DirectNetwork)

$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$modelDir = Join-Path $workspace 'models\tesseract'
$files = @{
    'chi_sim.traineddata' = @('https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/chi_sim.traineddata', '4fef2d1306c8e87616d4d3e4c6c67faf5d44be3342290cf8f2f0f6e3aa7e735b')
    'chi_sim_vert.traineddata' = @('https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/chi_sim_vert.traineddata', 'ea672a78157199c333aa12ec4e74550077689b545df5fc770903716850c8b2e5')
    'eng.traineddata' = @('https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/eng.traineddata', '8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba')
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
