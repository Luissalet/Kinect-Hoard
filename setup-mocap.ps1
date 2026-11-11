$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root '.venv-mocap\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    py -3.13 -m venv (Join-Path $root '.venv-mocap')
    if ($LASTEXITCODE -ne 0) { throw 'Instala Python 3.13 x64 para la captura de movimiento.' }
}
& $python -m pip install -r (Join-Path $root 'requirements-mocap.txt')
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar MediaPipe, OpenCV y SciPy.' }
$models = Join-Path $root '.cache\mocap'
New-Item -ItemType Directory -Force $models | Out-Null
foreach ($model in 'lite', 'full', 'heavy') {
    $target = Join-Path $models "pose_landmarker_$model.task"
    if (-not (Test-Path -LiteralPath $target)) {
        $url = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_$model/float16/latest/pose_landmarker_$model.task"
        Invoke-WebRequest $url -OutFile $target -UseBasicParsing
    }
}
Write-Host "Captura de movimiento: $python $root\mocap.py"
