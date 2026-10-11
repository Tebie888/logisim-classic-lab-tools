param(
    [Parameter(Mandatory=$true)][string]$Docx,
    [Parameter(Mandatory=$true)][string]$OutputPdf
)
$ErrorActionPreference = 'Stop'
$taskSource = (Resolve-Path -LiteralPath $Docx).Path
$taskOutput = [IO.Path]::GetFullPath($OutputPdf)
if ([IO.Path]::GetExtension($taskSource) -ne '.docx') { throw 'Source must be .docx' }
if ([IO.Path]::GetExtension($taskOutput) -ne '.pdf') { throw 'Output must be .pdf' }
if (Test-Path -LiteralPath $taskOutput) { throw 'Output exists; no file was overwritten' }
$taskParent = [IO.Path]::GetDirectoryName($taskOutput)
if (-not (Test-Path -LiteralPath $taskParent -PathType Container)) { throw 'Output directory must exist' }
$taskBefore = (Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash
$taskTemporary = Join-Path $taskParent ('.word-render-' + [Guid]::NewGuid().ToString('N') + '.pdf')
$taskWord = $null
$taskDocument = $null
try {
    # Own a separate Word instance; never attach to or close the user's active documents.
    $taskWord = New-Object -ComObject Word.Application
    $taskWord.Visible = $false
    $taskWord.DisplayAlerts = 0
    $taskWord.AutomationSecurity = 3
    $taskDocument = $taskWord.Documents.Open($taskSource, $false, $true, $false)
    $taskDocument.ExportAsFixedFormat($taskTemporary, 17)
    $taskDocument.Close(0)
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($taskDocument)
    $taskDocument = $null
    if ((Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash -ne $taskBefore) { throw 'Source changed during rendering' }
    [IO.File]::Move($taskTemporary, $taskOutput)
    @{ source=$taskSource; pdf=$taskOutput; source_modified=$false; engine='Microsoft Word' } | ConvertTo-Json -Compress
} finally {
    if ($null -ne $taskDocument) {
        $taskDocument.Close(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($taskDocument)
    }
    if ($null -ne $taskWord) {
        $taskWord.Quit(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($taskWord)
    }
    if (Test-Path -LiteralPath $taskTemporary) { Remove-Item -LiteralPath $taskTemporary }
}
