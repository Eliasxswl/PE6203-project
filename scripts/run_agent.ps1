param(
    [string]$Config = 'config/experiment.json',
    [string]$Resume,
    [switch]$Offline,
    [switch]$Parallel,
    [int]$Workers = 2
)
# Compatibility wrapper; all experimental behavior belongs to the Python entry point.
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$interpreter = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $interpreter)) {
    $interpreter = (Get-Command python -ErrorAction Stop).Source
}
$runArgs = @('-m', 'custom.experiment', 'run', '--config', $Config)
if ($Resume) { $runArgs += @('--resume', $Resume) }
if ($Offline) { $runArgs += '--offline' }
if ($Parallel) { $runArgs += @('--parallel', '--workers', "$Workers") }
& $interpreter @runArgs
exit $LASTEXITCODE
