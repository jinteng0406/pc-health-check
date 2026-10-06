"""當機與錯誤紀錄的 PowerShell 查詢（Windows 事件紀錄，最近 N 天）。

不依賴事件訊息文字（會因語系不同），只用提供者、事件 ID 與 EventData 欄位。
"""

PS_TEMPLATE = r"""
$since = (Get-Date).AddDays(-__DAYS__)
function Get-Ev($log, $provider, $ids) {
    try {
        Get-WinEvent -FilterHashtable @{ LogName = $log; ProviderName = $provider; Id = $ids; StartTime = $since } `
            -MaxEvents 200 -ErrorAction Stop
    } catch { @() }
}
function Get-Data($ev) {
    $d = @{}
    foreach ($x in ([xml]$ev.ToXml()).Event.EventData.Data) { if ($x.Name) { $d[$x.Name] = $x.'#text' } }
    $d
}
function Pack($events, [switch]$WithData) {
    @($events | ForEach-Object {
        $o = [ordered]@{ Time = $_.TimeCreated.ToString('s'); Id = $_.Id; Provider = $_.ProviderName }
        if ($WithData) { $o.Data = Get-Data $_ }
        [pscustomobject]$o
    })
}
$appCrashes = @(Get-Ev 'Application' 'Application Error' @(1000) | ForEach-Object {
    [pscustomobject]@{ Time = $_.TimeCreated.ToString('s'); App = "$($_.Properties[0].Value)" }
})
$dumps = @()
if (Test-Path "$env:SystemRoot\Minidump") {
    $dumps = @(Get-ChildItem "$env:SystemRoot\Minidump" -Filter *.dmp -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -ge $since } | ForEach-Object { $_.LastWriteTime.ToString('s') })
}
[pscustomobject]@{
    Days           = __DAYS__
    Now            = (Get-Date).ToString('s')
    KernelPower    = Pack (Get-Ev 'System' 'Microsoft-Windows-Kernel-Power' @(41)) -WithData
    BugChecks      = Pack (Get-Ev 'System' 'Microsoft-Windows-WER-SystemErrorReporting' @(1001)) -WithData
    UnexpectedOff  = Pack (Get-Ev 'System' 'EventLog' @(6008))
    Whea           = Pack (Get-Ev 'System' 'Microsoft-Windows-WHEA-Logger' @(1, 17, 18, 19, 20, 46, 47))
    DisplayTdr     = Pack (Get-Ev 'System' 'Display' @(4101))
    DiskErrors     = Pack (Get-Ev 'System' @('disk', 'Disk') @(7, 11, 51, 153))
    NtfsErrors     = Pack (Get-Ev 'System' 'Ntfs' @(55, 98))
    NvmeErrors     = Pack (Get-Ev 'System' 'stornvme' @(11, 129))
    AppCrashes     = $appCrashes
    Minidumps      = $dumps
} | ConvertTo-Json -Depth 5 -Compress
"""


def script(days: int) -> str:
    return PS_TEMPLATE.replace("__DAYS__", str(int(days)))
