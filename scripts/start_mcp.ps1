param(
    [ValidateSet('original','iter3','iter5','smoke','smoke-iter3','smoke-iter5')][string]$Stage = 'smoke',
    [int]$Port = 3050
)
$projectRoot = Split-Path -Parent $PSScriptRoot
$configPath = Join-Path $projectRoot "config\local\$Stage.json"
if (-not (Test-Path -LiteralPath $configPath)) { throw "Missing config: $configPath" }
Set-Location -LiteralPath $projectRoot
$runtimeDir = Join-Path $projectRoot "config\local\runtime-$Stage"
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
$runtimeConfig = Join-Path $runtimeDir 'mcp.json'
Copy-Item -LiteralPath $configPath -Destination $runtimeConfig
& "$projectRoot\.runtime\node_modules\.bin\1mcp.cmd" serve --host 127.0.0.1 --port $Port --config $runtimeConfig --config-dir $runtimeDir --log-level info
