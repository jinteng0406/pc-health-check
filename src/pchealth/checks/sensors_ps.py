"""CPU／主機板感測器的 PowerShell 查詢。

- BASE_SCRIPT：免驅動的部分（CPU 被韌體限速的事件、PawnIO 是否已安裝），任何電腦都會執行
- LHM_TEMPLATE：只有偵測到 PawnIO 時才執行，載入 LibreHardwareMonitorLib 讀完整感測器
  （在獨立的 PowerShell 程序中執行，出錯也不影響主程式）
"""

BASE_TEMPLATE = r"""
$since = (Get-Date).AddDays(-__DAYS__)
$limits = @()
try {
    $limits = @(Get-WinEvent -FilterHashtable @{ LogName = 'System'; ProviderName = 'Microsoft-Windows-Kernel-Processor-Power';
                                                Id = 37; StartTime = $since } -MaxEvents 500 -ErrorAction Stop | ForEach-Object {
        $d = @{}
        foreach ($x in ([xml]$_.ToXml()).Event.EventData.Data) { if ($x.Name) { $d[$x.Name] = $x.'#text' } }
        [pscustomobject]@{ Time = $_.TimeCreated.ToString('s'); Data = $d }
    })
} catch {}
$pawn = Get-Service -Name 'PawnIO' -ErrorAction SilentlyContinue
[pscustomobject]@{
    Days          = __DAYS__
    FirmwareLimit = $limits
    PawnIO        = if ($pawn) { "$($pawn.Status)" } else { $null }
} | ConvertTo-Json -Depth 4 -Compress
"""

LHM_TEMPLATE = r"""
$ErrorActionPreference = 'Stop'  # 載入失敗要回報錯誤，不能默默回傳 0 個感測器
$dir = '__DIR__'
# 依名稱從 LHM 資料夾載入相依組件（PowerShell 沒有 LHM 的 binding redirect）
[AppDomain]::CurrentDomain.add_AssemblyResolve({
    param($sender, $e)
    $name = (New-Object Reflection.AssemblyName($e.Name)).Name
    $path = Join-Path $dir "$name.dll"
    if (Test-Path $path) { return [Reflection.Assembly]::LoadFrom($path) }
    return $null
})
Add-Type -Path (Join-Path $dir 'LibreHardwareMonitorLib.dll')
$computer = New-Object LibreHardwareMonitor.Hardware.Computer
$computer.IsCpuEnabled = $true
$computer.IsMotherboardEnabled = $true
$computer.Open()
$script:sensors = New-Object System.Collections.ArrayList
$wanted = 'Temperature', 'Fan', 'Voltage', 'Power', 'Load'
function Walk($hw) {
    $hw.Update()
    foreach ($s in $hw.Sensors) {
        if ($wanted -contains "$($s.SensorType)" -and $s.Value -ne $null) {
            [void]$script:sensors.Add([pscustomobject]@{
                Hardware = $hw.Name; HardwareType = "$($hw.HardwareType)"
                Name = $s.Name; Type = "$($s.SensorType)"; Value = [math]::Round([double]$s.Value, 1) })
        }
    }
    foreach ($sub in $hw.SubHardware) { Walk $sub }
}
# 有些感測器第一次 Update 是空值，讀兩次
foreach ($hw in $computer.Hardware) { $hw.Update() }
Start-Sleep -Milliseconds 500
foreach ($hw in $computer.Hardware) { Walk $hw }
$computer.Close()
[pscustomobject]@{ Sensors = @($script:sensors) } | ConvertTo-Json -Depth 4 -Compress
"""


def base_script(days: int) -> str:
    return BASE_TEMPLATE.replace("__DAYS__", str(int(days)))


def lhm_script(lhm_dir: str) -> str:
    return LHM_TEMPLATE.replace("__DIR__", lhm_dir.replace("'", "''"))
