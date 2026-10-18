$ErrorActionPreference = 'Stop'
& "$PSScriptRoot\setup-scan.ps1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$python = Join-Path $PSScriptRoot '.venv-scan\Scripts\python.exe'
& $python -m pip install -r (Join-Path $PSScriptRoot 'requirements-scan-build.txt')
if ($LASTEXITCODE -ne 0) { throw 'No se pudo instalar PyInstaller.' }
Push-Location $PSScriptRoot
try {
    & $python -m PyInstaller --noconfirm --onedir --name KinectHoard.Fusion `
        --distpath '.cache\scan-dist' --workpath '.cache\scan-build' --specpath '.cache\scan-build' `
        --exclude-module torch --exclude-module tensorflow --exclude-module tensorboard `
        --exclude-module jupyter --exclude-module notebook --exclude-module matplotlib `
        --exclude-module vtk --exclude-module sklearn --exclude-module pandas fusion.py
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el ejecutable de Fusion.' }
    & '.\.cache\scan-dist\KinectHoard.Fusion\KinectHoard.Fusion.exe' --help | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'El ejecutable de Fusion no arranca.' }
}
finally { Pop-Location }
