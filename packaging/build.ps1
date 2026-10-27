# Builds build\PassVault-<version>-windows.zip:
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$out = Join-Path $root 'build'
$version = & $python -c "import sys; sys.path.insert(0, r'$root'); import passvault; print(passvault.__version__)"

& $python -m pip install -q -r (Join-Path $root 'requirements.txt') pyinstaller
& $python -m PyInstaller --noconfirm --clean --log-level WARN `
    --distpath "$out\dist" --workpath "$out\work" (Join-Path $PSScriptRoot 'PassVault.spec')
if ($LASTEXITCODE) { throw 'PyInstaller failed' }

$app = Join-Path $out 'dist\PassVault'
Copy-Item (Join-Path $root 'extension') $app -Recurse -Force
Copy-Item (Join-Path $PSScriptRoot 'install.bat'), (Join-Path $PSScriptRoot 'uninstall.bat') $app -Force
# Windows PowerShell 5.1 only reads Vietnamese text in scripts correctly with a BOM.
$bom = New-Object Text.UTF8Encoding $true
foreach ($name in 'install.ps1', 'uninstall.ps1', 'HUONG-DAN.txt') {
    [IO.File]::WriteAllText((Join-Path $app $name), [IO.File]::ReadAllText((Join-Path $PSScriptRoot $name)), $bom)
}

$zip = Join-Path $out "PassVault-$version-windows.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path $app -DestinationPath $zip
Write-Output "Built $zip ($([math]::Round((Get-Item $zip).Length / 1MB, 1)) MB)"
