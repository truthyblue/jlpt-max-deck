[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

Write-Host "`n[1/4] 먼저 PDF 17개가 든 폴더를 확인합니다."
Add-Type -AssemblyName System.Windows.Forms
$FolderPicker = New-Object System.Windows.Forms.FolderBrowserDialog
$FolderPicker.Description = "PDF 17개가 든 폴더를 선택하세요"
if ($FolderPicker.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
    $FolderPicker.Dispose()
    throw "PDF 폴더 선택을 취소했습니다."
}
$PdfRoot = $FolderPicker.SelectedPath
$FolderPicker.Dispose()
$PdfCount = @(Get-ChildItem -LiteralPath $PdfRoot -Recurse -File -Filter *.pdf).Count
if ($PdfCount -ne 17) {
    throw "선택한 폴더에서 PDF ${PdfCount}개를 찾았습니다. 정확히 17개가 필요합니다."
}
Write-Host "PDF 17개를 확인했습니다. PDF는 이 컴퓨터 안에서만 사용합니다."

Write-Host "`n[2/4] 덱을 만드는 데 필요한 프로그램을 확인합니다."
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "필요한 프로그램 uv가 없어 지금 설치합니다."
    & powershell.exe -ExecutionPolicy ByPass -Command `
        "irm https://astral.sh/uv/install.ps1 | iex"
    if ($LASTEXITCODE -ne 0) {
        throw "uv 설치에 실패했습니다. 종료 코드: $LASTEXITCODE"
    }
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
} else {
    Write-Host "필요한 프로그램이 준비되어 있습니다."
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv 설치 후 PowerShell을 다시 열고 같은 명령을 실행해 주세요."
}

$ReleaseUrl = "https://github.com/truthyblue/jlpt-max-deck/releases/latest/download"
$Suffix = [guid]::NewGuid().ToString("N").Substring(0, 6)
$DirectoryName = "JLPT-MAX-public-build-{0}-{1}" -f `
    (Get-Date -Format "yyyyMMdd-HHmmss"), $Suffix
$WorkRoot = Join-Path `
    ([Environment]::GetFolderPath("LocalApplicationData")) $DirectoryName
$DownloadRoot = Join-Path $WorkRoot "download"
New-Item -ItemType Directory -Force -Path $DownloadRoot | Out-Null

Write-Host "`n[3/4] 공개 빌더 파일을 내려받고 손상되지 않았는지 확인합니다."
$Assets = @(
    "JLPT-MAX-public-bundle.zip",
    "JLPT-MAX-public-bundle.zip.sha256",
    "public-release.json"
)
foreach ($Asset in $Assets) {
    Invoke-WebRequest "$ReleaseUrl/$Asset" `
        -OutFile (Join-Path $DownloadRoot $Asset) `
        -UseBasicParsing
}

$ZipPath = Join-Path $DownloadRoot "JLPT-MAX-public-bundle.zip"
$Pin = Get-Content (Join-Path $DownloadRoot "public-release.json") `
    -Raw | ConvertFrom-Json
$FileHash = ((Get-Content `
    (Join-Path $DownloadRoot "JLPT-MAX-public-bundle.zip.sha256") `
    -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
$ActualHash = (Get-FileHash $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualHash -ne $Pin.archive_sha256.ToLowerInvariant()) {
    throw "내려받은 파일이 릴리스에 등록된 원본과 다릅니다. 파일을 실행하지 않고 멈춥니다."
}
if ($ActualHash -ne $FileHash) {
    throw "내려받은 파일이 손상되었거나 릴리스 정보와 일치하지 않습니다. 파일을 실행하지 않고 멈춥니다."
}
Write-Host "파일이 릴리스에 등록된 원본과 일치합니다."

$BuildRoot = Join-Path $WorkRoot "build"
Expand-Archive $ZipPath -DestinationPath $BuildRoot
$BuildScript = Join-Path $BuildRoot "public-bundle\scripts\build-public.ps1"
if (-not (Test-Path -LiteralPath $BuildScript -PathType Leaf)) {
    throw "내려받은 압축 파일에서 덱 만들기 스크립트를 찾지 못했습니다."
}
Write-Host "`n[4/4] 이제 덱을 만듭니다. 컴퓨터에 따라 시간이 걸릴 수 있습니다."
& powershell.exe -NoProfile -ExecutionPolicy ByPass `
    -File $BuildScript -PdfRoot $PdfRoot
if ($LASTEXITCODE -ne 0) {
    throw "덱 만들기에 실패했습니다. 종료 코드: $LASTEXITCODE"
}

$OutputRoot = Join-Path $BuildRoot "public-release"
Write-Host "`n완료했습니다. Anki에 가져올 파일이 있는 폴더:"
Write-Host $OutputRoot
try {
    Invoke-Item $OutputRoot
} catch {
    Write-Warning "폴더를 자동으로 열지 못했습니다. 위 경로를 파일 탐색기에서 직접 열어 주세요."
}
