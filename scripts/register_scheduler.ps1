# 전력수급 로컬 수집 작업을 Windows 작업 스케줄러에 등록 (10분 간격, 무기한)
#
# 한 번만 실행하면 됩니다:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\register_scheduler.ps1
#
# 권한 오류가 나면 "관리자 권한 PowerShell"에서 다시 실행하세요.

$TaskName = "PowerGridCollect"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Worker   = Join-Path $RepoRoot "scripts\local_collect.ps1"

if (-not (Test-Path $Worker)) {
    Write-Error "워커 스크립트를 찾을 수 없습니다: $Worker"
    exit 1
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument ("-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"{0}`"" -f $Worker)

# 1분 뒤부터 10분 간격으로 무기한 반복
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 10) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

# PC가 꺼져 있던 시간은 건너뛰고, 켜지면 곧바로 따라잡음. 각 실행 5분 제한.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings `
    -Description "KPX 전력수급 5분 데이터 로컬 수집 후 자동 커밋/푸시" -Force | Out-Null

Write-Host "[OK] 등록 완료: '$TaskName' (10분 간격, 로그인 중 실행)"
Write-Host ""
Write-Host "  상태 확인 : Get-ScheduledTask -TaskName $TaskName"
Write-Host "  즉시 실행 : Start-ScheduledTask -TaskName $TaskName"
Write-Host "  로그 확인 : Get-Content logs\local_collect.log -Tail 20"
Write-Host "  등록 해제 : Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
