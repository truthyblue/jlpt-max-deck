param(
    [Parameter(Mandatory = $true)][string]$UpperPdf,
    [Parameter(Mandatory = $true)][string]$LowerPdf,
    [string]$OutputRoot
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $Root "build\kanji-addon"
}

Push-Location $Root
try {
    uv run --locked python src/build_kanji_addon.py `
        --upper-pdf $UpperPdf `
        --lower-pdf $LowerPdf `
        --asset-root (Join-Path $Root "assets") `
        --output-root $OutputRoot
}
finally {
    Pop-Location
}
