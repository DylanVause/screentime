#Requires -Version 5.1
<#
.SYNOPSIS
    Installs the ScreenTime client, configures it, and optionally adds it to startup.
#>

$GITHUB_URL  = "https://github.com/DylanVause/screentime"
$SERVER_URL  = "https://screentime.dylanvause.com"
$INSTALL_DIR = "$env:USERPROFILE\ScreenTime"

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Write-Err($msg)  { Write-Host "    ERROR: $msg" -ForegroundColor Red }

# ── Check Python ─────────────────────────────────────────────────────────────

Write-Step "Checking Python..."
try {
    $py = (Get-Command python -ErrorAction Stop).Source
    $ver = & python --version 2>&1
    Write-Ok "$ver at $py"
} catch {
    Write-Err "Python not found. Install from https://python.org/downloads and re-run."
    exit 1
}

# ── Download repo ─────────────────────────────────────────────────────────────

Write-Step "Downloading ScreenTime..."

if (Test-Path $INSTALL_DIR) {
    Write-Ok "Found existing install at $INSTALL_DIR — skipping download."
} else {
    $zip = "$env:TEMP\screentime.zip"
    $extracted = "$env:TEMP\screentime-extract"

    Invoke-WebRequest "$GITHUB_URL/archive/refs/heads/main.zip" -OutFile $zip
    Expand-Archive $zip -DestinationPath $extracted -Force

    $clientSrc = Get-ChildItem $extracted | Select-Object -First 1
    Copy-Item "$($clientSrc.FullName)\client" $INSTALL_DIR -Recurse
    Remove-Item $zip, $extracted -Recurse -Force
    Write-Ok "Installed to $INSTALL_DIR"
}

# ── Install Python dependencies ───────────────────────────────────────────────

Write-Step "Installing dependencies..."
& python -m pip install -q -r "$INSTALL_DIR\requirements.txt"
Write-Ok "Done."

# ── Prompt for config ─────────────────────────────────────────────────────────

Write-Step "Configuration"

$deviceName = Read-Host "  Device name (shown in dashboard)"
if (-not $deviceName) { $deviceName = $env:COMPUTERNAME }

$apiKey = Read-Host "  API key (from $SERVER_URL/api-keys)"
if (-not $apiKey) {
    Write-Err "API key is required."
    exit 1
}

# ── Write config.toml ─────────────────────────────────────────────────────────

$config = @"
[server]
url = "$SERVER_URL"
api_key = "$apiKey"
verify_ssl = true
timeout_seconds = 30

[device]
name = "$deviceName"

[tracking]
poll_interval = 1
upload_interval = 900
min_session_seconds = 2

[storage]
db_path = "sessions.db"
"@

Set-Content "$INSTALL_DIR\config.toml" $config -Encoding UTF8
Write-Ok "Config written."

# ── Startup shortcut ──────────────────────────────────────────────────────────

Write-Step "Auto-start on login"
$addStartup = Read-Host "  Start tracker automatically when you log in? (y/n)"

if ($addStartup -match "^[Yy]") {
    $startup  = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
    $shortcut = "$startup\ScreenTimeTracker.lnk"
    $vbs      = "$INSTALL_DIR\run_silent.vbs"

    $ws = New-Object -ComObject WScript.Shell
    $s  = $ws.CreateShortcut($shortcut)
    $s.TargetPath       = "wscript.exe"
    $s.Arguments        = "`"$vbs`""
    $s.WorkingDirectory = $INSTALL_DIR
    $s.Description      = "ScreenTime Tracker"
    $s.Save()
    Write-Ok "Shortcut created — tracker will start on next login."
} else {
    Write-Ok "Skipped. Run manually with:  $INSTALL_DIR\run.bat"
}

# ── Done ──────────────────────────────────────────────────────────────────────

Write-Host "`nInstall complete!" -ForegroundColor Green
Write-Host "To start now, run: $INSTALL_DIR\run.bat"
