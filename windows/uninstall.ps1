# Снятие нейропрофориентации с ноутбука: останавливает автозапуск и программу.
# Записи визитов остаются на месте, папку можно удалить руками.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$TaskName = "BHS Neuro"
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
$Shortcut = Join-Path ([Environment]::GetFolderPath("Startup")) "BHS Neuro.lnk"
if (Test-Path $Shortcut) { Remove-Item $Shortcut -Force }
# сначала обёртку, потом сам мост: иначе обёртка поднимет его обратно
Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and ($_.CommandLine -like "*run-bridge.ps1*" -or $_.CommandLine -like "*bridge.main*")
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Write-Host "Автозапуск снят, программа остановлена."
Write-Host "Записи визитов остались в папке data, папку можно удалить вручную."
Read-Host "Нажмите Enter, чтобы закрыть" | Out-Null
