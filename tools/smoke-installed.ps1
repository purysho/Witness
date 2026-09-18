param(
    [Parameter(Mandatory = $true)]
    [string]$Installer
)

$ErrorActionPreference = "Stop"

$installerPath = (Resolve-Path $Installer).Path
$root = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }
$installDir = Join-Path $root ("witness-installed-smoke-" + [Guid]::NewGuid().ToString("N"))

Write-Host "Installing $installerPath to $installDir"
$install = Start-Process -FilePath $installerPath -ArgumentList @("/S", "/D=$installDir") -Wait -PassThru
if ($install.ExitCode -ne 0) {
    throw "Witness NSIS installer exited with code $($install.ExitCode)"
}

if (-not (Test-Path $installDir)) {
    throw "Witness installer did not create $installDir"
}

$engine = Get-ChildItem -Path $installDir -Recurse -File -Filter "witness-engine.exe" | Select-Object -First 1
if (-not $engine) {
    throw "Installed Witness package does not contain witness-engine.exe"
}

$app = Get-ChildItem -Path $installDir -Recurse -File -Filter "*.exe" | Where-Object {
    $_.Name -ne "witness-engine.exe" -and $_.Name -notmatch "uninstall"
} | Sort-Object Length -Descending | Select-Object -First 1
if (-not $app) {
    throw "Could not locate the installed Witness desktop executable"
}

$readyFile = Join-Path $root ("witness-engine-ready-" + [Guid]::NewGuid().ToString("N") + ".txt")
$previousReadyFile = $env:WITNESS_SMOKE_READY_FILE
$env:WITNESS_SMOKE_READY_FILE = $readyFile

Write-Host "Launching installed desktop: $($app.FullName)"
$appProcess = Start-Process -FilePath $app.FullName -WorkingDirectory $installDir -PassThru

$deadline = [DateTime]::UtcNow.AddSeconds(60)
try {
    while ([DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 500
        $appProcess.Refresh()
        if ($appProcess.HasExited) {
            throw "Installed Witness desktop exited before engine readiness (code $($appProcess.ExitCode))"
        }
        if (Test-Path $readyFile) {
            $ready = (Get-Content $readyFile -Raw).Trim()
            if ($ready -like "engine-rpc-ready:*") {
                Write-Host "Installed app completed bundled-engine RPC: $ready"
                break
            }
        }
    }

    if (-not (Test-Path $readyFile)) {
        throw "Installed Witness desktop did not complete a bundled-engine RPC within the smoke window"
    }
}
finally {
    if ($appProcess -and -not $appProcess.HasExited) {
        Stop-Process -Id $appProcess.Id -Force -ErrorAction SilentlyContinue
        $appProcess.WaitForExit(5000) | Out-Null
    }
    Remove-Item -Force $readyFile -ErrorAction SilentlyContinue
    if ($null -eq $previousReadyFile) {
        Remove-Item Env:WITNESS_SMOKE_READY_FILE -ErrorAction SilentlyContinue
    } else {
        $env:WITNESS_SMOKE_READY_FILE = $previousReadyFile
    }
}

$uninstaller = Get-ChildItem -Path $installDir -Recurse -File -Filter "*uninstall*.exe" | Select-Object -First 1
if ($uninstaller) {
    Write-Host "Uninstalling smoke package: $($uninstaller.FullName)"
    $uninstall = Start-Process -FilePath $uninstaller.FullName -ArgumentList "/S" -Wait -PassThru
    if ($uninstall.ExitCode -ne 0) {
        throw "Witness uninstaller exited with code $($uninstall.ExitCode)"
    }
} else {
    Write-Warning "No uninstaller was found; removing smoke directory directly."
    Remove-Item -Recurse -Force $installDir -ErrorAction SilentlyContinue
}

Write-Host "Installed Witness package smoke passed."
