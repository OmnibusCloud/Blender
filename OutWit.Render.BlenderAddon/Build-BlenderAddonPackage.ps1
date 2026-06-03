param(
    [ValidateSet('win-x64', 'linux-x64', 'osx-arm64')]
    [string]$RuntimeIdentifier = 'win-x64',

    [ValidateSet('SelfContained', 'FrameworkDependent')]
    [string]$DeploymentMode = 'SelfContained',

    [string]$BridgePublishPath = '',

    [switch]$SkipBridgePublish
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$packageRoot = Join-Path $scriptRoot 'outwit_render_bridge'
$bridgeProject = Join-Path $scriptRoot '..\OutWit.Render.BlenderBridge\OutWit.Render.BlenderBridge.csproj'
$distRoot = Join-Path $scriptRoot 'dist'
$artifactsRoot = Join-Path $scriptRoot 'artifacts'
$stagingRoot = Join-Path $artifactsRoot 'staging'
$publishRoot = Join-Path $artifactsRoot 'publish'

if (-not (Test-Path $packageRoot))
{
    throw "Blender addon package folder was not found: $packageRoot"
}

if (-not (Test-Path $bridgeProject))
{
    throw "Blender bridge project was not found: $bridgeProject"
}

$initFile = Join-Path $packageRoot '__init__.py'
if (-not (Test-Path $initFile))
{
    throw "Blender addon __init__.py was not found: $initFile"
}

$initContent = Get-Content $initFile -Raw
$versionMatch = [regex]::Match($initContent, '"version"\s*:\s*\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)\)')
if (-not $versionMatch.Success)
{
    throw "Could not parse addon version from: $initFile"
}

$version = '{0}.{1}.{2}' -f $versionMatch.Groups[1].Value, $versionMatch.Groups[2].Value, $versionMatch.Groups[3].Value
$modeFolder = if ($DeploymentMode -eq 'SelfContained') { 'self-contained' } else { 'framework-dependent' }
$modeSuffix = if ($DeploymentMode -eq 'SelfContained') { 'selfcontained' } else { 'dotnet' }
$zipName = "omnibuscloud-render-bridge-blender-addon-$RuntimeIdentifier-$modeSuffix-$version.zip"
$zipPath = Join-Path $distRoot $zipName
$stagingVariantRoot = Join-Path $stagingRoot "$RuntimeIdentifier-$modeSuffix"
$stagingPackageRoot = $stagingVariantRoot
$stagingBridgeRoot = Join-Path $stagingPackageRoot "bridge\$RuntimeIdentifier\$modeFolder"

function Remove-PythonCaches([string]$root)
{
    if (-not (Test-Path $root))
    {
        return
    }

    Get-ChildItem -Path $root -Directory -Filter '__pycache__' -Recurse | Remove-Item -Recurse -Force
    Get-ChildItem -Path $root -File -Filter '*.pyc' -Recurse | Remove-Item -Force
}

function Publish-Bridge([string]$outputPath)
{
    $arguments = @(
        'publish',
        $bridgeProject,
        '-c', 'Release',
        '-r', $RuntimeIdentifier,
        '-o', $outputPath
    )

    if ($DeploymentMode -eq 'SelfContained')
    {
        $arguments += @('--self-contained', 'true', '/p:PublishSingleFile=true', '/p:PublishTrimmed=false')
    }
    else
    {
        $arguments += @('--self-contained', 'false', '/p:UseAppHost=true')
    }

    & dotnet @arguments
    if ($LASTEXITCODE -ne 0)
    {
        throw "Bridge publish failed for $RuntimeIdentifier / $DeploymentMode."
    }
}

if (-not (Test-Path $distRoot))
{
    New-Item -ItemType Directory -Path $distRoot | Out-Null
}

if (Test-Path $stagingVariantRoot)
{
    Remove-Item $stagingVariantRoot -Recurse -Force
}

New-Item -ItemType Directory -Path $stagingPackageRoot -Force | Out-Null
Copy-Item -Path (Join-Path $packageRoot '*') -Destination $stagingPackageRoot -Recurse -Force
Remove-PythonCaches -root $stagingPackageRoot

$effectiveBridgePublishPath = $BridgePublishPath
if ([string]::IsNullOrWhiteSpace($effectiveBridgePublishPath))
{
    $effectiveBridgePublishPath = Join-Path $publishRoot "$RuntimeIdentifier-$modeSuffix"
}

if (-not $SkipBridgePublish)
{
    if (Test-Path $effectiveBridgePublishPath)
    {
        Remove-Item $effectiveBridgePublishPath -Recurse -Force
    }

    New-Item -ItemType Directory -Path $effectiveBridgePublishPath -Force | Out-Null
    Publish-Bridge -outputPath $effectiveBridgePublishPath
}

if (-not (Test-Path $effectiveBridgePublishPath))
{
    throw "Bridge publish output was not found: $effectiveBridgePublishPath"
}

New-Item -ItemType Directory -Path $stagingBridgeRoot -Force | Out-Null
Copy-Item -Path (Join-Path $effectiveBridgePublishPath '*') -Destination $stagingBridgeRoot -Recurse -Force

if (Test-Path $zipPath)
{
    Remove-Item $zipPath -Force
}

Compress-Archive -Path (Join-Path $stagingVariantRoot '*') -DestinationPath $zipPath -CompressionLevel Optimal
Write-Output "Created Blender addon package: $zipPath"
