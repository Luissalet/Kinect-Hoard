$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root '.venv-scan\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    py -3.12 -m venv (Join-Path $root '.venv-scan')
    if ($LASTEXITCODE -ne 0) { throw 'Instala Python 3.12 x64 para el módulo de escaneo.' }
}
& $python -m pip install -r (Join-Path $root 'requirements-scan.txt')
if ($LASTEXITCODE -ne 0) { throw 'No se pudo instalar Open3D para Fusion.' }
Write-Host "Fusion: $python"
