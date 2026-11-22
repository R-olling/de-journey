<#
.SYNOPSIS
    注册 / 更新 / 删除 weather-pipeline 的每日计划任务。

.DESCRIPTION
    注册的是 week4\run_daily.py（不是 week3\run.py）。
    默认每天 07:00 跑，窗口 = 昨天往前 7 天。

.EXAMPLE
    .\register_task.ps1                 # 注册（已存在则覆盖）
    .\register_task.ps1 -Time 07:30
    .\register_task.ps1 -RunNow         # 注册后立刻触发一次，用来验证"真的会跑"
    .\register_task.ps1 -Remove         # 删掉任务
#>
param(
    [string]$TaskName = "de-journey-weather-daily",
    [string]$Time = "07:00",
    [switch]$RunNow,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "removed: $TaskName"
    return
}

# $PSScriptRoot = D:\code\de-journey\week4\scripts  -> 仓库根要退两级
$Repo   = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $Repo ".venv\Scripts\python.exe"
$Script = Join-Path $Repo "week4\run_daily.py"

foreach ($p in @($Python, $Script)) {
    if (-not (Test-Path $p)) { throw "not found: $p" }
}

# 为什么用绝对路径 + WorkingDirectory：
# 计划任务的默认工作目录是 C:\Windows\System32，相对路径一进任务就崩。
# 为什么不用 `python`：任务进程的 PATH 和终端不一样，venv 不在里面。
$Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Script`"" -WorkingDirectory $Repo
$Trigger = New-ScheduledTaskTrigger -Daily -At $Time
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Settings $Settings -Force `
    -Description "weather-pipeline daily incremental (week4/run_daily.py)" | Out-Null

$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
[PSCustomObject]@{
    TaskName    = $task.TaskName
    State       = $task.State
    NextRunTime = $info.NextRunTime
    LastRunTime = $info.LastRunTime
    LastResult  = ("0x{0:X} ({1})" -f $info.LastTaskResult, $info.LastTaskResult)
    Execute     = $Python
    Arguments   = "`"$Script`""
    WorkingDir  = $Repo
} | Format-List

if ($RunNow) {
    Write-Host "Start-ScheduledTask $TaskName ..." -ForegroundColor Yellow
    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 20
    $i2 = Get-ScheduledTaskInfo -TaskName $TaskName
    "LastRunTime = $($i2.LastRunTime)"
    ("LastResult  = 0x{0:X}" -f $i2.LastTaskResult)

    $logs = Join-Path $Repo "week4\logs"
    $latest = Get-ChildItem $logs -Filter "daily-*.log" |
              Sort-Object LastWriteTime -Descending |
              Select-Object -First 1
    if ($latest) { "latest log  = " + $latest.FullName }
}
