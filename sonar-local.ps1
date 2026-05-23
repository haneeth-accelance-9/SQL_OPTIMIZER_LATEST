# sonar-local.ps1 — Start SonarQube in Docker and run a local scan.
# Prerequisites: Docker Desktop must be running (Linux containers mode).
# Usage: .\sonar-local.ps1

$ErrorActionPreference = 'Stop'
$SonarUrl   = "http://localhost:9000"
$ProjectKey = "bayer-int_af-license-agreement-171817_ce02d861-5f80-4816-9b6f-1cc4000ba92f"

# Read token from environment variable (set once in your shell profile or CI secrets):
#   $env:SONAR_TOKEN = "squ_..."
$ScanToken = $env:SONAR_TOKEN
if (-not $ScanToken) {
    Write-Host "SONAR_TOKEN environment variable is not set." -ForegroundColor Red
    Write-Host "Set it before running: `$env:SONAR_TOKEN = 'squ_...'" -ForegroundColor Yellow
    exit 1
}

function Wait-SonarQube {
    Write-Host "Waiting for SonarQube to be ready..."
    $retries = 30
    for ($i = 0; $i -lt $retries; $i++) {
        try {
            $resp = Invoke-RestMethod "$SonarUrl/api/system/status" -ErrorAction SilentlyContinue
            if ($resp.status -eq "UP") {
                Write-Host "SonarQube is ready."
                return
            }
        } catch {}
        Write-Host "  Not ready yet ($($i+1)/$retries), retrying in 10s..."
        Start-Sleep -Seconds 10
    }
    throw "SonarQube did not become ready in time."
}

# ── Step 1: Start SonarQube ────────────────────────────────────────────────────
Write-Host "`n=== Starting SonarQube ===" -ForegroundColor Cyan
docker compose -f docker-compose.sonar.yml up -d
Wait-SonarQube

# ── Step 2: Run tests to generate coverage.xml ────────────────────────────────
Write-Host "`n=== Running tests (generates coverage.xml) ===" -ForegroundColor Cyan
Push-Location app
try {
    pip install -r requirements-dev.txt -q
    pytest --reuse-db
} finally {
    Pop-Location
}

# ── Step 3: Fix coverage.xml source path for Docker scanner ───────────────────
Write-Host "`n=== Fixing coverage.xml source path ===" -ForegroundColor Cyan
python -c @"
import re, os
path = 'app/coverage.xml'
if not os.path.exists(path):
    print('coverage.xml not found, skipping fix')
    exit(0)
with open(path, 'r') as f:
    content = f.read()
content = re.sub(r'<source>[^<]*optimizer</source>', '<source>/usr/src/optimizer</source>', content)
with open(path, 'w') as f:
    f.write(content)
print('coverage.xml source path updated to /usr/src/optimizer')
"@

# ── Step 4: Detect sonarqube network ──────────────────────────────────────────
$sqNetwork = docker inspect sonarqube --format "{{range `$k, `$v := .NetworkSettings.Networks}}{{`$k}}{{end}}" 2>$null
if (-not $sqNetwork) { $sqNetwork = "sql_optimizer_latest_default" }
Write-Host "Using Docker network: $sqNetwork"

# ── Step 5: Run sonar-scanner via Docker ──────────────────────────────────────
Write-Host "`n=== Running SonarQube scan ===" -ForegroundColor Cyan
$appPath = (Resolve-Path "app").Path -replace '\\', '/'

$env:MSYS_NO_PATHCONV = "1"
docker run --rm `
    --network $sqNetwork `
    -v "${appPath}://usr/src" `
    sonarsource/sonar-scanner-cli:5.0 `
    "-Dsonar.projectKey=$ProjectKey" `
    "-Dsonar.sources=optimizer" `
    "-Dsonar.tests=optimizer/tests" `
    "-Dsonar.language=py" `
    "-Dsonar.python.coverage.reportPaths=coverage.xml" `
    "-Dsonar.host.url=http://sonarqube:9000" `
    "-Dsonar.login=$ScanToken" `
    "-Dsonar.projectBaseDir=//usr/src" `
    "-Dsonar.exclusions=**/migrations/**,**/__pycache__/**,**/static/**,**/templates/**" `
    "-Dsonar.coverage.exclusions=**/migrations/**,**/tests/**,**/admin.py,**/apps.py"

Write-Host "`n=== Scan complete. Open $SonarUrl to view results. ===" -ForegroundColor Green
