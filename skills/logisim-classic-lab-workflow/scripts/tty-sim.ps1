<#
.SYNOPSIS
  Run a Logisim-HUST circuit headlessly (-tty) and report the result.

.DESCRIPTION
  Wraps: java -jar logisim-hust-20200118.exe -tty <format> <circuit>
  - injects -Dsun.stdout.encoding=UTF-8 so Chinese output is readable
  - always enforces a timeout (tty mode never exits without a 'halt' pin)
  - reports whether it halted by halt pin / oscillation / timeout

.PARAMETER Circuit
  Path to the .circ file to simulate.

.PARAMETER Format
  -tty format, comma-separated: table,speed,tty,halt,stats,few
  Accepts either -Format table,halt (PowerShell array) or -Format 'table,halt'.
  Default: table,halt,stats

.PARAMETER TimeoutSec
  Seconds before the simulation is killed. Default 30.

.EXAMPLE
  .\tty-sim.ps1 -Circuit .\lab.circ -Format table,halt -TimeoutSec 20
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Circuit,
    [string[]]$Format = @('table', 'halt', 'stats'),
    [ValidateRange(1, 300)][int]$TimeoutSec = 30,
    [string]$LogisimExe = $env:LOGISIM_HUST_EXE,
    [string]$JavaExe = $env:LOGISIM_MCP_JAVA,
    [string]$RamImage = '',
    [ValidateRange(1, 67108864)][int]$MaxOutputBytes = 4194304
)

$ErrorActionPreference = 'Stop'
$parts = @(($Format -join ',') -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
if (-not $parts.Count -or @($parts | Where-Object { $_ -notin @('table','speed','tty','halt','stats','few') }).Count) {
    throw '无效的 -tty 格式'
}
if (-not @($parts | Where-Object { $_ -ne 'few' }).Count) { throw 'few 不能单独使用' }
$fmt = $parts -join ','

if (-not $LogisimExe) {
    $LogisimExe = $env:LOGISIM_HUST_EXE
}
if (-not (Test-Path -LiteralPath $LogisimExe -PathType Leaf)) {
    throw "找不到 Logisim-HUST 程序: $LogisimExe (可用 -LogisimExe 或 `$env:LOGISIM_HUST_EXE 指定)"
}

$circ = (Resolve-Path -LiteralPath $Circuit).Path
if (-not (Test-Path -LiteralPath $circ -PathType Leaf)) { throw 'Circuit 必须是文件' }
if ($RamImage) { $RamImage = (Resolve-Path -LiteralPath $RamImage).Path }

if (-not $JavaExe) {
    if ($env:JAVA_HOME -and (Test-Path (Join-Path $env:JAVA_HOME 'bin\java.exe'))) {
        $JavaExe = Join-Path $env:JAVA_HOME 'bin\java.exe'
    }
    else {
        $JavaExe = (Get-Command java -ErrorAction Stop).Source
    }
}
if (-not (Test-Path -LiteralPath $JavaExe -PathType Leaf)) { throw "找不到 Java: $JavaExe" }

function Read-BoundedUtf8([string]$Path, [int]$Limit) {
    if (-not (Test-Path -LiteralPath $Path)) { return '' }
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $buffer = New-Object byte[] ([int][Math]::Min($stream.Length, $Limit))
        $offset = 0
        while ($offset -lt $buffer.Length) {
            $count = $stream.Read($buffer, $offset, $buffer.Length - $offset)
            if ($count -eq 0) { break }
            $offset += $count
        }
        return [System.Text.Encoding]::UTF8.GetString($buffer, 0, $offset)
    } finally {
        $stream.Dispose()
    }
}

$stdout = Join-Path $env:TEMP ('logisim-tty-' + [guid]::NewGuid().ToString('N') + '.out')
$stderr = Join-Path $env:TEMP ('logisim-tty-' + [guid]::NewGuid().ToString('N') + '.err')

$argList = @(
    '-Dsun.stdout.encoding=UTF-8',
    '-Dsun.stderr.encoding=UTF-8',
    '-jar', "`"$LogisimExe`"",
    '-tty', $fmt
)
if ($RamImage) { $argList += @('-load', "`"$RamImage`"") }
$argList += "`"$circ`""

Write-Host "[cmd] `"$JavaExe`" -jar `"$LogisimExe`" -tty $fmt `"$circ`"" -ForegroundColor DarkGray

$proc = $null
$simulationExitCode = 1
try {
    $proc = Start-Process -FilePath $JavaExe -ArgumentList $argList -WindowStyle Hidden `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    # Cache the native handle before exit; Windows PowerShell 5 otherwise
    # sometimes loses ExitCode for a Start-Process -PassThru process.
    $null = $proc.Handle
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    $timedOut = $false
    $outputLimited = $false
    while (-not $proc.WaitForExit(100)) {
        $length = (Get-Item -LiteralPath $stdout).Length + (Get-Item -LiteralPath $stderr).Length
        if ($length -gt $MaxOutputBytes) { $outputLimited = $true; break }
        if ($watch.Elapsed.TotalSeconds -ge $TimeoutSec) { $timedOut = $true; break }
    }
    if ($timedOut -or $outputLimited) {
        $proc.Kill()
        if (-not $proc.WaitForExit(10000)) { throw 'kill 后仿真进程仍未退出' }
    }
    $proc.Refresh()
    $text = Read-BoundedUtf8 $stdout $MaxOutputBytes
    $errText = Read-BoundedUtf8 $stderr $MaxOutputBytes
    $length = (Get-Item -LiteralPath $stdout).Length + (Get-Item -LiteralPath $stderr).Length
    $outputLimited = $outputLimited -or $length -gt $MaxOutputBytes
    Write-Output '===== 仿真输出 ====='
    if ($text.Trim()) { Write-Output $text } else { Write-Output '(无输出)' }
    if ($errText.Trim()) {
        Write-Output '===== stderr ====='
        Write-Output $errText
    }
    if ($outputLimited) {
        $verdict = "OUTPUT LIMIT ($($MaxOutputBytes) bytes，结果可能不完整)"
        $simulationExitCode = 125
    } elseif ($timedOut) {
        $verdict = "TIMEOUT after $($TimeoutSec)s（halt 未触发或加载未完成）"
        $simulationExitCode = 124
    } elseif ($text -match 'halted due to detected oscillation') {
        $verdict = 'HALTED by oscillation（检测到震荡）'
        $simulationExitCode = 2
    } elseif ($proc.ExitCode -ne 0) {
        $verdict = "ERROR (code $($proc.ExitCode))"
        $simulationExitCode = 1
    } elseif ($text -match 'halted due to halt pin') {
        $verdict = 'HALTED by halt pin（停止信号已触发，输出仍须对照预期）'
        $simulationExitCode = 0
    } else {
        $verdict = 'EXITED (code 0，未观察到明确停机原因)'
        $simulationExitCode = 0
    }
    Write-Output '===== 结论 ====='
    Write-Output $verdict
} finally {
    if ($proc) {
        if (-not $proc.HasExited) { $proc.Kill(); $proc.WaitForExit(10000) | Out-Null }
        $proc.Dispose()
    }
    Remove-Item -LiteralPath $stdout, $stderr -Force -ErrorAction SilentlyContinue
}
exit $simulationExitCode
