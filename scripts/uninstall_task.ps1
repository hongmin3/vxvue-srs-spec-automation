<#
.SYNOPSIS
    등록된 VXvue SRS 사양서 자동화 Task Scheduler 작업을 제거한다.
#>
param(
    [string]$TaskName = "VXvue_SRS_Spec_Automation"
)

$ErrorActionPreference = "Stop"

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output "작업 제거 완료: $TaskName"
} else {
    Write-Output "작업 '$TaskName'이(가) 존재하지 않습니다."
}
