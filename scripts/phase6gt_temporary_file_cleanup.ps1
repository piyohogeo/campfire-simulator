function Invoke-Phase6gtExactTemporaryCleanup {
    param(
        [Parameter(Mandatory = $true)][string]$TemporaryPath,
        [Parameter(Mandatory = $true)][string]$CaseRoot,
        [Parameter(Mandatory = $true)][string]$ExpectedFilename
    )
    $exactPath = [IO.Path]::GetFullPath($TemporaryPath)
    $exactRoot = [IO.Path]::GetFullPath($CaseRoot)
    if ([IO.Path]::GetDirectoryName($exactPath) -ne $exactRoot -or [IO.Path]::GetFileName($exactPath) -ne $ExpectedFilename) {
        throw "Phase 6GT cleanup path is not the exact contracted temporary file"
    }
    $evidence = [ordered]@{
        schema="campfire.phase6gt.temporary-file-parent-cleanup.v1";
        exact_path=$exactPath;existed_after_process=$false;size_before_cleanup_bytes=0;
        removed_by_parent=$false;exists_after_cleanup=$false
    }
    if (Test-Path -LiteralPath $exactPath) {
        if (-not (Test-Path -LiteralPath $exactPath -PathType Leaf)) {
            throw "Phase 6GT cleanup target exists but is not a file"
        }
        $evidence.existed_after_process = $true
        $evidence.size_before_cleanup_bytes = [int64](Get-Item -LiteralPath $exactPath).Length
        Remove-Item -LiteralPath $exactPath -Force
        $evidence.removed_by_parent = $true
    }
    $evidence.exists_after_cleanup = [bool](Test-Path -LiteralPath $exactPath)
    if ($evidence.exists_after_cleanup) { throw "Phase 6GT exact temporary file remained after cleanup" }
    return $evidence
}
