# 打包成資料夾版 exe（本機與 GitHub Actions 共用）
# 若 bin\smartctl.exe 存在（CI 會從 smartmontools 複製過來），會一起打包
# 不設 ErrorActionPreference=Stop：PyInstaller 把進度寫到 stderr，Windows PowerShell 5.1 會誤判成錯誤。
# 成敗以 PyInstaller 的結束代碼為準（見最後一行）。
Set-Location $PSScriptRoot

$extra = @("--add-data", "THIRD_PARTY_NOTICES.md;.")
if (Test-Path "bin\smartctl.exe") {
    $extra += @("--add-binary", "bin\smartctl.exe;bin")
    if (Test-Path "bin\COPYING.txt") { $extra += @("--add-data", "bin\COPYING.txt;bin") }
} else {
    Write-Warning "找不到 bin\smartctl.exe，這次打包不含 smartctl"
}
# .NET 組件當資料檔打包（不是原生 DLL，不需要 PyInstaller 分析相依）
if (Test-Path "bin\lhm\LibreHardwareMonitorLib.dll") {
    $extra += @("--add-data", "bin\lhm;bin\lhm")
} else {
    Write-Warning "找不到 bin\lhm，這次打包不含 CPU／主機板感測器元件"
}

python -m PyInstaller run.py `
    --name PCHealthCheck `
    --onedir --windowed --noconfirm --clean `
    --paths src `
    --add-data "fixtures;fixtures" `
    @extra `
    --exclude-module PySide6.QtWebEngineCore `
    --exclude-module PySide6.Qt3DCore `
    --exclude-module PySide6.QtMultimedia `
    --exclude-module PySide6.QtQuick `
    --exclude-module PySide6.QtQml
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失敗" }
