Set WshShell = CreateObject("WScript.Shell")
WshShell.Run chr(34) & "D:\SalesManager\run_app.bat" & chr(34), 0
Set WshShell = Nothing
