"""Windows 更新與安全性的 PowerShell 查詢。"""

PS_SCRIPT = r"""
$history = @()
try {
    $searcher = (New-Object -ComObject Microsoft.Update.Session).CreateUpdateSearcher()
    $count = $searcher.GetTotalHistoryCount()
    if ($count -gt 0) {
        $history = @($searcher.QueryHistory(0, [Math]::Min($count, 100)) | Where-Object { $_.Operation -eq 1 } |
            ForEach-Object { [pscustomobject]@{
                Date = $_.Date.ToLocalTime().ToString('s'); Title = $_.Title
                Result = [int]$_.ResultCode; HResult = ('0x{0:X8}' -f $_.HResult) } })
    }
} catch {}
$rebootPending = (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired') -or
                 (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending')
$defender = $null
try {
    $s = Get-MpComputerStatus -ErrorAction Stop
    $defender = [pscustomobject]@{
        AMServiceEnabled          = $s.AMServiceEnabled
        AntivirusEnabled          = $s.AntivirusEnabled
        RealTimeProtectionEnabled = $s.RealTimeProtectionEnabled
        SignatureLastUpdated      = if ($s.AntivirusSignatureLastUpdated) { $s.AntivirusSignatureLastUpdated.ToString('s') } else { $null }
        AMRunningMode             = "$($s.AMRunningMode)"
    }
} catch {}
$av = @()
try {
    $av = @(Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct -ErrorAction Stop |
        ForEach-Object { [pscustomobject]@{ Name = $_.displayName; State = [int]$_.productState } })
} catch {}
[pscustomobject]@{
    Now           = (Get-Date).ToString('s')
    History       = $history
    RebootPending = $rebootPending
    Defender      = $defender
    Antivirus     = $av
} | ConvertTo-Json -Depth 4 -Compress
"""
