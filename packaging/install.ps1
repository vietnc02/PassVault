# Installs PassVault for the current Windows user (no admin needed):
# copies the app, registers the Chrome/Edge autofill bridge, and adds
# Desktop + Start Menu shortcuts. Vault data in %APPDATA%\PassVault is untouched.
$ErrorActionPreference = 'Stop'
$src = $PSScriptRoot
$dest = Join-Path $env:LOCALAPPDATA 'Programs\PassVault'
$hostName = 'com.passvault.host'

if (Get-Process -Name PassVault -ErrorAction SilentlyContinue) {
    Write-Host 'PassVault đang chạy. Hãy đóng app rồi chạy lại install.bat.' -ForegroundColor Red
    exit 1
}

# 1. Copy the app (skip when re-running from the installed folder).
if ((Resolve-Path $src).Path.TrimEnd('\') -ne $dest.TrimEnd('\')) {
    if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
    New-Item -ItemType Directory -Force $dest | Out-Null
    Copy-Item (Join-Path $src '*') $dest -Recurse -Force
}

# 2. Register the native messaging host. Chrome derives an unpacked
#    extension's ID from the public key in its manifest.
$manifest = Get-Content (Join-Path $dest 'extension\manifest.json') -Raw | ConvertFrom-Json
$hash = [System.Security.Cryptography.SHA256]::Create().ComputeHash([Convert]::FromBase64String($manifest.key))
$extId = -join ($hash[0..15] | ForEach-Object { [char](97 + ($_ -shr 4)); [char](97 + ($_ -band 15)) })

$hostManifest = Join-Path $dest "$hostName.json"
$json = [ordered]@{
    name            = $hostName
    description     = 'PassVault autofill bridge'
    path            = (Join-Path $dest 'passvault_host.exe')
    type            = 'stdio'
    allowed_origins = @("chrome-extension://$extId/")
} | ConvertTo-Json
# Chrome's parser rejects a UTF-8 BOM, so write without one.
[IO.File]::WriteAllText($hostManifest, $json, (New-Object Text.UTF8Encoding $false))

foreach ($key in "HKCU:\Software\Google\Chrome\NativeMessagingHosts\$hostName",
                 "HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\$hostName") {
    New-Item -Path $key -Value $hostManifest -Force | Out-Null
}

# 3. Shortcuts.
$shell = New-Object -ComObject WScript.Shell
foreach ($dir in [Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs')) {
    $link = $shell.CreateShortcut((Join-Path $dir 'PassVault.lnk'))
    $link.TargetPath = Join-Path $dest 'PassVault.exe'
    $link.WorkingDirectory = $dest
    $link.Save()
}

Write-Host ''
Write-Host 'Đã cài PassVault vào:' $dest -ForegroundColor Green
Write-Host 'Đã tạo shortcut PassVault trên Desktop và Start Menu.'
Write-Host ''
Write-Host 'Còn 1 bước để bật tự điền trên Chrome:' -ForegroundColor Yellow
Write-Host '  1. Mở chrome://extensions và bật "Developer mode"'
Write-Host '  2. Bấm "Load unpacked" và chọn thư mục:'
Write-Host "     $dest\extension"
Start-Process explorer.exe $dest
