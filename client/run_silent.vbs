' Launches tracker.py with no console window.
' Place a shortcut to this file in:
'   shell:startup   (current user auto-start)
'   shell:common startup  (all users)

Dim tracker_dir
tracker_dir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)

Dim shell
Set shell = CreateObject("WScript.Shell")
shell.Run "pythonw """ & tracker_dir & "\tracker.py""", 0, False
