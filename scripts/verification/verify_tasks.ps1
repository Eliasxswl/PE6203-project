#Requires -Version 7.0
<#
.SYNOPSIS
    Role 3 independent verification: classify each candidate task against its
    required tools in test_cases.json and the verified real-catalog change table.

.DESCRIPTION
    For the gate-passing task ids, recomputes required-tool counts from
    src/custom/data/test_cases/test_cases.json and labels each task CHANGED /
    CONTROL / UNLABELLED using the change table independently reproduced from
    the pilot judge_catalog (see verify_catalogs.ps1).

    Place this script at scripts/verification/verify_tasks.ps1 in the repo.
    It locates the repository root automatically; every path can be
    overridden with a parameter.

.PARAMETER RepoRoot
    Repository root. Defaults to two directories above this script
    (scripts/verification -> repo root).

.PARAMETER TestCasesPath
    Path to test_cases.json. Defaults to
    src/custom/data/test_cases/test_cases.json under RepoRoot.

.PARAMETER TaskIds
    Task ids to check. Defaults to the 25 gate-passing candidates
    (17 catalog-covered core + 8 extension).

.EXAMPLE
    pwsh scripts/verification/verify_tasks.ps1
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..' '..')).Path,
    [string]$TestCasesPath,
    [int[]]$TaskIds = @(
        9, 24, 117, 416,
        267, 271, 273, 274, 278, 386, 389, 390, 394, 403, 410, 411, 425,
        29, 102, 107, 114, 157, 320, 356, 358
    )
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path (Join-Path $RepoRoot 'config/experiment.json'))) {
    throw "RepoRoot '$RepoRoot' does not look like the project root (config/experiment.json not found). Pass -RepoRoot explicitly."
}
if (-not $TestCasesPath) {
    $TestCasesPath = Join-Path $RepoRoot 'src/custom/data/test_cases/test_cases.json'
}
if (-not (Test-Path $TestCasesPath)) {
    throw "test_cases.json not found at '$TestCasesPath'. Pass -TestCasesPath explicitly."
}

# Server-name aliases applied by src/custom/experiment/runtime.py ALIASES
$aliases = @{
    'server-sequential-thinking' = '@modelcontextprotocol/server-sequential-thinking'
    'mcp-server-time'            = '@guanxiong/mcp-server-time'
    'server-memory'              = '@guanxiong/server-memory'
    'pollinations/model-context-protocol' = '@pollinations/model-context-protocol'
}

# Verified change table from the pilot judge_catalog diff (run 20261015T045814).
# Value = @(change vs original at middle, change vs original at late);
# 'NONE' unchanged, 'ADDED' new tool (not required by any task when added),
# 'REMOVED' tool gone, 'ABSENT' tool not present at that stage.
$chg = @{
    '@kazuph/mcp-taskmanager::request_planning' = @('DESC+PARAM', 'DESC+PARAM')
    '@modelcontextprotocol/server-filesystem::read_text_file' = @('DESC+PARAM', 'DESC+PARAM')
    '@modelcontextprotocol/server-filesystem::read_file'       = @('NONE', 'REMOVED')
    '@modelcontextprotocol/server-filesystem::search_files'    = @('NONE', 'PARAM')
    '@modelcontextprotocol/server-sequential-thinking::sequentialthinking' = @('DESC', 'DESC+PARAM')
    '@modelcontextprotocol/server-sequential-thinking::parallel-thinking'  = @('ADDED', 'ADDED')
    '@modelcontextprotocol/server-sequential-thinking::convergent-synthesis' = @('ABSENT', 'ADDED')
}

# Servers whose live catalogs are already covered by pilot evidence
$covered = @(
    'mcp-shrimp-task-manager', 'mcp-tasks', '@kazuph/mcp-taskmanager',
    '@modelcontextprotocol/server-filesystem', '@modelcontextprotocol/server-sequential-thinking'
)

$tasks = Get-Content $TestCasesPath -Raw | ConvertFrom-Json
$byId = @{}
foreach ($t in $tasks) { $byId[[int]$t.idx] = $t }

foreach ($id in $TaskIds) {
    if (-not $byId.ContainsKey($id)) { Write-Output "$id : NOT FOUND"; continue }
    $t = $byId[$id]
    $rawServers = @($t.servers.PSObject.Properties.Name)
    $canonServers = $rawServers | ForEach-Object { $aliases[$_] ?? $_ }
    $nTools = 0
    $mid = @()
    $late = @()
    $unknown = @()

    foreach ($srv in $rawServers) {
        $canon = $aliases[$srv] ?? $srv
        foreach ($tool in $t.servers.$srv) {
            $nTools++
            $k = "$canon::$tool"
            if ($chg.ContainsKey($k)) {
                if ($chg[$k][0] -notin @('NONE', 'ADDED', 'ABSENT')) {
                    $mid += ("{0}:{1}" -f $tool, $chg[$k][0])
                }
                if ($chg[$k][1] -notin @('NONE', 'ADDED', 'ABSENT')) {
                    $late += ("{0}:{1}" -f $tool, $chg[$k][1])
                }
            }
            elseif ($canon -notin $covered) {
                $unknown += $canon
            }
        }
    }

    $unknown = $unknown | Sort-Object -Unique
    $status = if ($late.Count -or $mid.Count) { 'CHANGED' }
              elseif ($unknown.Count) { 'UNLABELLED(no catalog)' }
              else { 'CONTROL' }
    $line = "{0,3} | {1,-20} | n={2} | mid=[{3}] late=[{4}] | {5}" -f `
        $id, $status, $nTools, ($mid -join ','), ($late -join ','), ($canonServers -join ';')
    if ($unknown.Count) { $line += "  ?? no catalog: " + ($unknown -join ',') }
    Write-Output $line
}
