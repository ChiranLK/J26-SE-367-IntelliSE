# INTELISE Component 4 - Supervisor Demo Environment Health Check
$ErrorActionPreference = "Continue"

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "   INTELISE COMPONENT 4 - SUPERVISOR DEMO SYSTEM HEALTH CHECK" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

$AllHealthy = $true

# 1. Virtual Environment & Python Runtime
Write-Host "[1/5] Checking Python Virtual Environment..." -NoNewline
$VenvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $PyVersion = & $VenvPython --version 2>&1
    Write-Host " [OK]" -ForegroundColor Green
    Write-Host "      Runtime: $PyVersion ($VenvPython)" -ForegroundColor Gray
} else {
    Write-Host " [FAIL]" -ForegroundColor Red
    Write-Host "      Virtualenv python.exe not found at $VenvPython" -ForegroundColor Red
    $AllHealthy = $false
}

# 2. FastAPI Backend Server (Port 8000)
Write-Host ""
Write-Host "[2/5] Checking FastAPI Backend API (http://127.0.0.1:8000/health)..." -NoNewline
try {
    $BackendResp = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method Get -TimeoutSec 4
    if ($BackendResp.status -eq "ok") {
        Write-Host " [OK]" -ForegroundColor Green
        Write-Host "      Service: $($BackendResp.service)" -ForegroundColor Gray
        Write-Host "      Database: $($BackendResp.storage_backend) (Ephemeral: $($BackendResp.is_ephemeral_storage))" -ForegroundColor Gray
    } else {
        Write-Host " [WARN]" -ForegroundColor Yellow
        Write-Host "      Unexpected response status: $($BackendResp.status)" -ForegroundColor Yellow
    }
} catch {
    Write-Host " [FAIL]" -ForegroundColor Red
    Write-Host "      Cannot connect to FastAPI backend at http://127.0.0.1:8000" -ForegroundColor Red
    Write-Host "      Start with: cd backend; ..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000" -ForegroundColor Yellow
    $AllHealthy = $false
}

# 3. React / Vite Frontend Server (Port 5173)
Write-Host ""
Write-Host "[3/5] Checking React/Vite Frontend (http://127.0.0.1:5173)..." -NoNewline
try {
    $FrontendResp = Invoke-WebRequest -Uri "http://127.0.0.1:5173" -Method Get -TimeoutSec 4 -UseBasicParsing
    if ($FrontendResp.StatusCode -eq 200) {
        Write-Host " [OK]" -ForegroundColor Green
        Write-Host "      Frontend URL: http://127.0.0.1:5173" -ForegroundColor Gray
    } else {
        Write-Host " [WARN]" -ForegroundColor Yellow
        Write-Host "      Unexpected status code: $($FrontendResp.StatusCode)" -ForegroundColor Yellow
    }
} catch {
    Write-Host " [FAIL]" -ForegroundColor Red
    Write-Host "      Cannot connect to Vite dev server at http://127.0.0.1:5173" -ForegroundColor Red
    Write-Host "      Start with: cd frontend; npm run dev" -ForegroundColor Yellow
    $AllHealthy = $false
}

# 4. Docker Engine & Sandbox Runner Image
Write-Host ""
Write-Host "[4/5] Checking Docker Sandbox Environment..." -NoNewline
try {
    $DockerVersion = docker --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $ImageMatch = docker images --format "{{.Repository}}:{{.Tag}}" | Select-String "intelise-python-runner:3.12"
        if ($ImageMatch) {
            Write-Host " [OK]" -ForegroundColor Green
            Write-Host "      Docker Daemon: Connected ($DockerVersion)" -ForegroundColor Gray
            Write-Host "      Sandbox Image: intelise-python-runner:3.12 [Ready]" -ForegroundColor Gray
        } else {
            Write-Host " [WARN]" -ForegroundColor Yellow
            Write-Host "      Docker daemon active, but 'intelise-python-runner:3.12' image is missing." -ForegroundColor Yellow
            $AllHealthy = $false
        }
    } else {
        Write-Host " [FAIL]" -ForegroundColor Red
        Write-Host "      Docker command failed. Is Docker Desktop running?" -ForegroundColor Red
        $AllHealthy = $false
    }
} catch {
    Write-Host " [FAIL]" -ForegroundColor Red
    Write-Host "      Docker CLI not found or daemon unreachable." -ForegroundColor Red
    $AllHealthy = $false
}

# 5. Ollama LLM Runtime & Qwen2.5-Coder Model (Port 11434)
Write-Host ""
Write-Host "[5/5] Checking Ollama LLM Service (http://127.0.0.1:11434/api/tags)..." -NoNewline
try {
    $OllamaResp = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -Method Get -TimeoutSec 4
    $ModelList = $OllamaResp.models | ForEach-Object { $_.name }
    $HasQwen = $ModelList | Select-String "qwen2.5-coder:3b"
    if ($HasQwen) {
        Write-Host " [OK]" -ForegroundColor Green
        Write-Host "      Runtime: Ollama active on port 11434" -ForegroundColor Gray
        Write-Host "      Required Model: qwen2.5-coder:3b [Ready]" -ForegroundColor Gray
    } else {
        Write-Host " [WARN]" -ForegroundColor Yellow
        Write-Host "      Ollama running, but model 'qwen2.5-coder:3b' was not found." -ForegroundColor Yellow
        Write-Host "      Available: $($ModelList -join ', ')" -ForegroundColor Gray
        $AllHealthy = $false
    }
} catch {
    Write-Host " [FAIL]" -ForegroundColor Red
    Write-Host "      Cannot connect to Ollama runtime at http://127.0.0.1:11434" -ForegroundColor Red
    Write-Host "      Start with: ollama serve" -ForegroundColor Yellow
    $AllHealthy = $false
}

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
if ($AllHealthy) {
    Write-Host " VERDICT: ALL SYSTEMS GO (DEMO READY)" -ForegroundColor Green
    Write-Host " Frontend: http://127.0.0.1:5173" -ForegroundColor White
    Write-Host " Backend Docs: http://127.0.0.1:8000/docs" -ForegroundColor White
} else {
    Write-Host " VERDICT: ONE OR MORE DEPENDENCIES REQUIRE ATTENTION" -ForegroundColor Red
}
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""
