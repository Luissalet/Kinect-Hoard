$ErrorActionPreference = 'Stop'
$venv = Join-Path $PSScriptRoot '.venv'
if (-not (Test-Path -LiteralPath (Join-Path $venv 'Scripts\python.exe'))) {
    py -3 -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno de Python. Se requiere Python 3.11 o superior.' }
}
$python = Join-Path $venv 'Scripts\python.exe'
& $python -m pip install -r (Join-Path $PSScriptRoot 'requirements-mcp.txt')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "MCP listo: $python $PSScriptRoot\mcp_server.py"
