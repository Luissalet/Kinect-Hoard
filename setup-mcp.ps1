$ErrorActionPreference = 'Stop'
$venv = Join-Path $PSScriptRoot '.venv'
if (-not (Test-Path -LiteralPath (Join-Path $venv 'Scripts\python.exe'))) {
    py -3 -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno de Python. Se requiere Python 3.11 o superior.' }
}
$python = Join-Path $venv 'Scripts\python.exe'
& $python -m pip install -r (Join-Path $PSScriptRoot 'requirements-mcp.txt')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$link = Join-Path (Split-Path $PSScriptRoot -Parent) 'HoardLink'
if (-not (Test-Path -LiteralPath (Join-Path $link 'pyproject.toml'))) { throw 'Falta HoardLink junto a Kinect-Hoard para instalar la biblioteca comun de la familia.' }
& $python -m pip install $link
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "MCP listo: $python $PSScriptRoot\mcp_server.py"
