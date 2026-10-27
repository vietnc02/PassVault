# Removes the installed app, shortcuts and browser registration.
# The vault (%APPDATA%\PassVault) is kept unless the user deletes it.
$ErrorActionPreference = 'Stop'
$dest = Join-Path $env:LOCALAPPDATA 'Programs\PassVault'
$hostName = 'com.passvault.host'

if (Get-Process -Name PassVault -ErrorAction SilentlyContinue) {
    Write-Host 'PassVault đang chạy. Hãy đóng app rồi chạy lại.' -ForegroundColor Red
    exit 1
}

foreach ($key in "HKCU:\Software\Google\Chrome\NativeMessagingHosts\$hostName",
                 "HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\$hostName") {
    if (Test-Path $key) { Remove-Item $key -Force }
}
foreach ($dir in [Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs')) {
    $link = Join-Path $dir 'PassVault.lnk'
    if (Test-Path $link) { Remove-Item $link -Force }
}
Set-Location $env:TEMP  # don't hold a handle on the folder being removed
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }

Write-Host 'Đã gỡ PassVault.' -ForegroundColor Green
Write-Host "Kho mật khẩu vẫn còn ở $env:APPDATA\PassVault (xóa thủ công nếu không cần)."
Write-Host 'Nhớ gỡ extension PassVault trong chrome://extensions.'
