param(
    [string]$QgisRoot = 'C:\Program Files\QGIS 3.44.9',
    [ValidateSet('en_US', 'hu_HU', 'both')]
    [string]$Language = 'both'
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$launchers = @('python-qgis-ltr.bat', 'python-qgis.bat')
$launcherPath = $null
foreach ($name in $launchers) {
    $candidate = Join-Path $QgisRoot "bin\$name"
    if (Test-Path -LiteralPath $candidate) {
        $launcherPath = $candidate
        break
    }
}
if (-not $launcherPath) { throw "A QGIS Python-indítója nem található: $QgisRoot" }
$testPath = Join-Path $taskRoot 'tests\test_qgis.py'
$previousLanguage = $env:TOPOLOGY_TEST_LANGUAGE
$testExitCode = 0
try {
    $languages = if ($Language -eq 'both') { @('en_US', 'hu_HU') } else { @($Language) }
    foreach ($locale in $languages) {
        $env:TOPOLOGY_TEST_LANGUAGE = $locale
        & cmd /c "`"$launcherPath`" `"$testPath`""
        if ($LASTEXITCODE -ne 0) { $testExitCode = $LASTEXITCODE; break }
    }
}
finally {
    $env:TOPOLOGY_TEST_LANGUAGE = $previousLanguage
}
exit $testExitCode
