"""硬碟與磁碟區的 PowerShell 查詢（Windows 內建 Storage 模組）。"""

PS_SCRIPT = r"""
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
$disks = Get-PhysicalDisk | ForEach-Object {
    $r = $null
    try { $r = $_ | Get-StorageReliabilityCounter -ErrorAction Stop } catch {}
    [pscustomobject]@{
        DeviceId          = "$($_.DeviceId)"
        FriendlyName      = $_.FriendlyName
        MediaType         = "$($_.MediaType)"
        BusType           = "$($_.BusType)"
        Size              = $_.Size
        HealthStatus      = "$($_.HealthStatus)"
        OperationalStatus = (@($_.OperationalStatus) | ForEach-Object { "$_" }) -join ', '
        Reliability       = if ($r) { [pscustomobject]@{
            Temperature            = $r.Temperature
            TemperatureMax         = $r.TemperatureMax
            Wear                   = $r.Wear
            PowerOnHours           = $r.PowerOnHours
            ReadErrorsUncorrected  = $r.ReadErrorsUncorrected
            WriteErrorsUncorrected = $r.WriteErrorsUncorrected
        } } else { $null }
    }
}
$vols = Get-Volume | Where-Object { $_.DriveLetter -and "$($_.DriveType)" -eq 'Fixed' } | ForEach-Object {
    [pscustomobject]@{
        DriveLetter   = "$($_.DriveLetter)"
        Label         = $_.FileSystemLabel
        FileSystem    = $_.FileSystem
        Size          = $_.Size
        SizeRemaining = $_.SizeRemaining
        HealthStatus  = "$($_.HealthStatus)"
    }
}
[pscustomobject]@{ Admin = $admin; Disks = @($disks); Volumes = @($vols) } | ConvertTo-Json -Depth 4 -Compress
"""
