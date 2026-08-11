param(
    [Parameter(Mandatory = $true)][string]$OutputDir
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
$output = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $output) { throw "Phase 6DW inventory refuses output reuse: $output" }
New-Item -ItemType Directory -Path $output | Out-Null
$dxdiagPath = Join-Path $output "dxdiag-sensitive-local.txt"
$reportPath = Join-Path $output "inventory.json"

Add-Type @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class Phase6dwDisplayInventory {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct DISPLAY_DEVICE {
        public int cb;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string DeviceName;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string DeviceString;
        public int StateFlags;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string DeviceID;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string DeviceKey;
    }
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern bool EnumDisplayDevices(string lpDevice, uint iDevNum, ref DISPLAY_DEVICE displayDevice, uint flags);
    public static List<string[]> GetRows() {
        var rows = new List<string[]>();
        for (uint i = 0; ; ++i) {
            var adapter = new DISPLAY_DEVICE(); adapter.cb = Marshal.SizeOf(adapter);
            if (!EnumDisplayDevices(null, i, ref adapter, 0)) break;
            bool hadMonitor = false;
            for (uint j = 0; ; ++j) {
                var monitor = new DISPLAY_DEVICE(); monitor.cb = Marshal.SizeOf(monitor);
                if (!EnumDisplayDevices(adapter.DeviceName, j, ref monitor, 0)) break;
                hadMonitor = true;
                rows.Add(new [] { adapter.DeviceName, adapter.DeviceString, adapter.StateFlags.ToString(), adapter.DeviceID, monitor.DeviceName, monitor.DeviceString, monitor.StateFlags.ToString(), monitor.DeviceID });
            }
            if (!hadMonitor) rows.Add(new [] { adapter.DeviceName, adapter.DeviceString, adapter.StateFlags.ToString(), adapter.DeviceID, "", "", "0", "" });
        }
        return rows;
    }
}
'@

function Convert-NvidiaGpuRows {
    $rows = @()
    $text = & nvidia-smi --query-gpu=index,uuid,name,pci.bus_id,pci.device_id,driver_version,display_active,display_mode,memory.total,memory.used,utilization.gpu,power.draw,power.limit,temperature.gpu --format=csv,noheader,nounits
    foreach ($line in @($text)) {
        $v = @($line -split ',\s*')
        if ($v.Count -ne 14) { continue }
        $rows += [ordered]@{
            index=$v[0]; uuid=$v[1]; name=$v[2]; pci_bus_id=$v[3]; pci_device_id=$v[4]
            driver_version=$v[5]; display_active=$v[6]; display_mode=$v[7]
            memory_total_mib=$v[8]; memory_used_mib=$v[9]; utilization_percent=$v[10]
            power_w=$v[11]; power_limit_w=$v[12]; temperature_c=$v[13]
        }
    }
    return @($rows)
}

$videoControllers = @(Get-CimInstance Win32_VideoController | ForEach-Object {
    [ordered]@{
        name=$_.Name; device_id=$_.DeviceID; pnp_device_id=$_.PNPDeviceID
        driver_version=$_.DriverVersion; driver_date=$_.DriverDate.ToString("o")
        current_width=$_.CurrentHorizontalResolution; current_height=$_.CurrentVerticalResolution
        current_refresh_hz=$_.CurrentRefreshRate; status=$_.Status
    }
})
$pnp = @()
foreach ($controller in $videoControllers) {
    $properties = @{}
    foreach ($item in @(Get-PnpDeviceProperty -InstanceId $controller.pnp_device_id)) {
        if ($item.KeyName -in @(
            "DEVPKEY_Device_LocationInfo",
            "DEVPKEY_Device_InstallDate",
            "DEVPKEY_Device_FirstInstallDate",
            "DEVPKEY_Device_DriverDate",
            "DEVPKEY_Device_DriverVersion"
        )) { $properties[$item.KeyName] = [string]$item.Data }
    }
    $pnp += [ordered]@{ name=$controller.name; pnp_device_id=$controller.pnp_device_id; properties=$properties }
}
$displays = @([Phase6dwDisplayInventory]::GetRows() | ForEach-Object {
    [ordered]@{
        display_name=$_[0]; adapter_name=$_[1]; adapter_state_flags=[int]$_[2]; adapter_pnp_id=$_[3]
        monitor_name=$_[4]; monitor_description=$_[5]; monitor_state_flags=[int]$_[6]; monitor_pnp_id=$_[7]
    }
})

