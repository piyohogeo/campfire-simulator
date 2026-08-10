Set-StrictMode -Version 3.0
$script:CampfireIsolatedKitPrivacyFile = Join-Path $PSScriptRoot "isolated_kit_privacy.toml"

function New-CampfireIsolatedKitApp {
    param([Parameter(Mandatory = $true)][string]$SourceApp)

    $source = [IO.Path]::GetFullPath($SourceApp)
    if (-not (Test-Path -LiteralPath $source)) { throw "Kit app source does not exist: $source" }
    $sourceDirectory = [IO.Path]::GetDirectoryName($source)
    $destinationDirectory = Join-Path ([IO.Path]::GetDirectoryName($sourceDirectory)) "isolated-apps"
    New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
    $destination = Join-Path $destinationDirectory (([IO.Path]::GetFileNameWithoutExtension($source)) + ".isolated.kit")
    $text = [IO.File]::ReadAllText($source)
    $text = $text -replace '(?m)^telemetry\.enableAnonymousData\s*=\s*(?:true|false)\s*\r?\n', ''
    $settingsMarker = "[settings]"
    $markerIndex = $text.IndexOf($settingsMarker, [StringComparison]::Ordinal)
    if ($markerIndex -lt 0) { throw "Kit app has no [settings] table: $source" }
    $lineEnd = $text.IndexOf("`n", $markerIndex)
    if ($lineEnd -lt 0) { $lineEnd = $text.Length - 1 }
    $safety = @"
app.uploadDumpsOnStartup = false
crashreporter.devOnlyOverridePrivacyAndForceUpload = false
crashreporter.compressDumpFiles = true
crashreporter.gatherUserStory = false
crashreporter.preserveDump = true
crashreporter.skipOldDumpUpload = true
crashreporter.url = ""
telemetry.enableAnonymousData = false
privacy.externalBuild = false
privacy.performance = false
privacy.personalization = false
privacy.usage = false
privacy.extraDiagnosticDataOptIn = ""
"@
    $text = $text.Insert($lineEnd + 1, $safety + [Environment]::NewLine)
    [IO.File]::WriteAllText($destination, $text, [Text.UTF8Encoding]::new($false))
    return $destination
}

function Get-CampfireIsolatedKitCrashSafetyArgs {
    param([Parameter(Mandatory = $true)][string]$DumpDir)

    $resolved = [IO.Path]::GetFullPath($DumpDir)
    New-Item -ItemType Directory -Path $resolved -Force | Out-Null
    return @(
        "--/app/uploadDumpsOnStartup=false"
        "--/crashreporter/enabled=true"
        "--/crashreporter/compressDumpFiles=true"
        "--/crashreporter/skipOldDumpUpload=true"
        "--/crashreporter/preserveDump=true"
        "--/crashreporter/gatherUserStory=false"
        "--/crashreporter/devOnlyOverridePrivacyAndForceUpload=false"
        "--/crashreporter/url="
        "--/crashreporter/dumpDir=$resolved"
        "--/structuredLog/privacySettingsFile=$script:CampfireIsolatedKitPrivacyFile"
        "--/privacy/performance=false"
        "--/privacy/usage=false"
        "--/privacy/personalization=false"
        "--/privacy/extraDiagnosticDataOptIn=false"
    )
}

function Get-CampfireCrashDumpInventory {
    param([Parameter(Mandatory = $true)][string]$DumpDir)

    if (-not (Test-Path -LiteralPath $DumpDir)) { return @() }
    return @(Get-ChildItem -LiteralPath $DumpDir -File -Force | Where-Object {
        $_.Name -match '\.dmp(?:\.zip)?$|\.dmp\.toml$|\.dmp\.txt$'
    } | ForEach-Object {
        $hash = $null
        $readable = $false
        try {
            $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256 -ErrorAction Stop).Hash
            $readable = $true
        } catch {
            # Crash Reporter may still hold the archive while compressing it.
            # Callers can poll again; a partially written archive is never treated as verified.
        }
        [ordered]@{
            name = $_.Name
            path = $_.FullName
            bytes = $_.Length
            sha256 = $hash
            readable = $readable
            sensitive_local_artifact = $true
        }
    })
}

function Get-CampfireCrashRegistrySnapshot {
    $paths = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\Windows Error Reporting",
        "HKLM:\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps",
        "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\AeDebug",
        "HKCU:\SOFTWARE\Microsoft\Windows\Windows Error Reporting",
        "HKCU:\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps"
    )
    $snapshot = [ordered]@{}
    foreach ($path in $paths) {
        if (-not (Test-Path -LiteralPath $path)) {
            $snapshot[$path] = $null
            continue
        }
        $properties = [ordered]@{}
        $item = Get-ItemProperty -LiteralPath $path
        foreach ($property in $item.PSObject.Properties | Where-Object { $_.Name -notmatch '^PS' } | Sort-Object Name) {
            $properties[$property.Name] = $property.Value
        }
        $snapshot[$path] = $properties
    }
    return $snapshot
}

function Get-CampfireCrashSafetyEvidence {
    param(
        [Parameter(Mandatory = $true)][string]$LogPath,
        [Parameter(Mandatory = $true)][string]$DumpDir
    )

    $configured = @()
    if (Test-Path -LiteralPath $LogPath) {
        $configured = @(Select-String -LiteralPath $LogPath -SimpleMatch @(
            "crash reporter has been successfully initialized",
            "upload enabled:",
            "preserve dump enabled:",
            "preventing upload of minidump"
        ) | ForEach-Object { $_.Line })
    }
    return [ordered]@{
        automatic_upload_disabled_by = @(
            "/app/uploadDumpsOnStartup=false",
            "/crashreporter/skipOldDumpUpload=true",
            "/crashreporter/devOnlyOverridePrivacyAndForceUpload=false",
            "/crashreporter/url=<empty>",
            "/structuredLog/privacySettingsFile=<repo-local opt-out file>",
            "/privacy/performance=false"
        )
        preserve_dump_requested = $true
        gather_user_story_requested = $false
        configured_log_lines = $configured
        dump_inventory = @(Get-CampfireCrashDumpInventory -DumpDir $DumpDir)
    }
}
