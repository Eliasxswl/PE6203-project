#Requires -Version 7.0
<#
.SYNOPSIS
    Role 3 independent verification: diff the live tools/list catalogs across
    the three MCPEvol-Bench stages (original / iter3 / iter5).

.DESCRIPTION
    Reads the judge_catalog blocks recorded in a pilot run's records.json and
    produces a server-level diff (added / removed / description / parameter)
    between stages. Labels are derived from real catalogs only; the public
    mutation records are intentionally not used (they do not match the live
    snapshots).

    Place this script at scripts/verification/verify_catalogs.ps1 in the repo.
    It then locates the repository root automatically; every path can be
    overridden with a parameter.

.PARAMETER RepoRoot
    Repository root. Defaults to two directories above this script
    (scripts/verification -> repo root).

.PARAMETER RecordsPath
    Path to a run's records.json. Defaults to the archived pilot run
    results/20261015T045814.065101Z_Kevin/records.json under RepoRoot.

.PARAMETER TaskIds
    Task ids whose trajectories carry the judge_catalog blocks to merge.
    The archived pilot covered 9, 24, 117, 273, 403.

.PARAMETER Strategy
    Strategy prefix in the trajectory keys. Catalogs are strategy-independent;
    no_update is used by default.

.PARAMETER Repeat
    Repeat index used in the trajectory keys (default 0).

.PARAMETER OutputPath
    Optional file to write the diff report to (written as UTF-8 text).

.EXAMPLE
    pwsh scripts/verification/verify_catalogs.ps1

.EXAMPLE
    pwsh scripts/verification/verify_catalogs.ps1 -RepoRoot D:\PE6203-project `
        -OutputPath docs/role3/evidence/catalog_diff.txt
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..' '..')).Path,
    [string]$RecordsPath,
    [int[]]$TaskIds = @(9, 24, 117, 273, 403),
    [string]$Strategy = 'no_update',
    [int]$Repeat = 0,
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'
$stages = @('original', 'iter3', 'iter5')

if (-not (Test-Path (Join-Path $RepoRoot 'config/experiment.json'))) {
    throw "RepoRoot '$RepoRoot' does not look like the project root (config/experiment.json not found). Pass -RepoRoot explicitly."
}
if (-not $RecordsPath) {
    $RecordsPath = Join-Path $RepoRoot 'results/20261015T045814.065101Z_Kevin/records.json'
}
if (-not (Test-Path $RecordsPath)) {
    throw "records.json not found at '$RecordsPath'. Pass -RecordsPath explicitly."
}

$report = New-Object System.Collections.Generic.List[string]
function Add-Line([string]$text) {
    $script:report.Add($text)
    Write-Output $text
}

$j = Get-Content $RecordsPath -Raw | ConvertFrom-Json

function Get-Signature($entry) {
    $entry.description + '|' + ($entry.inputSchema | ConvertTo-Json -Depth 20 -Compress)
}

# stage -> server::tool -> catalog entry; consistency is checked across tasks
$stageCat = @{}
foreach ($s in $stages) {
    $merged = @{}
    foreach ($t in $TaskIds) {
        $key = "$Strategy/$s/$t/$Repeat"
        $tr = $j.trajectories.$key
        if (-not $tr) { Add-Line "MISSING $key"; continue }
        foreach ($prop in $tr.judge_catalog.PSObject.Properties) {
            $e = $prop.Value
            if ($merged.ContainsKey($prop.Name)) {
                if ((Get-Signature $merged[$prop.Name]) -ne (Get-Signature $e)) {
                    Add-Line "INCONSISTENT within $s : $($prop.Name) (task $t)"
                }
            } else { $merged[$prop.Name] = $e }
        }
    }
    $stageCat[$s] = $merged
    Add-Line ("stage {0}: {1} catalog entries" -f $s, $merged.Count)
}

function Split-ByServer($cat) {
    $h = @{}
    foreach ($k in $cat.Keys) {
        $i = $k.IndexOf('::')
        $srv = $k.Substring(0, $i)
        $tool = $k.Substring($i + 2)
        if (-not $h.ContainsKey($srv)) { $h[$srv] = @{} }
        $h[$srv][$tool] = $cat[$k]
    }
    return $h
}

$byStage = @{}
foreach ($s in $stages) { $byStage[$s] = Split-ByServer $stageCat[$s] }

$servers = @()
foreach ($s in $stages) { $servers += $byStage[$s].Keys }
$servers = $servers | Sort-Object -Unique

foreach ($srv in $servers) {
    Add-Line ("=== {0} ===" -f $srv)
    $sets = @{}
    foreach ($s in $stages) {
        if ($byStage[$s].ContainsKey($srv)) { $sets[$s] = @($byStage[$s][$srv].Keys) }
        else { Add-Line "  [$s] SERVER ABSENT" }
    }
    $all = @()
    foreach ($s in $stages) { if ($sets.ContainsKey($s)) { $all += $sets[$s] } }
    $all = $all | Sort-Object -Unique

    foreach ($tool in $all) {
        $in = @{}
        foreach ($s in $stages) { $in[$s] = ($sets.ContainsKey($s) -and $sets[$s] -contains $tool) }
        if (-not $in['original']) {
            Add-Line ("  + ADDED later: iter3={0} iter5={1} : {2}" -f $in['iter3'], $in['iter5'], $tool)
            continue
        }
        if (-not $in['iter5']) {
            Add-Line ("  - REMOVED by iter5 (present iter3={0}) : {1}" -f $in['iter3'], $tool)
            continue
        }
        if (-not $in['iter3']) {
            Add-Line ("  ? present original+iter5 but not iter3 : {0}" -f $tool)
            continue
        }
        $e0 = $byStage['original'][$srv][$tool]
        $e3 = $byStage['iter3'][$srv][$tool]
        $e5 = $byStage['iter5'][$srv][$tool]
        if ((Get-Signature $e0) -eq (Get-Signature $e3) -and (Get-Signature $e3) -eq (Get-Signature $e5)) { continue }
        $parts = @()
        foreach ($pair in @(@('iter3', $e3), @('iter5', $e5))) {
            $lab = $pair[0]
            $ee = $pair[1]
            $ch = @()
            if ($ee.description -ne $e0.description) { $ch += 'DESC' }
            if (($ee.inputSchema | ConvertTo-Json -Depth 20 -Compress) -ne
                ($e0.inputSchema | ConvertTo-Json -Depth 20 -Compress)) { $ch += 'PARAM' }
            if ($ch.Count) { $parts += ("{0}:{1}" -f $lab, ($ch -join '+')) }
        }
        Add-Line ("  ~ {0}  {1}" -f $tool, ($parts -join '  '))
    }
}

if ($OutputPath) {
    $out = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputPath)
    $report -join [Environment]::NewLine | Set-Content -Path $out -Encoding utf8
    Write-Output ""
    Write-Output "Report written to $out"
}
