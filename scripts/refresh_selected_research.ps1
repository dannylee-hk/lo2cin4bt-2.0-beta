param(
    [string]$Python = "D:\trading\lo2cin4bt-v2\.venv\Scripts\python.exe",
    [string]$Output = "D:\trading\lo2cin4bt-v2\workspace\reports\agents\lo2cin4bt_PM\2026-06-15_refresh_results.json"
)

$ErrorActionPreference = "Continue"
$results = @()

function Invoke-ResearchStep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $startedAt = Get-Date
    Push-Location $WorkingDirectory
    try {
        & $Python @Arguments
        $exitCode = $LASTEXITCODE
    }
    catch {
        $exitCode = 1
        Write-Error $_
    }
    finally {
        Pop-Location
    }

    $script:results += [ordered]@{
        name = $Name
        working_directory = $WorkingDirectory
        arguments = $Arguments
        started_at = $startedAt.ToString("o")
        finished_at = (Get-Date).ToString("o")
        exit_code = $exitCode
        status = if ($exitCode -eq 0) { "completed" } else { "failed" }
    }
}

Invoke-ResearchStep `
    -Name "parabolic-short-daily-gate" `
    -WorkingDirectory "D:\trading\strategies\research\parabolic-short" `
    -Arguments @(
        "parabolic_short_monitor.py",
        "--tickers",
        "SMCI,MU,SNDK",
        "--no-intraday"
    )

Invoke-ResearchStep `
    -Name "re-rate-full-refresh" `
    -WorkingDirectory "D:\trading\strategies\research\re-rate" `
    -Arguments @("rerate_screener.py")

Invoke-ResearchStep `
    -Name "btc-vrp-snapshot-append" `
    -WorkingDirectory "D:\trading\strategies\research\btc-covered-call-guide-2026" `
    -Arguments @(
        "download_free_option_chains.py",
        "deribit-panel-append",
        "--currency",
        "BTC",
        "--workers",
        "8"
    )

Invoke-ResearchStep `
    -Name "btc-vrp-panel-build" `
    -WorkingDirectory "D:\trading\strategies\research\btc-covered-call-guide-2026" `
    -Arguments @("btc_vrp_panel\build_btc_vrp_panel.py")

$outputPath = [System.IO.Path]::GetFullPath($Output)
[System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($outputPath)) | Out-Null
$results | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $outputPath

if ($results.exit_code -contains 1) {
    exit 1
}
