param(
  [switch]$StopServices
)

$ErrorActionPreference = "SilentlyContinue"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")

if ($StopServices) {
  foreach ($port in @(8001, 3000)) {
    Get-NetTCPConnection -LocalPort $port -State Listen | ForEach-Object {
      Stop-Process -Id $_.OwningProcess -Force
    }
  }
}

$logDir = Join-Path $root "logs"
if (Test-Path -LiteralPath $logDir) {
  Get-ChildItem -LiteralPath $logDir -File -Include *.log,*.err,*.out -Recurse | Remove-Item -Force
}

Get-ChildItem -LiteralPath $root -Directory -Recurse -Force -Filter "__pycache__" |
  Where-Object { $_.FullName -notmatch "\\(\.git|\.venv|node_modules)\\" } |
  Remove-Item -Recurse -Force

foreach ($path in @(".pytest_cache", ".mypy_cache", ".ruff_cache", ".coverage", "coverage.xml", "backend.pid", "frontend.pid")) {
  $target = Join-Path $root $path
  if (Test-Path -LiteralPath $target) {
    Remove-Item -LiteralPath $target -Recurse -Force
  }
}
