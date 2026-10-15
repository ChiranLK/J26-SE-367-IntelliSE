# Verify and start one generated workspace inside a disposable Docker container.
# This script never runs npm or generated JavaScript on the Windows host.

param(
  [Parameter(Mandatory = $true)]
  [string]$WorkspaceRelativePath,
  [Parameter(Mandatory = $true)]
  [string]$ExecutionId,
  [string]$ProjectSuffix = "",
  [switch]$RunApiSmoke,
  [switch]$Detached
)

$ErrorActionPreference = "Stop"
$PreviewRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ComponentRoot = Split-Path -Parent $PreviewRoot
Set-Location $ComponentRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker CLI not found."
}
docker ps 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
  throw "Docker daemon is not running. Start Docker Desktop and retry."
}

$env:GENERATED_WORKSPACE_ROOT = "generated-workspaces/runtime-preview"
$metaJson = & .\.venv\Scripts\python.exe runtime-preview\verify_copy.py $WorkspaceRelativePath --execution-id $ExecutionId
if ($LASTEXITCODE -ne 0) { throw "verify_copy failed" }
$meta = $metaJson | ConvertFrom-Json
$workspaceHost = Join-Path $ComponentRoot ($meta.execution_directory -replace "/", "\")
$executionDir = Split-Path -Parent $workspaceHost
$logsDir = Join-Path $executionDir "logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

$project = "c3-preview-$($meta.generation_run_id.Substring(0, 8))"
if ($ProjectSuffix) { $project = "$project-$ProjectSuffix" }

$env:WORKSPACE_HOST_PATH = $workspaceHost
Set-Location $PreviewRoot

Write-Host "Building isolated preview image..."
docker compose -f compose.preview.yml build | Tee-Object -FilePath (Join-Path $logsDir "docker-build.log")

$upArgs = @("-f", "compose.preview.yml", "--project-name", $project, "up")
if ($Detached) { $upArgs += "-d" } else { $upArgs += "--abort-on-container-exit" }

Write-Host "Starting isolated preview for run $($meta.generation_run_id)"
Write-Host "  Frontend: http://127.0.0.1:5180"
Write-Host "  Backend:  http://127.0.0.1:3001/api/v1/tasks"
Write-Host "  Mode:     $($meta.generation_mode)"
Write-Host "  Digest:   $($meta.artifact_digest_sha256)"

function Wait-BackendReady {
  param([string]$Url, [int]$TimeoutSec = 180)
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      Invoke-RestMethod -Method Get -Uri $Url -TimeoutSec 3 | Out-Null
      return $true
    } catch {
      Start-Sleep -Seconds 2
    }
  }
  return $false
}

if ($Detached) {
  docker compose @upArgs | Tee-Object -FilePath (Join-Path $logsDir "docker-up.log")
  if (-not (Wait-BackendReady -Url "http://127.0.0.1:3001/api/v1/tasks")) {
    docker compose -f compose.preview.yml --project-name $project logs --tail 80 | Tee-Object -FilePath (Join-Path $logsDir "docker-logs-on-timeout.log")
    throw "Backend did not become ready. See $logsDir"
  }
  if ($RunApiSmoke) {
    & (Join-Path $PreviewRoot "crud-smoke.ps1") -OutFile (Join-Path $executionDir "api-smoke.json")
  }
  Write-Host "Container running. Stop with: docker compose -f runtime-preview/compose.preview.yml --project-name $project down"
} else {
  docker compose @upArgs 2>&1 | Tee-Object -FilePath (Join-Path $logsDir "docker-up.log")
}

Set-Location $ComponentRoot
$meta | Add-Member -NotePropertyName preview_urls -NotePropertyValue @{
  frontend = "http://127.0.0.1:5180"
  backend = "http://127.0.0.1:3001/api/v1/tasks"
} -Force
$meta | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $executionDir "preview-meta.json") -Encoding utf8
