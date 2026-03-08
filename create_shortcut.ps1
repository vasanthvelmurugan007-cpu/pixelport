$WshShell = New-Object -comObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$HOME\Desktop\Castify.lnk")
$Shortcut.TargetPath = "pythonw.exe"
$Shortcut.Arguments = "C:\Users\santo\.gemini\antigravity\scratch\screen_share\desktop_app.py"
$Shortcut.WorkingDirectory = "C:\Users\santo\.gemini\antigravity\scratch\screen_share"
$Shortcut.Save()
