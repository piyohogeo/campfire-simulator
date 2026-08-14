param(
    [Parameter(Mandatory = $true)][ValidateSet("progress", "silent", "partial", "descendant")][string]$Mode,
    [Parameter(Mandatory = $true)][string]$ArtifactPath,
    [int]$DurationMilliseconds = 3000,
    [int]$IntervalMilliseconds = 200
)
$deadline = [DateTime]::UtcNow.AddMilliseconds($DurationMilliseconds)
$child = $null
if ($Mode -eq "descendant") {
    $child = Start-Process -FilePath (Get-Process -Id $PID).Path -ArgumentList @("-NoLogo", "-NoProfile", "-Command", "Start-Sleep -Seconds 60") -PassThru -WindowStyle Hidden
    [IO.File]::WriteAllText($ArtifactPath, [string]$child.Id, [Text.UTF8Encoding]::new($false))
}
if ($Mode -eq "partial") {
    [IO.File]::WriteAllText($ArtifactPath, "THREAD_STACKS`nntdll!fixture_wait+0x1`n", [Text.UTF8Encoding]::new($false))
    [Console]::Out.WriteLine("THREAD_STACKS")
    [Console]::Out.Flush()
}
while ([DateTime]::UtcNow -lt $deadline) {
    if ($Mode -eq "progress") {
        [Console]::Out.Write(".")
        [Console]::Out.Flush()
        [IO.File]::AppendAllText($ArtifactPath, ".", [Text.UTF8Encoding]::new($false))
    }
    Start-Sleep -Milliseconds $IntervalMilliseconds
}
if ($Mode -eq "progress") {
    [Console]::Out.WriteLine("complete")
    [Console]::Out.Flush()
}

