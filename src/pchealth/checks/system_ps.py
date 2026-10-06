"""這台電腦總覽的 PowerShell 查詢（日期一律先轉成字串，避免 ConvertTo-Json 的格式問題）。"""

PS_SCRIPT = r"""
$cs   = Get-CimInstance Win32_ComputerSystem
$bb   = Get-CimInstance Win32_BaseBoard
$bios = Get-CimInstance Win32_BIOS
$os   = Get-CimInstance Win32_OperatingSystem
$cpu  = Get-CimInstance Win32_Processor | Select-Object -First 1
$gpus = Get-CimInstance Win32_VideoController | ForEach-Object {
    [pscustomobject]@{
        Name          = $_.Name
        DriverVersion = $_.DriverVersion
        DriverDate    = if ($_.DriverDate) { $_.DriverDate.ToString('yyyy-MM-dd') } else { $null }
    }
}
[pscustomobject]@{
    Manufacturer      = $cs.Manufacturer
    Model             = $cs.Model
    MemoryBytes       = $cs.TotalPhysicalMemory
    BoardManufacturer = $bb.Manufacturer
    BoardProduct      = $bb.Product
    BiosVersion       = $bios.SMBIOSBIOSVersion
    BiosDate          = if ($bios.ReleaseDate) { $bios.ReleaseDate.ToString('yyyy-MM-dd') } else { $null }
    OsCaption         = $os.Caption
    OsVersion         = $os.Version
    OsBuild           = $os.BuildNumber
    LastBoot          = $os.LastBootUpTime.ToString('s')
    Now               = (Get-Date).ToString('s')
    Cpu               = "$($cpu.Name)".Trim()
    Gpus              = @($gpus)
} | ConvertTo-Json -Depth 3 -Compress
"""
