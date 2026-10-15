# HTTP CRUD smoke against the Docker-published generated backend.
# Generated JavaScript executes only inside the container.

param(
  [string]$BaseUrl = "http://127.0.0.1:3001/api/v1/tasks",
  [string]$OutFile = ""
)

$ErrorActionPreference = "Stop"
$results = @()

function Record($name, $status, $detail) {
  $script:results += [ordered]@{ test = $name; status = $status; detail = $detail }
}

try {
  $list0 = Invoke-RestMethod -Method Get -Uri $BaseUrl
  if ($list0 -is [System.Array]) { Record "list_initial" "PASS" "count=$($list0.Count)" } else { Record "list_initial" "FAIL" "unexpected payload" }

  $created = Invoke-RestMethod -Method Post -Uri $BaseUrl -ContentType "application/json" -Body '{"title":"PP1 smoke task"}'
  if ($created.title -eq "PP1 smoke task" -and $created.id) { Record "create" "PASS" "id=$($created.id)" } else { Record "create" "FAIL" "bad body" }
  $id = $created.id

  $list1 = Invoke-RestMethod -Method Get -Uri $BaseUrl
  if (@($list1).Count -ge 1) { Record "list_after_create" "PASS" "count=$(@($list1).Count)" } else { Record "list_after_create" "FAIL" "empty" }

  $updated = Invoke-RestMethod -Method Patch -Uri "$BaseUrl/$id" -ContentType "application/json" -Body '{"completed":true}'
  if ($updated.completed -eq $true) { Record "update" "PASS" "completed=true" } else { Record "update" "FAIL" "completed=$($updated.completed)" }

  $delete = Invoke-WebRequest -Method Delete -Uri "$BaseUrl/$id" -UseBasicParsing
  if ($delete.StatusCode -eq 204) { Record "delete" "PASS" "HTTP 204" } else { Record "delete" "FAIL" "status=$($delete.StatusCode)" }

  try {
    Invoke-RestMethod -Method Patch -Uri "$BaseUrl/00000000-0000-4000-8000-000000000099" -ContentType "application/json" -Body '{"completed":true}'
    Record "missing_task_404" "FAIL" "expected HTTP error"
  } catch {
    $response = $_.Exception.Response
    if ($response -and [int]$response.StatusCode -eq 404) { Record "missing_task_404" "PASS" "HTTP 404" } else { Record "missing_task_404" "FAIL" $_.Exception.Message }
  }
} catch {
  Record "setup" "FAIL" $_.Exception.Message
}

$payload = @{
  base_url = $BaseUrl
  tested_at_utc = (Get-Date).ToUniversalTime().ToString("o")
  results = $results
}
$json = $payload | ConvertTo-Json -Depth 5
if ($OutFile) { $json | Set-Content -LiteralPath $OutFile -Encoding utf8 }
$json
if ($results | Where-Object { $_.status -eq "FAIL" }) { exit 1 }
