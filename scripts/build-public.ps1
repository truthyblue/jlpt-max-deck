[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PdfRoot,

    [string]$BundleRoot = "",

    [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$RuntimeRoot = (Resolve-Path -LiteralPath (Join-Path $RepoRoot "..")).Path
$PdfPath = (Resolve-Path -LiteralPath $PdfRoot).Path

if ([string]::IsNullOrWhiteSpace($BundleRoot)) {
    $BundlePath = $RepoRoot
} else {
    $BundlePath = (Resolve-Path -LiteralPath $BundleRoot).Path
}

$OutputPath = $null
if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputPath = [System.IO.Path]::GetFullPath($OutputRoot)
}

if (-not (Test-Path -LiteralPath $BundlePath -PathType Container)) {
    throw "Public bundle directory is missing: $BundlePath"
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required. Install it with: winget install --id=astral-sh.uv -e"
}

Push-Location $RepoRoot
try {
    $env:OMP_NUM_THREADS = "1"
    $env:OMP_THREAD_LIMIT = "1"
    $env:PYTHONDONTWRITEBYTECODE = "1"
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $RuntimeRoot ".jlpt-max-public-venv"
    & uv sync --locked --python 3.13
    if ($LASTEXITCODE -ne 0) {
        throw "uv sync failed with exit code $LASTEXITCODE"
    }

    $Python = Join-Path $env:UV_PROJECT_ENVIRONMENT "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw "Python 3.13 environment was not created: $Python"
    }
    $BuildArgs = @(
        "src/build_public_deck.py",
        "--pdf-root", $PdfPath,
        "--bundle-root", $BundlePath
    )
    if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) {
        $BuildArgs += @("--output-root", $OutputPath)
    }
    & $Python @BuildArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Public deck build failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}
