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

Write-Host "Launching installed desktop: $($app.FullName)"
$appProcess = Start-Process -FilePath $app.FullName -WorkingDirectory $installDir -PassThru

$engineProcess = $null
$deadline = [DateTime]::UtcNow.AddSeconds(30)
try {
    while ([DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Seconds 1
        $appProcess.Refresh()
        if ($appProcess.HasExited) {
            throw "Installed Witness desktop exited before engine startup (code $($appProcess.ExitCode))"
        }

        $engineProcess = Get-Process -ErrorAction SilentlyContinue | Where-Object {
            try {
                $_.Path -and ([IO.Path]::GetFullPath($_.Path) -eq [IO.Path]::GetFullPath($engine.FullName))
            } catch {
                $false
            }
        } | Select-Object -First 1
        if ($engineProcess) { break }
    }

    if (-not $engineProcess) {
        throw "Installed Witness desktop did not start its bundled engine within the smoke window"
    }

    Write-Host "Installed app started bundled engine PID $($engineProcess.Id)"
}
finally {
    if ($appProcess -and -not $appProcess.HasExited) {
        Stop-Process -Id $appProcess.Id -Force -ErrorAction SilentlyContinue
        $appProcess.WaitForExit(5000) | Out-Null
    }
    if ($engineProcess) {
        Stop-Process -Id $engineProcess.Id -Force -ErrorAction SilentlyContinue
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
