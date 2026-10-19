$ErrorActionPreference = 'Stop'
& "$PSScriptRoot\build.ps1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$scanExe = Join-Path $PSScriptRoot '.cache\scan-dist\KinectHoard.Fusion\KinectHoard.Fusion.exe'
$scanRuntime = Join-Path $PSScriptRoot '.cache\scan-dist\KinectHoard.Fusion\_internal'
$scanInputs = @('fusion.py', 'quality_scan.py', 'dual_calibration.py', 'build-scan.ps1', 'setup-scan.ps1', 'requirements-scan.txt', 'requirements-scan-build.txt') |
    ForEach-Object { Join-Path $PSScriptRoot $_ }
$needsScanBuild = -not (Test-Path -LiteralPath $scanExe) -or -not (Test-Path -LiteralPath $scanRuntime)
if (-not $needsScanBuild) {
    $bundleTime = (Get-Item -LiteralPath $scanExe).LastWriteTimeUtc
    $needsScanBuild = @($scanInputs | Where-Object { (Get-Item -LiteralPath $_).LastWriteTimeUtc -gt $bundleTime }).Count -gt 0
}
if ($needsScanBuild) {
    & "$PSScriptRoot\build-scan.ps1"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else { Write-Host 'Fusion: reutilizando ejecutable sin cambios.' }
$target = Join-Path $PSScriptRoot 'KinectHoard.App\bin\Release\net48'
$stage = Join-Path $PSScriptRoot '.cache\release\KinectHoard-One'
$rootFull = [System.IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$stageFull = [System.IO.Path]::GetFullPath($stage)
if (-not $stageFull.StartsWith($rootFull + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw "Ruta temporal fuera del proyecto: $stageFull"
}
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $target 'KinectHoard.App.exe') -Destination $stage
Copy-Item -LiteralPath (Join-Path $target 'KinectHoard.App.exe.config') -Destination $stage
Copy-Item -LiteralPath (Join-Path $target 'speech-commands.txt') -Destination $stage
Get-ChildItem -LiteralPath $target -Filter '*.dll' -File | Copy-Item -Destination $stage
Copy-Item -LiteralPath (Join-Path $target 'models') -Destination $stage -Recurse
Copy-Item -LiteralPath (Join-Path $target 'NuiDatabase') -Destination $stage -Recurse
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'install-one-runtime.ps1') -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'install-360-driver.ps1') -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'diagnose-usb.ps1') -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'diagnose-audio.ps1') -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'setup-mcp.ps1') -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'launch-hoard.ps1') -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'mcp_server.py') -Destination $stage
foreach ($name in @('hoard_server.py', 'camera_runtime.py', 'scanner_worker.py', 'workspace_catalog.py', 'app-icon.svg', 'app-icon.png', 'app-icon.ico')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $stage
}
foreach ($name in @('ui', 'integrations')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $stage -Recurse
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'fusion.py') -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'quality_scan.py') -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'dual_calibration.py') -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot '.cache\scan-dist\KinectHoard.Fusion\KinectHoard.Fusion.exe') -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot '.cache\scan-dist\KinectHoard.Fusion\_internal') -Destination $stage -Recurse
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'build-scan.ps1') -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'build-native360.ps1') -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'setup-scan.ps1') -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'requirements-scan.txt') -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'requirements-scan-build.txt') -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'requirements-mcp.txt') -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'faustus-plugin.json') -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'docs') -Destination $stage -Recurse
$exampleStage = Join-Path $stage 'examples'
New-Item -ItemType Directory -Path $exampleStage -Force | Out-Null
Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'examples') -File | Copy-Item -Destination $exampleStage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'licenses') -Destination $stage -Recurse
foreach ($project in @('KinectHoard.Core', 'KinectHoard.Driver.One', 'KinectHoard.Driver.ThreeSixty', 'KinectHoard.Driver.ThreeSixty.Native', 'KinectHoard.App')) {
    $source = Join-Path $PSScriptRoot $project
    $destination = Join-Path $stage $project
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    Get-ChildItem -LiteralPath $source -File | Where-Object { $_.Extension -in @('.cs', '.csproj') } |
        Copy-Item -Destination $destination
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'KinectHoard.Native360') -Destination $stage -Recurse
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'README.md') -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'PRIVACY.md') -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'THIRD_PARTY_NOTICES.md') -Destination $stage
$zip = Join-Path $PSScriptRoot 'KinectHoard-One.zip'
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip
Write-Host "Paquete: $zip"
