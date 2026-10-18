$ErrorActionPreference = 'Stop'
$exe = Join-Path $PSScriptRoot 'KinectHoard.App.exe'
if (-not (Test-Path -LiteralPath $exe)) { $exe = Join-Path $PSScriptRoot 'KinectHoard.App\bin\Release\net48\KinectHoard.App.exe' }
if (-not (Test-Path -LiteralPath $exe)) { throw 'KinectHoard.App.exe no existe; compila con build.ps1.' }
Start-Process -FilePath $exe
