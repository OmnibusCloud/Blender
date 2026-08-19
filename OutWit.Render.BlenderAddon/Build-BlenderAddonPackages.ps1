Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$buildScript = Join-Path $scriptRoot 'Build-BlenderAddonPackage.ps1'
$distRoot = Join-Path $scriptRoot 'dist'

$runtimes = @('win-x64', 'linux-x64', 'osx-arm64')

if (Test-Path $distRoot)
{
    Get-ChildItem -Path $distRoot -File -Filter 'omnibuscloud-render-blender-addon-*.zip' | Remove-Item -Force
}

foreach ($runtime in $runtimes)
{
    Write-Output "Building Blender addon package for $runtime ..."
    & $buildScript -RuntimeIdentifier $runtime
    if ($LASTEXITCODE -ne 0)
    {
        throw "Blender addon package build failed for $runtime."
    }
}

Write-Output 'Created all Blender addon packages.'
