param(
    [Parameter(Mandatory = $true)][string]$Phase,
    [Parameter(Mandatory = $true)][string]$ChangeName,
    [Parameter(Mandatory = $true)][string]$Focus,
    [Parameter(Mandatory = $true)][string]$ScenarioScript,
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [Parameter(Mandatory = $true)][string]$OutputVideo,
    [Parameter(Mandatory = $true)][string]$OutputPoster,
    [Parameter(Mandatory = $true)][string]$PhaseManifest,
    [Parameter(Mandatory = $true)][string]$DevlogVideoPath,
    [Parameter(Mandatory = $true)][string]$DevlogPosterPath,
    [ValidateRange(10, 60)][int]$EncodedFps = 30,
    [ValidateRange(1, 30)][int]$SourceFps = 10
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
$OutputVideo = [IO.Path]::GetFullPath($OutputVideo)
$OutputPoster = [IO.Path]::GetFullPath($OutputPoster)
$PhaseManifest = [IO.Path]::GetFullPath($PhaseManifest)
$ScenarioScript = [IO.Path]::GetFullPath($ScenarioScript)
if (Test-Path -LiteralPath $OutputDir) {
    throw "Demo build refuses to reuse artifact output: $OutputDir"
}
if (-not (Test-Path -LiteralPath $ScenarioScript)) {
    throw "Demo scenario runner does not exist: $ScenarioScript"
}
$scenarioDir = Join-Path $OutputDir "scenario"
$captureRoot = Join-Path $scenarioDir "captures"
$stagedFrames = Join-Path $OutputDir "encode_frames"
New-Item -ItemType Directory -Path $scenarioDir, $stagedFrames -Force | Out-Null

& $ScenarioScript -OutputDir $scenarioDir -CaptureRoot $captureRoot `
    -RtxVisualPreset CandidatePerformance -Width 1280 -Height 720
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$scenarioManifestPath = Join-Path $scenarioDir "scenario_manifest.json"
$scenario = Get-Content -Raw -Encoding UTF8 -LiteralPath $scenarioManifestPath | ConvertFrom-Json
if (
    $scenario.status -ne "ok" -or
    $scenario.phase -ne $Phase -or
    $scenario.rendering.preset -ne "CandidatePerformance" -or
    [int]$scenario.rendering.aa_op -ne 3 -or
    [int]$scenario.rendering.dlss_exec_mode -ne 0 -or
    [int]$scenario.rendering.max_bounces -ne 2 -or
    @($scenario.rendering.resolution)[0] -ne 1280 -or
    @($scenario.rendering.resolution)[1] -ne 720
) {
    throw "Demo scenario did not prove Candidate Performance at 1280x720."
}

$fatalTokens = @(
    "IRenderSettings::getRenderSettings failed getting a stage-id",
    "Traceback (most recent call last)",
    "CUDA_ERROR_ILLEGAL_ADDRESS",
    "device lost",
    "invalid pointer",
    "[crash] A crash has occurred",
    "Uploading minidump:"
)
$fatalCounts = [ordered]@{}
foreach ($token in $fatalTokens) { $fatalCounts[$token] = 0 }
foreach ($log in @($scenario.kit_logs)) {
    if (-not (Test-Path -LiteralPath $log)) { throw "Scenario Kit log missing: $log" }
    foreach ($token in $fatalTokens) {
        $fatalCounts[$token] += @(Select-String -LiteralPath $log -SimpleMatch $token).Count
    }
}
$dumpFiles = @()
foreach ($directory in @($scenario.crash_dump_directories)) {
    if (Test-Path -LiteralPath $directory) {
        $dumpFiles += @(Get-ChildItem -LiteralPath $directory -File -Force | Where-Object {
            $_.Name -match '\.dmp(?:\.zip)?$|\.dmp\.toml$|\.dmp\.txt$'
        })
    }
}
if (($fatalCounts.Values | Measure-Object -Sum).Sum -ne 0 -or $dumpFiles.Count) {
    throw "Demo scenario rejected by fatal/crash/dump/upload safety gate."
}

function Read-PngSize([string]$Path) {
    $bytes = [IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -lt 24) { throw "PNG is truncated: $Path" }
    $width = [Net.IPAddress]::NetworkToHostOrder([BitConverter]::ToInt32($bytes, 16))
    $height = [Net.IPAddress]::NetworkToHostOrder([BitConverter]::ToInt32($bytes, 20))
    return @($width, $height)
}

$frameIndex = 0
$frameHashes = [Collections.Generic.HashSet[string]]::new()
$segmentRecords = @()
$elapsed = 1.5
foreach ($segment in @($scenario.segments)) {
    $frames = @(Get-ChildItem -LiteralPath $segment.frame_directory -Filter "frame_*.png" -File | Sort-Object Name)
    if ($frames.Count -ne [int]$segment.frame_count) {
        throw "Segment $($segment.id) frame count mismatch."
    }
    $segmentUnique = [Collections.Generic.HashSet[string]]::new()
    foreach ($frame in $frames) {
        $size = Read-PngSize $frame.FullName
        if ($size[0] -ne 1280 -or $size[1] -ne 720) {
            throw "Unexpected demo frame size $($size -join 'x'): $($frame.FullName)"
        }
        $hash = (Get-FileHash -LiteralPath $frame.FullName -Algorithm SHA256).Hash
        [void]$segmentUnique.Add($hash)
        [void]$frameHashes.Add($hash)
        Copy-Item -LiteralPath $frame.FullName -Destination (Join-Path $stagedFrames ("frame_{0:D4}.png" -f $frameIndex))
        $frameIndex++
    }
    if ($segmentUnique.Count -lt [Math]::Ceiling($frames.Count * 0.8)) {
        throw "Segment $($segment.id) lacks continuous visual change."
    }
    $duration = $frames.Count / [double]$SourceFps
    $segmentRecords += [ordered]@{
        id = $segment.id
        event_label = $segment.event_label
        frame_count = $frames.Count
        unique_frame_count = $segmentUnique.Count
        start_seconds = $elapsed
        end_seconds = $elapsed + $duration
    }
    $elapsed += $duration
}
if ($frameIndex -lt 2 -or $frameHashes.Count -lt [Math]::Ceiling($frameIndex * 0.8)) {
    throw "Combined demo frames are insufficiently distinct."
}

$ffmpeg = Get-Command ffmpeg.exe -ErrorAction Stop
$ffprobe = Get-Command ffprobe.exe -ErrorAction Stop
$overlayPath = Join-Path $OutputDir "overlay.ass"
function Ass-Time([double]$Seconds) {
    $span = [TimeSpan]::FromSeconds($Seconds)
    return ("{0}:{1:D2}:{2:D2}.{3:D2}" -f [int]$span.TotalHours, $span.Minutes, $span.Seconds, [int]($span.Milliseconds / 10))
}
$ass = @(
    "[Script Info]",
    "ScriptType: v4.00+",
    "PlayResX: 1280",
    "PlayResY: 720",
    "WrapStyle: 2",
    "[V4+ Styles]",
    "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
    "Style: Title,Segoe UI,38,&H00FFFFFF,&H00FFFFFF,&H0010151C,&H88000000,-1,0,0,0,100,100,0,0,3,1,0,7,42,42,36,1",
    "Style: Event,Segoe UI,31,&H00FFFFFF,&H00FFFFFF,&H0010151C,&H99000000,-1,0,0,0,100,100,0,0,3,1,0,1,42,42,38,1",
    "[Events]",
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ("Dialogue: 0,{0},{1},Title,,0,0,0,,{2} - {3}\N{4}" -f (Ass-Time 0), (Ass-Time 1.5), $Phase.ToUpperInvariant(), $ChangeName, $Focus)
)
foreach ($segment in $segmentRecords) {
    $ass += ("Dialogue: 0,{0},{1},Event,,0,0,0,,{2}" -f (Ass-Time $segment.start_seconds), (Ass-Time $segment.end_seconds), $segment.event_label)
}
[IO.File]::WriteAllLines($overlayPath, $ass, [Text.UTF8Encoding]::new($true))

New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($OutputVideo)), ([IO.Path]::GetDirectoryName($OutputPoster)), ([IO.Path]::GetDirectoryName($PhaseManifest)) -Force | Out-Null
$filter = "tpad=start_mode=clone:start_duration=1.5:stop_mode=clone:stop_duration=1.0,fps=$EncodedFps,subtitles=overlay.ass"
Push-Location $OutputDir
try {
    & $ffmpeg.Source -hide_banner -loglevel warning -y -framerate $SourceFps `
        -i "encode_frames/frame_%04d.png" -vf $filter -c:v libx264 `
        -preset medium -crf 22 -pix_fmt yuv420p -movflags +faststart $OutputVideo
    if ($LASTEXITCODE -ne 0) { throw "Demo ffmpeg encode failed: $LASTEXITCODE" }
} finally { Pop-Location }
Copy-Item -LiteralPath $scenario.poster_frame -Destination $OutputPoster -Force

$probeJson = & $ffprobe.Source -v error -select_streams v:0 `
    -show_entries stream=codec_name,width,height,avg_frame_rate,nb_frames,duration `
    -show_entries format=duration -of json $OutputVideo
if ($LASTEXITCODE -ne 0) { throw "Demo ffprobe failed." }
$probe = $probeJson | ConvertFrom-Json
$durationSeconds = [double]$probe.format.duration
if (
    $probe.streams[0].codec_name -ne "h264" -or
    [int]$probe.streams[0].width -ne 1280 -or
    [int]$probe.streams[0].height -ne 720 -or
    $durationSeconds -lt 10.0 -or
    $durationSeconds -gt 30.0
) { throw "Encoded demo does not satisfy codec, resolution, or duration gate." }

$manifest = [ordered]@{
    schema = "campfire.devlog-phase-demo.v1"
    status = "encoded_unverified"
    phase = $Phase
    change_name = $ChangeName
    focus = $Focus
    source_commit = $scenario.source_commit
    generated_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
    scenario_runner = $scenario.scenario_runner
    common_runner = "scripts/build_devlog_demo.ps1"
    rendering = $scenario.rendering
    feature_flags = $scenario.feature_flags
    events = $segmentRecords
    source_frame_count = $frameIndex
    source_unique_frame_count = $frameHashes.Count
    encoded_fps = $EncodedFps
    duration_seconds = [Math]::Round($durationSeconds, 3)
    encoded_bytes = (Get-Item -LiteralPath $OutputVideo).Length
    encoded_sha256 = (Get-FileHash -LiteralPath $OutputVideo -Algorithm SHA256).Hash
    devlog_video_path = $DevlogVideoPath
    devlog_poster_path = $DevlogPosterPath
    fatal_log_counts = $fatalCounts
    crash_dump_count = $dumpFiles.Count
    automatic_upload_attempt_count = [int]$fatalCounts["Uploading minidump:"]
    playback_verified = $false
    playback_verified_at_utc = $null
    verification_notes = $null
    eligible_for_latest = $false
    benchmark_population = $false
    qualification = $scenario.qualification
}
[IO.File]::WriteAllText($PhaseManifest, ($manifest | ConvertTo-Json -Depth 20) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Host "Demo encoded; playback verification required before latest promotion: $OutputVideo"
