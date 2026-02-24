param(
    [switch]$Quick,
    [switch]$Strict
)

$ErrorActionPreference = "Continue"

function Write-Pass([string]$Message) { Write-Host "[PASS] $Message" -ForegroundColor Green }
function Write-Warn([string]$Message) { Write-Host "[WARN] $Message" -ForegroundColor Yellow }
function Write-Fail([string]$Message) { Write-Host "[FAIL] $Message" -ForegroundColor Red }
function Write-Info([string]$Message) { Write-Host "[INFO] $Message" -ForegroundColor Cyan }

$repoRoot = (Split-Path -Path $PSScriptRoot -Parent)
$venvPath = Join-Path $repoRoot ".venv"
$envPath = Join-Path $repoRoot ".env"
$configPath = Join-Path $repoRoot "config\config.yaml"

$pass = 0
$warn = 0
$fail = 0

Write-Host "=== BrightMind Doctor ===" -ForegroundColor Cyan
Write-Info "Repo root: $repoRoot"

if (Get-Command python -ErrorAction SilentlyContinue) {
    Write-Pass "Python detected: $(python --version 2>&1)"
    $pass++
} else {
    Write-Fail "Python not found in PATH"
    $fail++
}

if (Test-Path (Join-Path $venvPath "Scripts\python.exe")) {
    Write-Pass "Virtual environment exists at $venvPath"
    $pass++
} else {
    Write-Fail "Virtual environment missing at $venvPath"
    $fail++
}

$dDrive = Get-PSDrive -Name D -ErrorAction SilentlyContinue
if ($dDrive) {
    $freeD = [math]::Round($dDrive.Free / 1GB, 2)
    if ($freeD -ge 10) {
        Write-Pass "D: free space is $freeD GB"
        $pass++
    } else {
        Write-Fail "D: free space is $freeD GB (< 10 GB required)"
        $fail++
    }
} else {
    Write-Fail "D: drive not found"
    $fail++
}

$ollamaModels = [Environment]::GetEnvironmentVariable("OLLAMA_MODELS", "User")
if (-not $ollamaModels) {
    Write-Warn "OLLAMA_MODELS is not set (recommended: D:\ollama\models)"
    $warn++
} elseif ($ollamaModels -like "D:\*") {
    Write-Pass "OLLAMA_MODELS points to D: ($ollamaModels)"
    $pass++
} else {
    if ($Strict) {
        Write-Fail "OLLAMA_MODELS points outside D: ($ollamaModels)"
        $fail++
    } else {
        Write-Warn "OLLAMA_MODELS points outside D: ($ollamaModels)"
        $warn++
    }
}

if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Write-Pass "Ollama detected: $(ollama --version 2>&1)"
    $pass++
    if (-not $Quick) {
        $ollamaList = (ollama list 2>&1)
        if ($LASTEXITCODE -eq 0) {
            Write-Pass "Ollama is responsive"
            $pass++
            if ($ollamaList -match "qwen2.5-coder:7b") {
                Write-Pass "Default 7B model detected"
                $pass++
            } else {
                Write-Warn "Default 7B model not found; run download_model.ps1"
                $warn++
            }
        } else {
            Write-Warn "Ollama detected but not responsive"
            $warn++
        }
    }
} else {
    Write-Fail "Ollama not found in PATH"
    $fail++
}

if (Test-Path $envPath) {
    $envContent = Get-Content -Raw $envPath
    $botValue = (($envContent -split "`n") | Where-Object { $_ -match '^SLACK_BOT_TOKEN=' } | Select-Object -First 1)
    $appValue = (($envContent -split "`n") | Where-Object { $_ -match '^SLACK_APP_TOKEN=' } | Select-Object -First 1)

    $botToken = ($botValue -replace '^SLACK_BOT_TOKEN=', '').Trim()
    $appToken = ($appValue -replace '^SLACK_APP_TOKEN=', '').Trim()

    $botPlaceholder = ($botToken -eq '') -or ($botToken -match 'your-') -or ($botToken -notmatch '^xoxb-')
    $appPlaceholder = ($appToken -eq '') -or ($appToken -match 'your-') -or ($appToken -notmatch '^xapp-')

    if (-not $botPlaceholder -and -not $appPlaceholder) {
        Write-Pass "Slack tokens look configured"
        $pass++
    } else {
        if ($botPlaceholder) { Write-Fail "SLACK_BOT_TOKEN missing/placeholder/invalid" }
        if ($appPlaceholder) { Write-Fail "SLACK_APP_TOKEN missing/placeholder/invalid" }
        $fail++
    }
} else {
    Write-Fail ".env file missing at $envPath"
    $fail++
}

if (Test-Path $configPath) {
    Write-Pass "Config file exists at $configPath"
    $pass++
} else {
    Write-Warn "Config file missing; defaults/env only"
    $warn++
}

if (Get-Command openclaw -ErrorAction SilentlyContinue) {
    Write-Info "OpenClaw CLI detected (optional)"
} else {
    Write-Info "OpenClaw CLI not detected (optional)"
}

if (-not $Quick) {
    try {
        $gateway = Invoke-RestMethod -Uri "http://localhost:8080/health" -Method GET -TimeoutSec 3
        Write-Info "LLM Gateway health: status=$($gateway.status) readiness=$($gateway.readiness)"
    } catch {
        Write-Info "LLM Gateway is not running (this is fine before run_all.ps1)"
    }
}

Write-Host ""
Write-Host "Summary: PASS=$pass WARN=$warn FAIL=$fail" -ForegroundColor Cyan
if ($fail -gt 0) {
    Write-Host "Status: NOT_READY" -ForegroundColor Red
    exit 2
}

if ($warn -gt 0) {
    Write-Host "Status: READY_WITH_WARNINGS" -ForegroundColor Yellow
    exit 0
}

Write-Host "Status: READY" -ForegroundColor Green
exit 0
