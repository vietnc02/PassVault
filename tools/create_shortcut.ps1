# Creates a "PassVault" shortcut on the current user's Desktop.
$project = Split-Path -Parent $PSScriptRoot
$desktop = [Environment]::GetFolderPath('Desktop')

$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path $desktop 'PassVault.lnk'))
$link.TargetPath = Join-Path $project '.venv\Scripts\pythonw.exe'
$link.Arguments = '-m passvault.app'
$link.WorkingDirectory = $project
$link.IconLocation = (Join-Path $project 'assets\passvault.ico') + ',0'
$link.Description = 'PassVault password manager'
$link.Save()
Write-Output "Created $(Join-Path $desktop 'PassVault.lnk')"
