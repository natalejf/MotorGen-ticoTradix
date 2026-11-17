param([string]$SourceFile='ninjatrader\StratixChallengeCandleController.cs',[string]$OutputFile='ninjatrader\StratixController.compilecheck.dll',[string]$ManifestFile='ninjatrader\source_manifest.json')
$ErrorActionPreference='Stop'
$taskCustom=Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'NinjaTrader 8\bin\Custom'
$taskFramework='C:\Windows\Microsoft.NET\Framework64\v4.0.30319'
$taskRefs=@(
 'C:\Program Files\NinjaTrader 8\bin\NinjaTrader.Core.dll',
 'C:\Program Files\NinjaTrader 8\bin\NinjaTrader.Gui.dll',
 (Join-Path $taskCustom 'NinjaTrader.Custom.dll'),
 (Join-Path $taskFramework 'WPF\PresentationFramework.dll'),
 (Join-Path $taskFramework 'WPF\PresentationCore.dll'),
 (Join-Path $taskFramework 'WPF\WindowsBase.dll'),
 (Join-Path $taskFramework 'System.Xaml.dll'),
 (Join-Path $taskFramework 'System.ComponentModel.DataAnnotations.dll'))
$taskArgs=@('/nologo','/target:library','/platform:x64',('/out:'+$OutputFile)) +
 @($taskRefs | ForEach-Object { '/reference:' + $_ }) + @($SourceFile)
& (Join-Path $taskFramework 'csc.exe') @taskArgs 2>&1 | Tee-Object -FilePath '.\reports\ninja_compile.log'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$taskManifest=Get-Content -LiteralPath $ManifestFile -Raw | ConvertFrom-Json
$taskManifest | Add-Member -NotePropertyName native_compile_status -NotePropertyValue 'COMPILECHECK_OK_NT8_REFERENCES_RUNTIME_PENDING' -Force
$taskManifest | Add-Member -NotePropertyName compile_checked_at -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
$taskManifest | Add-Member -NotePropertyName integrated_sha256 -NotePropertyValue ((Get-FileHash -LiteralPath $SourceFile -Algorithm SHA256).Hash.ToLower()) -Force
$taskManifest | ConvertTo-Json | Set-Content -LiteralPath $ManifestFile -Encoding utf8
Write-Output 'Compilación aislada con referencias de NinjaTrader: OK. No se instaló ni activó el assembly.'
