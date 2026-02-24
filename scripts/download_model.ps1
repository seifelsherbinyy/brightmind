# BrightMind Model Download Script
# Downloads specified Ollama model with safety checks

param(
    [Parameter(Mandatory=$true)]
    [string]$Model,
    
    [switch]$Force,
    [switch]$SkipConfirmation
)

$ErrorActionPreference = "Stop"

# Colors
$ColorInfo = "Cyan"
$ColorSuccess = "Green"
$ColorWarning = "Yellow"
$ColorError = "Red"
$ColorNeutral = "White"

function Write-Info { param([string]$Message) Write-Host "[INFO] $Message" -ForegroundColor $ColorInfo }
function Write-Success { param([string]$Message) Write-Host "[SUCCESS] $Message" -ForegroundColor $ColorSuccess }
function Write-Warning { param([string]$Message) Write-Host "[WARN] $Message" -ForegroundColor $ColorWarning }
function Write-Error { param([string]$Message) Write-Host "[ERROR] $Message" -ForegroundColor $ColorError }

Write-Host ""
Write-Host "=== BrightMind Model Download ===" -ForegroundColor $ColorInfo
Write-Host ""

# =============================================================================
# Model Size Database
# =============================================================================
$modelSizes = @{
    "phi3:3.8b" = 2.2
    "phi3:3.8b-mini" = 2.2
    "llama3.2:1b" = 1.3
    "llama3.2:3b" = 2.0
    "llama3.2:7b" = 4.1
    "qwen2.5-coder:1.5b" = 1.0
    "qwen2.5-coder:7b" = 4.5
    "qwen2.5-coder:14b" = 9.0
    "qwen2.5-coder:32b" = 20.0
    "deepseek-r1:1.5b" = 1.1
    "deepseek-r1:7b" = 4.0
    "deepseek-r1:14b" = 9.0
    "deepseek-r1:32b" = 20.0
    "gemma2:2b" = 1.6
    "gemma2:9b" = 5.4
    "mistral:7b" = 4.1
    "codellama:7b" = 3.8
    "codellama:13b" = 7.8
}

# Estimate size
$estimatedSize = $modelSizes[$Model]
if (-not $estimatedSize) {
    # Try to estimate from model name
    if ($Model -match ":(\d+)b") {
        $paramCount = [int]$matches[1]
        # Rough estimate: 0.5GB per billion parameters for Q4 quantization
        $estimatedSize = [math]::Round($paramCount * 0.6, 1)
    } else {
        $estimatedSize = 5.0  # Default estimate
    }
    Write-Warning "Unknown model size, estimating ~$estimatedSize GB"
}

# =============================================================================
# Pre-Download Checks
# =============================================================================
Write-Info "Model: $Model"
Write-Info "Estimated size: ~$estimatedSize GB"
Write-Info "Recommendation: default quality model is qwen2.5-coder:7b (~4.5GB)"
Write-Info "Fallback for constrained systems: qwen2.5-coder:1.5b or llama3.2:3b"
Write-Host ""

# Check Ollama
$ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollamaCmd) {
    Write-Error "Ollama not found in PATH"
    Write-Info "Install from: https://ollama.com/download/windows"
    exit 1
}

# Check disk space
$ollamaModels = [Environment]::GetEnvironmentVariable("OLLAMA_MODELS", "User")
if (-not $ollamaModels) {
    $ollamaModels = "$env:USERPROFILE\.ollama\models"
}

$targetDrive = ($ollamaModels -split ":")[0]
$drive = Get-PSDrive -Name $targetDrive -ErrorAction SilentlyContinue

if (-not $drive) {
    Write-Error "Target drive $targetDrive`: not found"
    exit 1
}

$freeSpaceGB = [math]::Round($drive.Free / 1GB, 2)
$requiredSpaceGB = $estimatedSize + 2  # Add buffer

Write-Info "Target location: $ollamaModels"
Write-Info "Available space: $freeSpaceGB GB"
Write-Info "Required space: ~$requiredSpaceGB GB"
Write-Host ""

if ($freeSpaceGB -lt $requiredSpaceGB) {
    Write-Error "Insufficient disk space"
    Write-Info "Free up space or set OLLAMA_MODELS to a different drive"
    exit 1
}

# Warn about C: drive
if ($targetDrive -eq "C") {
    Write-Warning "Models will be downloaded to C: drive"
    Write-Info "Consider setting OLLAMA_MODELS to D:\ollama\models"
    Write-Host ""
}

# Confirmation
if (-not $SkipConfirmation -and -not $Force) {
    $confirmation = Read-Host "Download $Model (~$estimatedSize GB)? (y/N)"
    if ($confirmation -ne "y" -and $confirmation -ne "Y") {
        Write-Info "Download cancelled"
        exit 0
    }
}

Write-Host ""

# =============================================================================
# Download
# =============================================================================
Write-Info "Starting download..."
Write-Info "This may take 10-30 minutes depending on your connection"
Write-Host ""

$startTime = Get-Date

try {
    # Pull the model
    & ollama pull $Model 2>&1 | ForEach-Object {
        $line = $_
        
        # Show progress
        if ($line -match "pulling|downloading|extracting") {
            Write-Host "  $line" -ForegroundColor $ColorNeutral
        } elseif ($line -match "success|complete") {
            Write-Success $line
        } elseif ($line -match "error|failed") {
            Write-Error $line
        } else {
            Write-Host "  $line"
        }
    }
    
    if ($LASTEXITCODE -ne 0) {
        throw "Ollama pull failed with exit code $LASTEXITCODE"
    }
    
    $endTime = Get-Date
    $duration = $endTime - $startTime
    
    Write-Host ""
    Write-Success "Model downloaded successfully!"
    Write-Info "Duration: $($duration.ToString('hh\:mm\:ss'))"
    
    # Verify
    Write-Host ""
    Write-Info "Verifying installation..."
    $modelList = & ollama list 2>&1
    $modelFound = $modelList | Where-Object { $_ -match "^$Model\s" }
    
    if ($modelFound) {
        Write-Success "Model verified: $modelFound"
    } else {
        Write-Warning "Model may not have installed correctly"
    }
    
    Write-Host ""
    Write-Info "Test the model:"
    Write-Host "  ollama run $Model"
    Write-Host ""
    
} catch {
    Write-Error "Download failed: $_"
    Write-Host ""
    Write-Info "Troubleshooting:"
    Write-Host "  1. Check internet connection"
    Write-Host "  2. Verify Ollama is running: ollama list"
    Write-Host "  3. Try again: .\scripts\download_model.ps1 -Model `"$Model`" -Force"
    Write-Host "  4. Check Ollama logs"
    exit 1
}

Write-Host ""
