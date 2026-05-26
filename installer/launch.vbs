Option Explicit

Dim WShell, FSO, script_dir, python_exe, app_py
Dim base_port, max_port, port, p, oExec, strResult

Set WShell = CreateObject("WScript.Shell")
Set FSO    = CreateObject("Scripting.FileSystemObject")

script_dir = FSO.GetParentFolderName(WScript.ScriptFullName) & "\"
python_exe = script_dir & ".venv\Scripts\python.exe"
app_py     = script_dir & "app.py"
base_port  = 8502
max_port   = 8510

' ── Sanity check ────────────────────────────────────────────────────────────
If Not FSO.FileExists(python_exe) Then
    MsgBox "Trade Log is not set up yet." & vbCrLf & vbCrLf & _
           "Please run  'INSTALL - Double-Click This First.bat'  first.", _
           vbExclamation, "Trade Log"
    WScript.Quit
End If

' ── Snapshot current port usage ─────────────────────────────────────────────
Set oExec = WShell.Exec("netstat -an")
strResult = oExec.StdOut.ReadAll

' ── Find first free port ─────────────────────────────────────────────────────
port = 0
For p = base_port To max_port
    If InStr(strResult, ":" & p) = 0 Then
        port = p
        Exit For
    End If
Next

If port = 0 Then
    MsgBox "Could not find a free port between " & base_port & " and " & max_port & "." & vbCrLf & vbCrLf & _
           "Please close some other applications and try again.", _
           vbExclamation, "Trade Log"
    WScript.Quit
End If

' ── Start Streamlit (hidden window — no terminal visible) ────────────────────
WShell.Run "cmd /c """ & python_exe & """ -m streamlit run """ & _
           app_py & """ --server.port " & port & _
           " --server.headless true > nul 2>&1", 0, False
WScript.Sleep 4000

' ── Open browser ─────────────────────────────────────────────────────────────
WShell.Run "http://localhost:" & port
