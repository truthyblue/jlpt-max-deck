#requires -Version 5.1

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Windows.Forms

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$OutputRoot = Join-Path $Root "build/kanji-addon"
$LogPath = Join-Path $Root "kanji-builder.log"
$UvVersion = "0.11.32"
$UvRoot = Join-Path $Root ".tools/uv"
$UvExe = Join-Path $UvRoot "uv.exe"

function Select-Pdf {
    param([Parameter(Mandatory = $true)][string]$Title)

    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    try {
        $dialog.Title = $Title
        $dialog.Filter = "PDF 파일 (*.pdf)|*.pdf"
        $dialog.Multiselect = $false
        $dialog.RestoreDirectory = $true
        $downloads = Join-Path $env:USERPROFILE "Downloads"
        if (Test-Path -LiteralPath $downloads -PathType Container) {
            $dialog.InitialDirectory = $downloads
        }
        if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
            return $null
        }
        return $dialog.FileName
    }
    finally {
        $dialog.Dispose()
    }
}

function Show-BuilderError {
    param([Parameter(Mandatory = $true)][string]$Message)

    [System.Windows.Forms.MessageBox]::Show(
        $Message,
        "JLPT MAX 한자 확장",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
}

function Confirm-OutputReplacement {
    $answer = [System.Windows.Forms.MessageBox]::Show(
        "이전에 만든 결과가 있습니다.`n기존 결과를 지우고 다시 만들까요?",
        "JLPT MAX 한자 확장",
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Question
    )
    return $answer -eq [System.Windows.Forms.DialogResult]::Yes
}

try {
    Write-Host ""
    Write-Host "JLPT MAX 일상무따 한자 확장 만들기"
    Write-Host "화면에 나타나는 순서대로 PDF 두 개를 선택하세요."
    Write-Host ""

    $UpperPdf = Select-Pdf "1권(상권)의 지원 소책자 PDF를 선택하세요"
    if (-not $UpperPdf) {
        Write-Host "사용자가 작업을 취소했습니다."
        exit 0
    }
    Write-Host "1권 PDF: $([IO.Path]::GetFileName($UpperPdf))"

    $LowerPdf = Select-Pdf "2권(하권)의 지원 소책자 PDF를 선택하세요"
    if (-not $LowerPdf) {
        Write-Host "사용자가 작업을 취소했습니다."
        exit 0
    }
    Write-Host "2권 PDF: $([IO.Path]::GetFileName($LowerPdf))"

    if ([IO.Path]::GetFullPath($UpperPdf) -eq [IO.Path]::GetFullPath($LowerPdf)) {
        throw "같은 PDF를 두 번 선택했습니다. 1권과 2권 PDF를 각각 선택해 주세요."
    }

    if (
        (Test-Path -LiteralPath $OutputRoot) -and
        (Get-ChildItem -LiteralPath $OutputRoot -Force | Select-Object -First 1)
    ) {
        if (-not (Confirm-OutputReplacement)) {
            Write-Host "기존 결과를 유지하고 작업을 취소했습니다."
            exit 0
        }
        Remove-Item -LiteralPath $OutputRoot -Recurse -Force
    }

    $installedVersion = ""
    if (Test-Path -LiteralPath $UvExe -PathType Leaf) {
        $installedVersion = (& $UvExe --version 2>$null)
    }
    if (-not ($installedVersion -like "uv $UvVersion*")) {
        Write-Host ""
        Write-Host "1/3 필요한 빌드 도구를 준비합니다. 처음 한 번만 인터넷을 사용합니다."
        if (Test-Path -LiteralPath $UvRoot) {
            Remove-Item -LiteralPath $UvRoot -Recurse -Force
        }
        New-Item -ItemType Directory -Path $UvRoot -Force | Out-Null
        $env:UV_UNMANAGED_INSTALL = $UvRoot
        $env:UV_NO_MODIFY_PATH = "1"
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $installer = Invoke-RestMethod "https://astral.sh/uv/$UvVersion/install.ps1"
        Invoke-Expression $installer
        if (-not (Test-Path -LiteralPath $UvExe -PathType Leaf)) {
            throw "필요한 빌드 도구를 준비하지 못했습니다. 인터넷 연결을 확인해 주세요."
        }
    }
    else {
        Write-Host ""
        Write-Host "1/3 필요한 빌드 도구가 준비되어 있습니다."
    }

    if (Test-Path -LiteralPath $LogPath) {
        Remove-Item -LiteralPath $LogPath -Force
    }
    Write-Host "2/3 PDF를 확인하고 한자 카드 2,337개를 만듭니다."
    Write-Host "창을 닫지 말고 기다려 주세요."
    Write-Host ""

    Push-Location $Root
    $transcriptStarted = $false
    try {
        Start-Transcript -Path $LogPath -Force | Out-Null
        $transcriptStarted = $true
        $previousErrorAction = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $UvExe run --locked --python 3.13 python src/build_kanji_addon.py `
            --upper-pdf $UpperPdf `
            --lower-pdf $LowerPdf `
            --asset-root (Join-Path $Root "assets") `
            --output-root $OutputRoot
        $buildExitCode = $LASTEXITCODE
        $ErrorActionPreference = $previousErrorAction
    }
    finally {
        if ($transcriptStarted) {
            Stop-Transcript | Out-Null
        }
        Pop-Location
    }

    if ($buildExitCode -ne 0) {
        throw "한자 확장을 만들지 못했습니다. 선택한 PDF와 오류 내용을 확인해 주세요."
    }

    $BuildReportPath = Join-Path $OutputRoot "kanji-addon-build-report.json"
    if (-not (Test-Path -LiteralPath $BuildReportPath -PathType Leaf)) {
        throw "완성 파일 정보를 찾지 못했습니다."
    }
    $BuildReport = Get-Content -LiteralPath $BuildReportPath -Raw -Encoding UTF8 |
        ConvertFrom-Json
    $PackageName = [string]$BuildReport.apkg
    if (
        [string]::IsNullOrWhiteSpace($PackageName) -or
        [IO.Path]::GetFileName($PackageName) -ne $PackageName
    ) {
        throw "완성 파일 정보가 올바르지 않습니다."
    }
    $Package = Join-Path $OutputRoot $PackageName
    if (-not (Test-Path -LiteralPath $Package -PathType Leaf)) {
        throw "완성된 APKG를 찾지 못했습니다."
    }

    Write-Host ""
    Write-Host "3/3 한자 확장을 완성했습니다."
    Start-Process -FilePath "explorer.exe" -ArgumentList @($OutputRoot)
    [System.Windows.Forms.MessageBox]::Show(
        "한자 확장을 완성했습니다.`n열린 폴더의 $PackageName 파일을 Anki에 가져오세요.",
        "JLPT MAX 한자 확장",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    ) | Out-Null
    exit 0
}
catch {
    Write-Host ""
    Write-Host "오류: $($_.Exception.Message)" -ForegroundColor Red
    $detail = "한자 확장을 만들지 못했습니다.`n$($_.Exception.Message)"
    if (Test-Path -LiteralPath $LogPath -PathType Leaf) {
        $detail += "`n`n자세한 내용: $LogPath"
    }
    Show-BuilderError $detail
    exit 1
}
