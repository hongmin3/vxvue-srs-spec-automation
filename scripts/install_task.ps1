<#
.SYNOPSIS
    VXvue/License Manager SRS 사양서 자동화를 Windows Task Scheduler에 등록한다.

.DESCRIPTION
    - 매주 월요일 09:00 실행
    - 예정된 시작을 놓친 경우(PC 꺼짐 등) 다음 로그온/가능 시점에 즉시 실행 (StartWhenAvailable)
    - 동일 작업이 이미 실행 중이면 중복 실행 방지 (MultipleInstances = IgnoreNew)
    - 실패 시 최대 3회, 10분 간격으로 재시도
    - 네트워크 사용 가능할 때만 실행
    - 로그온 여부와 무관하게 실행되도록 S4U 로그온 방식 사용 (비밀번호 저장 불필요)
    - 우선순위를 4(보통)로 지정 - Task Scheduler 기본값 7(낮음)에서는 Chromium 인쇄가
      크게 느려져 PDF 렌더링이 시간제한을 초과하는 것을 실제로 확인했다.

.PARAMETER TaskName
    등록할 작업 이름 (기본값: VXvue_SRS_Spec_Automation)

.PARAMETER PythonExe
    사용할 python.exe 전체 경로 (기본값: PATH에서 자동 탐색)
#>
param(
    [string]$TaskName = "VXvue_SRS_Spec_Automation",
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $PSScriptRoot
Write-Output "프로젝트 경로: $ProjectDir"

if (-not $PythonExe) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "python.exe를 PATH에서 찾을 수 없습니다. -PythonExe 파라미터로 전체 경로를 지정하세요."
    }
    $PythonExe = $cmd.Source
}
Write-Output "Python 경로: $PythonExe"

$action = New-ScheduledTaskAction -Execute $PythonExe -Argument "main.py" -WorkingDirectory $ProjectDir

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 9:00am

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 10) `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -Priority 4

# S4U: 로그온 여부와 무관하게 실행되며, 별도로 비밀번호를 저장하지 않는다.
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Limited

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Output "기존 작업 '$TaskName' 발견 - 갱신을 위해 먼저 제거합니다."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "VXvue/License Manager Polarion SRS 사양서 자동 최신화 및 변경 리포트 생성" | Out-Null

Write-Output "작업 등록 완료: $TaskName"
Write-Output ""
Get-ScheduledTask -TaskName $TaskName | Format-List TaskName, State
Get-ScheduledTaskInfo -TaskName $TaskName | Format-List NextRunTime, LastRunTime, LastTaskResult
