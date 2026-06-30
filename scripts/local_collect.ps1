# 로컬 전력수급 수집 + 자동 커밋/푸시 (Windows 작업 스케줄러용 워커)
#
# 배경: KPX OpenAPI(openapi.kpx.or.kr)는 한국 IP에서만 응답하므로
#       GitHub Actions(해외 IP) 자동수집이 불가 → 수집은 로컬 PC(한국)에서 수행.
# 동작: ① pull --rebase(원격 최신 DB 확보) → ② collect_once(원격 DB에 today 행 upsert)
#       → ③ DB 변경 시에만 커밋·push.
#       반드시 "pull 먼저, 수집 나중" 순서여야 바이너리 DB 충돌이 안 남
#       (항상 원격 DB를 베이스로 새 행만 누적 → push는 fast-forward).
#
# 수동 실행:  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\local_collect.ps1

# 리포지토리 루트 = 이 스크립트의 상위(scripts)의 상위
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

# 로그 준비
$LogDir = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "local_collect.log"
function Log($msg) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

# 파이썬 (프로젝트 .venv 우선, 없으면 시스템 python)
$Py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }

$branch = (& git rev-parse --abbrev-ref HEAD).Trim()
Log "=== 수집 시작 (py=$Py, branch=$branch) ==="

# 1) 원격 최신 반영 (다른 세션/클라우드가 push한 DB·리포트). --autostash로 로컬 변경 임시 보관.
& git pull --rebase --autostash origin $branch 2>&1 | ForEach-Object { Log $_ }
if ($LASTEXITCODE -ne 0) {
    Log "pull 실패 — 이번 회차 중단(다음 실행 때 재시도)"
    exit 1
}

# 2) 수집 — 위에서 받은 원격 DB에 today 행을 idempotent upsert
& $Py -m scripts.collect_once 2>&1 | ForEach-Object { Log $_ }
$collectExit = $LASTEXITCODE
if ($collectExit -ne 0) {
    Log "수집 실패(exit=$collectExit) — 커밋/푸시 생략"
    exit $collectExit
}

# 3) DB 변경분만 스테이징 (.gitignore에서 *.db는 추적 대상)
$DbPath = "src/storage/data.db"
& git add $DbPath
& git diff --cached --quiet -- $DbPath
$changed = ($LASTEXITCODE -ne 0)
if (-not $changed) {
    Log "DB 변경 없음 — 커밋 생략"
    exit 0
}

# 4) 커밋 → push (원격 DB 기반이라 fast-forward, 충돌 없음)
$stamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ss"
& git commit -m "auto(collect): local snapshot $stamp" 2>&1 | ForEach-Object { Log $_ }
& git push origin $branch 2>&1 | ForEach-Object { Log $_ }
if ($LASTEXITCODE -ne 0) {
    Log "푸시 실패 — 다음 실행 때 재시도"
    exit 1
}

Log "=== 완료 (branch=$branch) ==="
