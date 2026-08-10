param(
    [Parameter(Mandatory = $true)][string]$PhaseManifest,
    [Parameter(Mandatory = $true)][string]$LatestManifest,
    [Parameter(Mandatory = $true)][string]$VerificationNotes,
    [Parameter(Mandatory = $true)][switch]$PlaybackVerified
)

$ErrorActionPreference = "Stop"
if (-not $PlaybackVerified) { throw "Latest demo promotion requires explicit playback verification." }
$PhaseManifest = [IO.Path]::GetFullPath($PhaseManifest)
$LatestManifest = [IO.Path]::GetFullPath($LatestManifest)
$manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $PhaseManifest | ConvertFrom-Json
if ($manifest.status -ne "encoded_unverified" -or $manifest.playback_verified) {
    throw "Phase demo is not awaiting playback verification."
}
$devlogRoot = [IO.Path]::GetDirectoryName([IO.Path]::GetDirectoryName($LatestManifest))
$devlogPrefix = $devlogRoot.TrimEnd("\") + "\"
if (-not $PhaseManifest.StartsWith($devlogPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Phase demo manifest must be inside the devlog tree."
}
$relativePhaseManifest = $PhaseManifest.Substring($devlogPrefix.Length).Replace("\", "/")
$video = [IO.Path]::GetFullPath((Join-Path $devlogRoot $manifest.devlog_video_path))
$poster = [IO.Path]::GetFullPath((Join-Path $devlogRoot $manifest.devlog_poster_path))
if (-not (Test-Path -LiteralPath $video) -or -not (Test-Path -LiteralPath $poster)) {
    throw "Verified demo media is missing."
}
if ((Get-FileHash -LiteralPath $video -Algorithm SHA256).Hash -ne $manifest.encoded_sha256) {
    throw "Verified demo video hash changed before promotion."
}
$verifiedAt = [DateTimeOffset]::UtcNow.ToString("o")
$manifest.status = "verified"
$manifest.playback_verified = $true
$manifest.playback_verified_at_utc = $verifiedAt
$manifest.verification_notes = $VerificationNotes
$manifest.eligible_for_latest = $true
$latest = [ordered]@{
    schema = "campfire.devlog-latest-demo.v1"
    status = "verified"
    phase = $manifest.phase
    change_name = $manifest.change_name
    source_commit = $manifest.source_commit
    video_path = $manifest.devlog_video_path
    poster_path = $manifest.devlog_poster_path
    focus = $manifest.focus
    scenario_runner = $manifest.scenario_runner
    common_runner = $manifest.common_runner
    generated_at_utc = $manifest.generated_at_utc
    playback_verified_at_utc = $verifiedAt
    verification_notes = $VerificationNotes
    feature_flags = $manifest.feature_flags
    duration_seconds = $manifest.duration_seconds
    encoded_sha256 = $manifest.encoded_sha256
    phase_manifest_path = $relativePhaseManifest
}
New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($LatestManifest)) -Force | Out-Null
[IO.File]::WriteAllText($PhaseManifest, ($manifest | ConvertTo-Json -Depth 20) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText($LatestManifest, ($latest | ConvertTo-Json -Depth 20) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Host "Latest demo promoted after playback verification: $($manifest.phase)"
