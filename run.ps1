& "$PSScriptRoot\build.ps1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& "$PSScriptRoot\KinectHoard.App\bin\Release\net48\KinectHoard.App.exe"
