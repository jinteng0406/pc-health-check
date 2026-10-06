"""開機啟動項與效能的 PowerShell 查詢。"""

PS_SCRIPT = r"""
# 工作管理員停用的啟動項記錄在 StartupApproved：第一個位元組為偶數＝啟用、奇數＝停用
function Get-Disabled {
    $names = @{}
    foreach ($root in 'HKCU:', 'HKLM:') {
        foreach ($sub in 'Run', 'Run32', 'StartupFolder') {
            $key = "$root\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\$sub"
            if (Test-Path $key) {
                $props = Get-ItemProperty $key
                foreach ($p in $props.PSObject.Properties) {
                    if ($p.Value -is [byte[]] -and $p.Value.Length -gt 0 -and ($p.Value[0] % 2) -eq 1) {
                        $names[$p.Name.ToLower()] = $true
                    }
                }
            }
        }
    }
    $names
}
$disabled = Get-Disabled
$startup = @(Get-CimInstance Win32_StartupCommand | ForEach-Object {
    $off = $disabled.ContainsKey("$($_.Name)".ToLower()) -or ($_.Location -like '*Startup*' -and $disabled.ContainsKey("$($_.Name).lnk".ToLower()))
    # HKU\S-1-5-21-…（帳號 SID）換成 HKCU，避免匯出資料含有可識別帳號的資訊
    [pscustomobject]@{ Name = $_.Name; Location = ("$($_.Location)" -replace '^HKU\\S-1-5-[\d-]+', 'HKCU'); Enabled = -not $off }
})
$os = Get-CimInstance Win32_OperatingSystem
$top = @(Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 5 |
    ForEach-Object { [pscustomobject]@{ Name = $_.ProcessName; MB = [int]($_.WorkingSet64 / 1MB) } })
$scheme = (powercfg /getactivescheme) -join ' '
[pscustomobject]@{
    Startup       = $startup
    TotalMemoryKB = [int64]$os.TotalVisibleMemorySize
    FreeMemoryKB  = [int64]$os.FreePhysicalMemory
    TopProcesses  = $top
    PowerScheme   = if ($scheme -match '([0-9a-fA-F-]{36})') { $Matches[1].ToLower() } else { $null }
} | ConvertTo-Json -Depth 4 -Compress
"""
