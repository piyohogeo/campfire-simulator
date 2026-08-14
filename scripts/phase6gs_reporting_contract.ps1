Set-StrictMode -Version 3.0

function Get-Phase6gsOptionalString {
    [CmdletBinding()]
    param(
        [AllowNull()][object]$InputObject,
        [Parameter(Mandatory = $true)][string]$PropertyName
    )
    if ($null -eq $InputObject) { return $null }
    $property = $InputObject.PSObject.Properties[$PropertyName]
    if ($null -eq $property) { return $null }
    $value = $property.Value
    if ($null -eq $value) { return $null }
    if ($value -isnot [string]) {
        throw "Phase 6GS optional property '$PropertyName' must be a string or null, got $($value.GetType().FullName)"
    }
    if ([string]::IsNullOrWhiteSpace($value)) { return $null }
    return [string]$value
}

function Write-Phase6gsTerminalState {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][System.Collections.IDictionary]$State,
        [Parameter(Mandatory = $true)][ValidateSet("qualified_no_later_operation_started", "safe_stop")][string]$Status,
        [Parameter(Mandatory = $true)][string]$OperationResult,
        [Parameter(Mandatory = $true)][string]$LifecycleResult,
        [AllowNull()][string]$LastSuccessfulAccessor
    )
    $State.status = $Status
    $State.operation_result = $OperationResult
    $State.lifecycle_result = $LifecycleResult
    $State.last_successful_accessor = $LastSuccessfulAccessor
    $State.terminal = $true
    $State.completed_timestamp_utc = [DateTime]::UtcNow.ToString("o")
    [IO.File]::WriteAllText(
        $Path,
        ($State | ConvertTo-Json -Depth 12) + [Environment]::NewLine,
        [Text.UTF8Encoding]::new($false)
    )
}
