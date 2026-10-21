# ============================================================================
# INTELISE Component 4 - Supervisor Demonstration Orchestrator
# One-click startup, validation, and demo scenario launcher
# ============================================================================

$ErrorActionPreference = "Continue"

function Show-Header {
    Clear-Host
    Write-Host "======================================================================" -ForegroundColor Cyan
    Write-Host "   INTELISE COMPONENT 4 — SUPERVISOR DEMONSTRATION ORCHESTRATOR" -ForegroundColor Cyan
    Write-Host "======================================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Show-Menu {
    Show-Header
    Write-Host "Please select a demonstration action:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  [1] Open Frontend Web Interface (http://127.0.0.1:5173)" -ForegroundColor White
    Write-Host "  [2] Open Backend OpenAPI Documentation (http://127.0.0.1:8000/docs)" -ForegroundColor White
    Write-Host "  [3] Execute Automated End-to-End Demo (Scenarios A, B, & C)" -ForegroundColor Green
    Write-Host "  [4] Run Full Backend Regression Suite (369 tests in Docker sandbox)" -ForegroundColor White
    Write-Host "  [5] Run System Health Check" -ForegroundColor White
    Write-Host "  [6] View Supervisor Demo Integration Report" -ForegroundColor White
    Write-Host "  [Q] Exit" -ForegroundColor Gray
    Write-Host ""
}

$VenvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"

while ($true) {
    Show-Menu
    $Choice = Read-Host "Enter selection [1-6, Q]"
    switch ($Choice) {
        "1" {
            Write-Host "`nOpening Frontend in default browser..." -ForegroundColor Cyan
            Start-Process "http://127.0.0.1:5173"
            Start-Sleep -Seconds 2
        }
        "2" {
            Write-Host "`nOpening Swagger Docs in default browser..." -ForegroundColor Cyan
            Start-Process "http://127.0.0.1:8000/docs"
            Start-Sleep -Seconds 2
        }
        "3" {
            Write-Host "`nExecuting Scenarios A, B, and C..." -ForegroundColor Cyan
            $DemoScript = Join-Path $PSScriptRoot "..\demo_scenarios\run_demo_scenarios.py"
            & $VenvPython $DemoScript
            Write-Host "`nPress Enter to return to menu..." -ForegroundColor Gray
            [void][System.Console]::ReadLine()
        }
        "4" {
            Write-Host "`nExecuting Full Backend Regression Suite..." -ForegroundColor Cyan
            $BackendDir = Join-Path $PSScriptRoot "..\backend"
            Push-Location $BackendDir
            & $VenvPython -m pytest tests/ -v
            Pop-Location
            Write-Host "`nPress Enter to return to menu..." -ForegroundColor Gray
            [void][System.Console]::ReadLine()
        }
        "5" {
            Write-Host "`nRunning Health Check..." -ForegroundColor Cyan
            $HealthScript = Join-Path $PSScriptRoot "health_check.ps1"
            & powershell.exe -ExecutionPolicy Bypass -File $HealthScript
            Write-Host "`nPress Enter to return to menu..." -ForegroundColor Gray
            [void][System.Console]::ReadLine()
        }
        "6" {
            $ReportPath = Join-Path $PSScriptRoot "..\docs\SUPERVISOR_DEMO_INTEGRATION_REPORT.md"
            if (Test-Path $ReportPath) {
                Get-Content $ReportPath | Out-Host -Paging
            } else {
                Write-Host "Report not found at $ReportPath" -ForegroundColor Red
                Start-Sleep -Seconds 2
            }
        }
        "Q" {
            Write-Host "`nExiting demonstration orchestrator. Goodbye!`n" -ForegroundColor Cyan
            break
        }
        "q" {
            Write-Host "`nExiting demonstration orchestrator. Goodbye!`n" -ForegroundColor Cyan
            break
        }
        default {
            Write-Host "Invalid option. Please try again." -ForegroundColor Red
            Start-Sleep -Seconds 1
        }
    }
}
