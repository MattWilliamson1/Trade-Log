Option Explicit

Dim WShell, FSO, script_dir, python_exe, app_py, port, already_running

Set WShell = CreateObject("WScript.Shell")
Set FSO    = CreateObject("Scripting.FileSystemObject")

script_dir = FSO.GetParentFolderName(WScript.ScriptFullName) & "\"
python_exe = script_dir & ".venv\Scripts\python.exe"
app_py     = script_dir & "app.py"
port       = 8502

' ── Sanity check ────────────────────────────────────────────────────────────
If Not FSO.FileExists(python_exe) Then
    MsgBox "Trade Log is not set up yet." & vbCrLf & vbCrLf & _
           "Please run  'INSTALL - Double-Click This First.bat'  first.", _
           vbExclamation, "Trade Log"
    WScript.Quit
End If

' ── Check if Streamlit is already running on this port ──────────────────────
already_running = False
Dim oExec, strResult
Set oExec  = WShell.Exec("netstat -an")
strResult  = oExec.StdOut.ReadAll
If InStr(strResult, ":" & port) > 0 Then
    already_running = True
End If

' ── Start Streamlit if needed (hidden window — no terminal visible) ──────────
If Not already_running Then
    WShell.Run "cmd /c """ & python_exe & """ -m streamlit run """ & _
               app_py & """ --server.port " & port & _
               " --server.headless true > nul 2>&1", 0, False
    WScript.Sleep 4000
End If

' ── Open browser ─────────────────────────────────────────────────────────────
WShell.Run "http://localhost:" & port
