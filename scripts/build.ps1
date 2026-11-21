param([string]$Toolchain='C:\msys64\ucrt64\bin', [string]$Configuration='Debug')
$ErrorActionPreference='Stop'
$env:PATH="$Toolchain;$env:PATH"
$sourceRoot=Split-Path $PSScriptRoot -Parent
$buildRoot=Join-Path (Split-Path $sourceRoot -Parent) "PulseMetrics_V2_BUILD/$($Configuration.ToLower())"
& cmake -S $sourceRoot -B $buildRoot -G Ninja "-DCMAKE_BUILD_TYPE=$Configuration"
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& cmake --build $buildRoot --parallel 2
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& ctest --test-dir $buildRoot --output-on-failure
exit $LASTEXITCODE
