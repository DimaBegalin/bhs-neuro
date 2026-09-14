# Установка нейропрофориентации BHS на ноутбук с Windows.
# Ставит всё нужное, прописывает автозапуск и больше не требует внимания.
# Запускается двойным щелчком по «Установить (Windows).bat» рядом с папкой.
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$AppDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $AppDir
$TaskName = "BHS Neuro"

function Pause-Exit($code) {
    Write-Host ""
    Read-Host "Нажмите Enter, чтобы закрыть" | Out-Null
    exit $code
}

$Site = "https://bhs-neuro.vercel.app"
if (Test-Path ".env") {
    $line = Get-Content ".env" -Encoding UTF8 | Where-Object { $_ -match '^TEST_URL=' } | Select-Object -First 1
    if ($line) { $Site = ($line -split '=', 2)[1].Trim() }
}

Write-Host "=========================================="
Write-Host "  Нейропрофориентация BHS: установка"
Write-Host "=========================================="
Write-Host ""

# --- 1. Python. Ставим свой, чтобы не зависеть от того, что уже стоит ---
$Uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
if (-not (Test-Path $Uv)) {
    $found = Get-Command uv -ErrorAction SilentlyContinue
    if ($found) {
        $Uv = $found.Source
    } else {
        Write-Host "Ставлю служебные файлы, это займёт минуту..."
        try {
            Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression | Out-Null
        } catch { }
        $Uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
    }
}
if (-not (Test-Path $Uv)) {
    Write-Host "ОШИБКА: не получилось поставить служебные файлы."
    Write-Host "Проверьте интернет и запустите этот файл ещё раз."
    Pause-Exit 1
}

Write-Host "Готовлю программу..."
& $Uv python install 3.12 2>&1 | Out-Null
& $Uv venv --python 3.12 .venv 2>&1 | Out-Null
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "ОШИБКА: не удалось подготовить окружение."
    Pause-Exit 1
}
$env:VIRTUAL_ENV = Join-Path $AppDir ".venv"
& $Uv pip install --quiet -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "ОШИБКА: не встали зависимости. Проверьте интернет."
    Pause-Exit 1
}

# Имя менеджера здесь не спрашиваем: он называет себя при входе на сайте,
# и программа берёт его оттуда.

# --- 2. Автозапуск. Программа поднимается сама при входе в систему ---
New-Item -ItemType Directory -Force -Path "logs" | Out-Null
$Runner = Join-Path $AppDir "windows\run-bridge.ps1"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Runner`"" `
    -WorkingDirectory $AppDir
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
# без ExecutionTimeLimit ноль планировщик убивает задачу через трое суток,
# и в понедельник мост оказывался бы мёртвым
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings `
        -Description "Мост к ободку нейропрофориентации BHS" -Force | Out-Null
    Start-ScheduledTask -TaskName $TaskName
} catch {
    Write-Host "Автозапуск через планировщик не прописался: $($_.Exception.Message)"
    Write-Host "Запускаю программу вручную и кладу ярлык в автозагрузку."
    $Startup = [Environment]::GetFolderPath("Startup")
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut((Join-Path $Startup "BHS Neuro.lnk"))
    $Shortcut.TargetPath = "powershell.exe"
    $Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Runner`""
    $Shortcut.WorkingDirectory = $AppDir
    $Shortcut.Save()
    Start-Process powershell.exe -WindowStyle Hidden -WorkingDirectory $AppDir `
        -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$Runner`""
}

Write-Host ""
Write-Host "Проверяю, что программа отвечает (до минуты на первый запуск)..."
$Ok = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    try {
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8765/status | Out-Null
        $Ok = $true; break
    } catch { }
}

Write-Host ""
if ($Ok) {
    Write-Host "=========================================="
    Write-Host "  ГОТОВО. Программа работает и будет"
    Write-Host "  запускаться сама при включении ноутбука."
    Write-Host "=========================================="
    Write-Host ""
    Write-Host "Дальше, перед первым ребёнком:"
    Write-Host "  1. Включите ободок и добавьте его в Windows:"
    Write-Host "     Параметры, Bluetooth и устройства, Добавить устройство."
    Write-Host "  2. Приложение Mind Tracker на этом ноутбуке должно быть ЗАКРЫТО:"
    Write-Host "     на Windows прибор держит только одна программа, и это наша."
    Write-Host "  3. Откройте в Chrome или Edge: $Site"
    Write-Host "     Войдите по почте и паролю, которые дала школа."
} else {
    Write-Host "Программа установлена, но пока не отвечает."
    Write-Host "Перезагрузите ноутбук и откройте сайт теста."
    Write-Host "Журнал: $AppDir\logs\bridge.log"
}
Pause-Exit 0
