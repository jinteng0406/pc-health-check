# 打包成資料夾版 exe（本機與 GitHub Actions 共用）
# 若 bin\smartctl.exe 存在（CI 會從 smartmontools 複製過來），會一起打包
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$extra = @("--add-data", "THIRD_PARTY_NOTICES.md;.")
if (Test-Path "bin\smartctl.exe") {
    $extra += @("--add-binary", "bin\smartctl.exe;bin")
    if (Test-Path "bin\COPYING.txt") { $extra += @("--add-data", "bin\COPYING.txt;bin") }
} else {
    Write-Warning "找不到 bin\smartctl.exe，這次打包不含 smartctl"
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
