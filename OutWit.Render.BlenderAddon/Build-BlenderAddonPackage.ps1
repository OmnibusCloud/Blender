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

# The addon version lives in two files; Blender reads bl_info (legacy install) and the manifest
# (extension install). Keep them equal so both report the same version.
$manifestFile = Join-Path $packageRoot 'blender_manifest.toml'
if (Test-Path $manifestFile)
{
    $manifestContent = Get-Content $manifestFile -Raw
    $manifestVersionMatch = [regex]::Match($manifestContent, '(?m)^\s*version\s*=\s*"([^"]+)"')
    if (-not $manifestVersionMatch.Success)
    {
        throw "Could not parse version from blender_manifest.toml: $manifestFile"
    }
    if ($manifestVersionMatch.Groups[1].Value -ne $version)
    {
        throw "Version mismatch: __init__.py bl_info is '$version' but blender_manifest.toml is '$($manifestVersionMatch.Groups[1].Value)'. Bump both to the same value."
    }
}

# Map .NET RID -> Blender extension platform tag so each per-platform zip declares its target OS
# (the repository serves the right zip per OS, and install-from-disk refuses a wrong-arch package).
$platformTag = switch ($RuntimeIdentifier)
{
    'win-x64' { 'windows-x64' }
    'linux-x64' { 'linux-x64' }
    'osx-arm64' { 'macos-arm64' }
    default { throw "No Blender platform tag mapping for runtime '$RuntimeIdentifier'." }
}

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
        '-o', $outputPath,
        # Stamp the bridge with the addon version (bl_info/manifest, validated equal above) so
        # GetBridgeStatusAsync reports the release it shipped with instead of a static 1.0.0.
        "/p:Version=$version"
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

# Stamp this build's target platform into the staged manifest so the zip is platform-specific.
$stagedManifest = Join-Path $stagingPackageRoot 'blender_manifest.toml'
if (Test-Path $stagedManifest)
{
    $stagedManifestContent = Get-Content $stagedManifest -Raw
    $platformsLine = "platforms = [`"$platformTag`"]"
    if ($stagedManifestContent -match '(?m)^\s*platforms\s*=.*$')
    {
        # Replace an existing top-level platforms key.
        $stagedManifestContent = [regex]::Replace($stagedManifestContent, '(?m)^\s*platforms\s*=.*$', $platformsLine)
    }
    elseif ($stagedManifestContent -match '(?m)^\[')
    {
        # Insert as a TOP-LEVEL key BEFORE the first TOML table header (e.g. [permissions]); a key
        # placed after a table header would be parsed as belonging to that table, corrupting the manifest.
        $tableHeaderRegex = [regex]'(?m)^\['
        $stagedManifestContent = $tableHeaderRegex.Replace($stagedManifestContent, "$platformsLine`n`n[", 1)
    }
    else
    {
        # No tables in the manifest: a trailing top-level key is safe.
        $stagedManifestContent = $stagedManifestContent.TrimEnd() + "`n$platformsLine`n"
    }
    Set-Content -Path $stagedManifest -Value $stagedManifestContent -NoNewline
}

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
