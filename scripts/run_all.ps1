param(
    [switch]$Restart,
    [switch]$Stop,
    [switch]$NoSlackBot,
    [switch]$NoOpenClawAdapter
)

$ErrorActionPreference = "Stop"

function Write-Info([string]$Message) { Write-Host "[INFO] $Message" -ForegroundColor Cyan }
function Write-Pass([string]$Message) { Write-Host "[PASS] $Message" -ForegroundColor Green }
function Write-Warn([string]$Message) { Write-Host "[WARN] $Message" -ForegroundColor Yellow }
function Write-Fail([string]$Message) { Write-Host "[FAIL] $Message" -ForegroundColor Red }

$repoRoot = (Split-Path -Path $PSScriptRoot -Parent)
$logDir = Join-Path $repoRoot "logs"
$pidFile = Join-Path $logDir "service_pids.json"
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $logDir)) { New-Item -Path $logDir -ItemType Directory -Force | Out-Null }

function Stop-ByPidMap {
    if (-not (Test-Path $pidFile)) {
        Write-Info "No PID file found ($pidFile)"
        return
    }
    $raw = Get-Content -Raw $pidFile
    if (-not $raw) { return }
    $map = $raw | ConvertFrom-Json
    foreach ($entry in $map.PSObject.Properties) {
        $name = $entry.Name
        $procId = [int]$entry.Value
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($proc) {
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            Write-Pass "Stopped $name (PID $procId)"
        } else {
            Write-Warn "$name PID $procId already stopped"
        }
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

if ($Stop) {
    Write-Host "=== BrightMind Stop ===" -ForegroundColor Cyan
    Stop-ByPidMap
    exit 0
}

if (-not (Test-Path $venvPython)) {
    Write-Fail "Virtual environment is missing. Run .\scripts\bootstrap.ps1"
    exit 1
}

if ($Restart) {
    Write-Info "Restart requested; stopping existing services first"
    Stop-ByPidMap
}

Write-Host "=== BrightMind Service Startup ===" -ForegroundColor Cyan
$started = @{}

function Start-ServiceProcess([string]$Name, [string]$ScriptPath, [string]$LogName) {
    $outPath = Join-Path $logDir $LogName
    $errPath = Join-Path $logDir ($LogName -replace "\.log$", ".err.log")
    $proc = Start-Process -FilePath $venvPython -ArgumentList $ScriptPath -WorkingDirectory $repoRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput $outPath -RedirectStandardError $errPath
    Start-Sleep -Seconds 2
    $check = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
    if ($check) {
        $script:started[$Name] = $proc.Id
        Write-Pass "$Name started (PID $($proc.Id))"
    } else {
        Write-Fail "$Name failed to start. Check $outPath and $errPath"
    }
}

Start-ServiceProcess -Name "llm_gateway" -ScriptPath "services/llm_gateway/app.py" -LogName "llm_gateway.log"

if (-not $NoSlackBot) {
    Start-ServiceProcess -Name "slack_bot" -ScriptPath "services/slack_bot/app.py" -LogName "slack_bot.log"
}

$envPath = Join-Path $repoRoot ".env"
$openclawEnabled = $false
if ((Test-Path $envPath) -and ((Get-Content -Raw $envPath) -match "OPENCLAW_ENABLED=true")) {
    $openclawEnabled = $true
}

if (-not $NoOpenClawAdapter -and $openclawEnabled) {
    Start-ServiceProcess -Name "openclaw_adapter" -ScriptPath "services/openclaw_adapter/app.py" -LogName "openclaw_adapter.log"
}

if ($started.Count -eq 0) {
    Write-Fail "No services started"
    exit 1
}

$started | ConvertTo-Json | Set-Content -Encoding utf8 $pidFile

Write-Host ""
Write-Host "Service summary:" -ForegroundColor Cyan
Write-Host "- Repo root: $repoRoot"
Write-Host "- Log dir:   $logDir"
Write-Host "- PID file:  $pidFile"
Write-Host "- LLM health: http://localhost:8080/health"
if ($started.ContainsKey("openclaw_adapter")) { Write-Host "- OpenClaw adapter: http://localhost:8081/health" }
Write-Host ""
$started.GetEnumerator() | ForEach-Object { Write-Host ("- {0}: PID {1}" -f $_.Key, $_.Value) }
Write-Host ""
Write-Host "Press Ctrl+C to stop. Services will be terminated on exit." -ForegroundColor Yellow

try {
    while ($true) {
        Start-Sleep -Seconds 5
        foreach ($entry in $started.GetEnumerator()) {
            if (-not (Get-Process -Id $entry.Value -ErrorAction SilentlyContinue)) {
                Write-Fail "$($entry.Key) stopped unexpectedly"
                exit 1
            }
        }
    }
} finally {
    Stop-ByPidMap
}
