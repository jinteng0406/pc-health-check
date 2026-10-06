# 打包成資料夾版 exe（本機與 GitHub Actions 共用）
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python -m PyInstaller run.py `
    --name PCHealthCheck `
    --onedir --windowed --noconfirm --clean `
    --paths src `
    --add-data "fixtures;fixtures" `
    --exclude-module PySide6.QtWebEngineCore `
    --exclude-module PySide6.Qt3DCore `
    --exclude-module PySide6.QtMultimedia `
    --exclude-module PySide6.QtQuick `
    --exclude-module PySide6.QtQml
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失敗" }
