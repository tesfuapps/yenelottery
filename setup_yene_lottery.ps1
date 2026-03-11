<#
setup_yene_lottery.ps1
Automated Setup Script for Yene Lottery Bot (Windows)
#>

Write-Host "Starting Yene Lottery Bot Environment Setup..." -ForegroundColor Cyan

# 1. Install Python 3.12 if not installed
Write-Host "Checking Python installation..." -ForegroundColor Yellow
$pythonCheck = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCheck -or ($pythonCheck.Source -match "WindowsApps")) {
    Write-Host "Python not found or only Microsoft Store stub found. Installing Python 3.12..." -ForegroundColor Cyan
    winget install Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    
    # Wait for winget to finish
    Start-Sleep -Seconds 10
    
    # Try adding Python to the current session's PATH roughly
    $pythonPath = "$env:LOCALAPPDATA\Programs\Python\Python312"
    $pythonScripts = "$env:LOCALAPPDATA\Programs\Python\Python312\Scripts"
    if (Test-Path $pythonPath) {
        $env:Path = "$pythonPath;$pythonScripts;" + $env:Path
    } else {
        # Alternatively, sometimes it installs to Program Files
        $pythonPathSys = "C:\Program Files\Python312"
        $pythonScriptsSys = "C:\Program Files\Python312\Scripts"
        if (Test-Path $pythonPathSys) {
             $env:Path = "$pythonPathSys;$pythonScriptsSys;" + $env:Path
        }
    }
} else {
    Write-Host "Python is already installed." -ForegroundColor Green
}

# 2. Install PostgreSQL if not installed
Write-Host "Checking PostgreSQL installation..." -ForegroundColor Yellow
$pgCheck = Get-Command psql -ErrorAction SilentlyContinue
if (-not $pgCheck) {
    Write-Host "PostgreSQL not found. Installing PostgreSQL..." -ForegroundColor Cyan
    winget install PostgreSQL.PostgreSQL --interactive --accept-package-agreements --accept-source-agreements
    
    Write-Host "NOTE: The PostgreSQL installer may pop up. Please click through it and remember the database password you set!" -ForegroundColor Yellow
} else {
    Write-Host "PostgreSQL is already installed." -ForegroundColor Green
}

# 3. Create Python Virtual Environment & Install dependencies
Write-Host "Setting up Python Virtual Environment..." -ForegroundColor Yellow
If (-not (Test-Path ".\venv")) {
    python -m venv venv
    Write-Host "Virtual environment created." -ForegroundColor Green
}

Write-Host "Installing Python packages (aiogram, PostgreSQL drivers, etc.)..." -ForegroundColor Yellow
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host ""
Write-Host "Setup script completed!" -ForegroundColor Green
Write-Host "-------------------------------------------------------"
Write-Host "IMPORTANT NEXT STEPS:" -ForegroundColor Yellow
Write-Host "1. PostgreSQL was installed with a default user 'postgres'."
Write-Host "   Open pgAdmin 4 (search in Windows Start) or psql and run: CREATE DATABASE yene_lottery;"
Write-Host "2. Copy .env.example to .env and fill in:"
Write-Host "   - BOT_TOKEN (from @BotFather on Telegram)"
Write-Host "   - YOUR ADMIN GROUP ID"
Write-Host "   - DB_PASSWORD (from the PostgreSQL install)"
Write-Host "3. To run the bot, type: .\venv\Scripts\python.exe bot.py"
Write-Host "-------------------------------------------------------"
