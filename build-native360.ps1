$ErrorActionPreference = 'Stop'
$root = [System.IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$cache = Join-Path $root '.cache'
$source = Join-Path $cache 'libfreenect-src'
$libusbArchive = Join-Path $cache 'libusb-1.0.27.7z'
$libusb = Join-Path $cache 'libusb'
$freenectBuild = Join-Path $cache 'libfreenect-build'
$bridgeBuild = Join-Path $cache 'native360-build'
$output = Join-Path $root 'native\win-x64'
$freenectCommit = '09a1f098040d00e6070c18174904547ec31d2774'
$libusbSha256 = '19835E290F46FAB6BD8CE4BE6AB7DC5209F1C04BAD177065DF485E51DC4118C8'
$cmake = 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
if (-not (Test-Path -LiteralPath $cmake)) { throw 'Instala Visual Studio 2022 Build Tools con CMake y MSVC x64.' }
New-Item -ItemType Directory -Force -Path $cache, $output | Out-Null
if (-not (Test-Path -LiteralPath $source)) {
    git clone https://github.com/OpenKinect/libfreenect.git $source
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo descargar libfreenect.' }
}
git -C $source fetch origin $freenectCommit
if ($LASTEXITCODE -ne 0) { throw 'No se pudo obtener la versión fijada de libfreenect.' }
git -C $source checkout --detach $freenectCommit
if ($LASTEXITCODE -ne 0) { throw 'No se pudo seleccionar la versión fijada de libfreenect.' }
if (-not (Test-Path -LiteralPath $libusbArchive)) {
    Invoke-WebRequest 'https://github.com/libusb/libusb/releases/download/v1.0.27/libusb-1.0.27.7z' -OutFile $libusbArchive
}
if ((Get-FileHash -LiteralPath $libusbArchive -Algorithm SHA256).Hash -ne $libusbSha256) {
    throw 'El archivo libusb no coincide con el SHA-256 esperado.'
}
if (-not (Test-Path -LiteralPath (Join-Path $libusb 'VS2022\MS64\dll\libusb-1.0.lib'))) {
    New-Item -ItemType Directory -Force -Path $libusb | Out-Null
    tar.exe -xf $libusbArchive -C $libusb
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo extraer libusb.' }
}
& $cmake -S $source -B $freenectBuild -G 'Visual Studio 17 2022' -A x64 `
    -D BUILD_C_SYNC=OFF -D BUILD_REDIST_PACKAGE=ON `
    -D "LIBUSB_1_INCLUDE_DIRS=$(Join-Path $libusb 'include')" `
    -D "LIBUSB_1_LIBRARIES=$(Join-Path $libusb 'VS2022\MS64\dll\libusb-1.0.lib')"
if ($LASTEXITCODE -ne 0) { throw 'Configuración de libfreenect fallida.' }
& $cmake --build $freenectBuild --config Release --target freenect
if ($LASTEXITCODE -ne 0) { throw 'Compilación de libfreenect fallida.' }
& $cmake -S (Join-Path $root 'KinectHoard.Native360') -B $bridgeBuild -G 'Visual Studio 17 2022' -A x64 `
    -D "FREENECT_INCLUDE_DIR=$(Join-Path $source 'include')" `
    -D "FREENECT_LIBRARY=$(Join-Path $freenectBuild 'lib\Release\freenect.lib')"
if ($LASTEXITCODE -ne 0) { throw 'Configuración del puente 360 fallida.' }
& $cmake --build $bridgeBuild --config Release
if ($LASTEXITCODE -ne 0) { throw 'Compilación del puente 360 fallida.' }
Copy-Item -LiteralPath (Join-Path $bridgeBuild 'Release\KinectHoard.Native360.dll') -Destination $output
Copy-Item -LiteralPath (Join-Path $freenectBuild 'lib\Release\freenect.dll') -Destination $output
Copy-Item -LiteralPath (Join-Path $libusb 'VS2022\MS64\dll\libusb-1.0.dll') -Destination $output
Write-Host "Controlador nativo construido en $output"
