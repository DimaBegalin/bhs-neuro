# Держит мост живым: упал или вышел сам, через три секунды поднимается снова.
# Это замена KeepAlive у launchd на macOS. Мост сам выходит с кодом 3, когда
# системный Bluetooth в его процессе умер, и рассчитывает на этот перезапуск.
$AppDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $AppDir
$Python = Join-Path $AppDir ".venv\Scripts\python.exe"
$Log = Join-Path $AppDir "logs\bridge.log"
New-Item -ItemType Directory -Force -Path (Join-Path $AppDir "logs") | Out-Null
# кириллица в журнале и в именах файлов: без этого Python на Windows пишет
# в кодировке консоли и ломает буквы
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"

while ($true) {
    # журнал не растёт бесконечно: раз в запуск подрезаем до последних 2 МБ
    if ((Test-Path $Log) -and ((Get-Item $Log).Length -gt 4MB)) {
        $bytes = [System.IO.File]::ReadAllBytes($Log)
        [System.IO.File]::WriteAllBytes($Log, $bytes[($bytes.Length - 2MB)..($bytes.Length - 1)])
    }
    $process = Start-Process -FilePath $Python -ArgumentList "-m", "bridge.main" `
        -WorkingDirectory $AppDir -NoNewWindow -PassThru -Wait `
        -RedirectStandardOutput $Log -RedirectStandardError (Join-Path $AppDir "logs\bridge.err.log")
    Add-Content -Path $Log -Value ("мост вышел с кодом {0}, перезапуск через 3 секунды" -f $process.ExitCode) -Encoding UTF8
    Start-Sleep -Seconds 3
}