$os = Get-CimInstance Win32_OperatingSystem
$dxdiag = Start-Process -FilePath "$env:SystemRoot\System32\dxdiag.exe" -ArgumentList @("/whql:off", "/t", $dxdiagPath) -PassThru -WindowStyle Hidden
if (-not $dxdiag.WaitForExit(120000)) { Stop-Process -Id $dxdiag.Id -Force; throw "DXDiag timed out" }
$dxdiagText = Get-Content -Raw -Encoding Unicode $dxdiagPath
if (-not $dxdiagText -or $dxdiagText -notmatch "DirectX") { $dxdiagText = Get-Content -Raw -Encoding UTF8 $dxdiagPath }
$dxdiagSummary = [ordered]@{
    operating_system = @([regex]::Matches($dxdiagText, '(?m)^\s*Operating System:\s*(.+)$') | ForEach-Object {$_.Groups[1].Value.Trim()})
    directx_version = @([regex]::Matches($dxdiagText, '(?m)^\s*DirectX Version:\s*(.+)$') | ForEach-Object {$_.Groups[1].Value.Trim()})
    card_names = @([regex]::Matches($dxdiagText, '(?m)^\s*Card name:\s*(.+)$') | ForEach-Object {$_.Groups[1].Value.Trim()})
    driver_models = @([regex]::Matches($dxdiagText, '(?m)^\s*Driver Model:\s*(.+)$') | ForEach-Object {$_.Groups[1].Value.Trim()})
    feature_levels = @([regex]::Matches($dxdiagText, '(?m)^\s*Feature Levels:\s*(.+)$') | ForEach-Object {$_.Groups[1].Value.Trim()})
}

$artifactTimeline = @()
foreach ($phase in @(
    [ordered]@{name="6DT"; path="artifacts\phase6dt-reference-audit-2"},
    [ordered]@{name="6DU"; path="artifacts\phase6du-static-cylinder-1"},
    [ordered]@{name="6DV"; path="artifacts\phase6dv-stage-open-classification-1"}
)) {
    $path = Join-Path $root $phase.path
    $files = @(Get-ChildItem -LiteralPath $path -Recurse -File -ErrorAction SilentlyContinue)
    $artifactTimeline += [ordered]@{
        phase=$phase.name; path=$phase.path; file_count=$files.Count
        earliest_local=if($files.Count){($files | Measure-Object LastWriteTime -Minimum).Minimum.ToString("o")}else{$null}
        latest_local=if($files.Count){($files | Measure-Object LastWriteTime -Maximum).Maximum.ToString("o")}else{$null}
    }
}

$processLines = @(& nvidia-smi)
$report = [ordered]@{
    schema="campfire.phase6dw.gpu-inventory.v1"
    phase="phase6dw"
    timestamp_local=(Get-Date).ToString("o")
    os=[ordered]@{caption=$os.Caption; version=$os.Version; build=$os.BuildNumber; architecture=$os.OSArchitecture; last_boot_local=$os.LastBootUpTime.ToString("o")}
    nvidia_gpus=@(Convert-NvidiaGpuRows)
    windows_video_controllers=$videoControllers
    pnp_devices=$pnp
    display_paths=$displays
    dxdiag_summary=$dxdiagSummary
    artifact_timeline=$artifactTimeline
    nvidia_smi_process_listing_local_only=$processLines
    sensitive_local_files=@("dxdiag-sensitive-local.txt", "inventory.json process listing")
}
[IO.File]::WriteAllText($reportPath, ($report | ConvertTo-Json -Depth 16) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Host "Phase 6DW GPU inventory complete: $reportPath"
