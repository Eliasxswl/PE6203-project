param(
    [Parameter(Mandatory=$true)][string]$TaskFile,
    [string]$OutputPath,
    [ValidateSet('original','iter3','iter5')][string]$Stage = 'original',
    [int]$Port = 3050,
    [string]$MutationPath,
    [string]$RunId = 'run-1'
)
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $projectRoot 'src'
$env:PYTHONUTF8 = '1'
Set-Location -LiteralPath "$projectRoot\src"
$runArgs = @('-m','custom.real_mcp.tool_level_test','--step','3','--test_case_file',$TaskFile,'--stage',$Stage,'--run_id',$RunId,'--mcp_server_url',"http://127.0.0.1:$Port/mcp")
if ($OutputPath) { $runArgs += @('--output_path',$OutputPath) }
if ($Stage -ne 'original') {
    $runArgs[3] = '4'
    if (-not $MutationPath) { throw 'Pass the verified -MutationPath for this stage and task subset.' }
    $runArgs += @('--mutation_path',$MutationPath)
}
& "$projectRoot\.venv\Scripts\python.exe" @runArgs
