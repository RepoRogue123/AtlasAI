# Atlas - one-command setup + start (Windows PowerShell)
#   .\run.ps1          -> installs if needed, builds the UI, serves everything on http://127.0.0.1:8000
#   .\run.ps1 -Dev     -> backend on :8000 + Vite dev server with hot reload on :5173
param([switch]$Dev)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

if (-not (Test-Path "$root\.env")) { Copy-Item "$root\.env.example" "$root\.env"; Write-Host "Created .env - add your GEMINI_API_KEY" -ForegroundColor Yellow }

$py = "$root\backend\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    python -m venv "$root\backend\.venv"
    & $py -m pip install -q -r "$root\backend\requirements.txt"
    & $py -m playwright install chromium
}
if (-not (Test-Path "$root\frontend\node_modules")) { Push-Location "$root\frontend"; npm install; Pop-Location }

if ($Dev) {
    Start-Process -FilePath $py -ArgumentList "-m", "app.main" -WorkingDirectory "$root\backend"
    Push-Location "$root\frontend"; npm run dev; Pop-Location
} else {
    Push-Location "$root\frontend"; npm run build; Pop-Location
    Write-Host "Atlas on http://127.0.0.1:8000  (sandbox apps on http://127.0.0.1:8001)" -ForegroundColor Green
    Push-Location "$root\backend"; & $py -m app.main; Pop-Location
}
