param(
    [string]$InstallDir,
    [string]$OllamaDir = "D:\ollama",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Write-Info([string]$Message) { Write-Host "[INFO] $Message" -ForegroundColor Cyan }
function Write-Success([string]$Message) { Write-Host "[PASS] $Message" -ForegroundColor Green }
function Write-Warn([string]$Message) { Write-Host "[WARN] $Message" -ForegroundColor Yellow }
function Write-Fail([string]$Message) { Write-Host "[FAIL] $Message" -ForegroundColor Red }

$repoRoot = (Split-Path -Path $PSScriptRoot -Parent)
if (-not $InstallDir) { $InstallDir = $repoRoot }
$InstallDir = (Resolve-Path $InstallDir).Path

Write-Host "=== BrightMind Bootstrap ===" -ForegroundColor Cyan
Write-Info "Repo root: $repoRoot"
Write-Info "Install dir: $InstallDir"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Fail "Python not found in PATH"
    exit 1
}

$pyVersion = (python --version 2>&1)
Write-Info "Python: $pyVersion"

$dDrive = Get-PSDrive -Name D -ErrorAction SilentlyContinue
if (-not $dDrive) {
    Write-Fail "D: drive not available"
    exit 1
}

$freeD = [math]::Round($dDrive.Free / 1GB, 2)
if ($freeD -lt 10) {
    Write-Fail "D: free space is $freeD GB (< 10 GB required)"
    exit 1
}
Write-Success "D: free space is $freeD GB"

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) {
    Write-Info "Admin rights detected"
} else {
    Write-Warn "Running without admin rights; user-scope setup only"
}

$dirs = @(
    $InstallDir,
    (Join-Path $InstallDir "logs"),
    (Join-Path $InstallDir "cache"),
    (Join-Path $InstallDir "data")
)
foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) { New-Item -Path $dir -ItemType Directory -Force | Out-Null }
}
Write-Success "Project directories are ready"

$venvPath = Join-Path $InstallDir ".venv"
if ((Test-Path $venvPath) -and $Force) {
    Remove-Item -Recurse -Force $venvPath
}
if (-not (Test-Path $venvPath)) {
    python -m venv $venvPath
    Write-Success "Created virtual environment"
} else {
    Write-Info "Virtual environment already exists"
}

$pythonExe = Join-Path $venvPath "Scripts\python.exe"
$pipExe = Join-Path $venvPath "Scripts\pip.exe"
if (-not (Test-Path $pythonExe)) {
    Write-Fail "Virtual environment is incomplete at $venvPath"
    exit 1
}

& $pythonExe -m pip install --upgrade pip | Out-Null

function Install-EditableIfExists([string]$Label, [string]$Path) {
    if (Test-Path $Path) {
        Write-Info "Installing $Label dependencies"
        & $pipExe install -e $Path
    } else {
        Write-Warn "Skipped $Label dependencies; missing $Path"
    }
}

function Install-RequirementsIfExists([string]$Label, [string]$Path) {
    if (Test-Path $Path) {
        Write-Info "Installing $Label dependencies"
        & $pipExe install -r $Path
    } else {
        Write-Warn "Skipped $Label dependencies; missing $Path"
    }
}

Install-EditableIfExists "common" (Join-Path $InstallDir "services\common")
Install-RequirementsIfExists "llm_gateway" (Join-Path $InstallDir "services\llm_gateway\requirements.txt")
Install-RequirementsIfExists "slack_bot" (Join-Path $InstallDir "services\slack_bot\requirements.txt")
Install-RequirementsIfExists "openclaw_adapter" (Join-Path $InstallDir "services\openclaw_adapter\requirements.txt")
Write-Success "Dependencies installed"

$envPath = Join-Path $InstallDir ".env"
$envExamplePath = Join-Path $InstallDir ".env.example"
if (-not (Test-Path $envPath) -and (Test-Path $envExamplePath)) {
    Copy-Item $envExamplePath $envPath
    Write-Warn "Created .env from .env.example (edit tokens before running services)"
}

$configPath = Join-Path $InstallDir "config\config.yaml"
$configExamplePath = Join-Path $InstallDir "config\config.example.yaml"
if (-not (Test-Path $configPath) -and (Test-Path $configExamplePath)) {
    Copy-Item $configExamplePath $configPath
    Write-Success "Created config.yaml from template"
}

$ollamaModelsTarget = Join-Path $OllamaDir "models"
$currentModels = [Environment]::GetEnvironmentVariable("OLLAMA_MODELS", "User")
if (-not $currentModels -or $currentModels -like "C:\*") {
    [Environment]::SetEnvironmentVariable("OLLAMA_MODELS", $ollamaModelsTarget, "User")
    $env:OLLAMA_MODELS = $ollamaModelsTarget
    Write-Success "Set OLLAMA_MODELS to $ollamaModelsTarget"
} else {
    Write-Info "OLLAMA_MODELS already set to $currentModels"
}

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Warn "Ollama not detected. Install from https://docs.ollama.com/windows"
    Write-Warn "Optional unattended install command: iwr https://openclaw.ai/install.ps1 -UseBasicParsing | iex"
} else {
    Write-Info "Ollama detected: $(ollama --version)"
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1) Edit .env with SLACK_BOT_TOKEN and SLACK_APP_TOKEN"
Write-Host "2) Run .\scripts\doctor.ps1"
Write-Host "3) Run .\scripts\download_model.ps1 -Model \"qwen2.5-coder:7b\""
Write-Host "4) Run .\scripts\run_all.ps1"
