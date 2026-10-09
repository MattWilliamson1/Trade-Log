"""Keep the trade log in the cloud so it follows the student between computers.

The database is never opened from the cloud. SQLite in WAL mode spreads one
save across three files, and a sync client uploads them separately and
whenever it likes, so a live database in a Drive folder is a corrupted
database waiting to happen. Instead the app keeps working on its local file
exactly as before, and this module:

* on startup, pulls the cloud copy when it is newer than the local one;
* after changes, uploads a *snapshot* — one complete, consistent file taken
  with SQLite's backup API — never the live file;
* refuses to overwrite either side when both changed since the last sync,
  and hands that decision to the user;
* leaves a small lock file saying which computer has the log open, so a
  second computer can warn before it is edited in two places.

Two backends store the files: Google Drive, reached directly over its REST
API after a one-time browser sign-in (nothing to install), and any folder on
disk — which is how Dropbox, OneDrive, iCloud and Google Drive for desktop
all present themselves.

"Changed" is decided by content fingerprint, not timestamps: an unchanged
database snapshots to byte-identical bytes, so the MD5 of the snapshot is
compared with the MD5 recorded at the last sync. Google Drive reports the
MD5 of what it stores, so the remote side needs no download to compare.

Nothing here imports Streamlit. app.py owns the UI and the one operation
that needs the app — replacing the live database — and passes it in.
"""

from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import http.server
import io
import json
import os
import secrets
import shutil
import socket
import sqlite3
import tempfile
import threading
import time
import urllib.parse
import zipfile
from pathlib import Path
from typing import Callable

try:
    import requests
except Exception:          # pragma: no cover - requests ships in requirements
    requests = None

from db import DB_PATH, BACKUP_DIR

APP_DIR = Path(__file__).parent
DATA_DIR = DB_PATH.parent

# Per-install sync configuration and memory. Deliberately *not* in the
# database: pulling a database from the cloud would overwrite it.
STATE_PATH = DATA_DIR / "cloud_sync.json"
GDRIVE_TOKEN_PATH = DATA_DIR / "gdrive_token.json"

REMOTE_FOLDER = "Trade Log"
REMOTE_DB = "tradelog.db"
REMOTE_ATT = "attachments.zip"
REMOTE_LOCK = "trade-log-in-use.json"

ATTACHMENT_DIRS = ("attachments", "plan_attachments")

LOCK_STALE_MIN = 15        # a lock not refreshed for this long is abandoned
HEARTBEAT_SEC = 120
CHECK_SEC = 30

# ── Google OAuth client ────────────────────────────────────────────────────────
# A "Desktop app" OAuth client from the Trade Log Google Cloud project. For an
# installed app Google treats the secret as not secret (it ships inside every
# copy), and PKCE protects the sign-in. A google_oauth_client.json downloaded
# from the Cloud console and dropped beside this file overrides these.
GOOGLE_CLIENT_ID = ""
GOOGLE_CLIENT_SECRET = ""
GOOGLE_SCOPE = "https://www.googleapis.com/auth/drive.file"

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
_API = "https://www.googleapis.com/drive/v3"
_UPLOAD = "https://www.googleapis.com/upload/drive/v3"


def google_client() -> tuple[str, str]:
    p = APP_DIR / "google_oauth_client.json"
    if p.exists():
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
            j = j.get("installed") or j.get("web") or j
            return j.get("client_id", ""), j.get("client_secret", "")
        except Exception:
            pass
    return GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET


def google_configured() -> bool:
    return bool(google_client()[0]) and requests is not None


# ── Local state ───────────────────────────────────────────────────────────────

def machine_name() -> str:
    return socket.gethostname() or "this computer"


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(st: dict) -> None:
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_PATH)


def update_state(**kw) -> dict:
    with _state_lock:
        st = load_state()
        st.update(kw)
        save_state(st)
        return st


_state_lock = threading.RLock()


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _md5_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Snapshots ─────────────────────────────────────────────────────────────────

def snapshot_db(dest: Path) -> str:
    """Write a consistent copy of the live database to ``dest``; return its MD5.

    The backup API reads through the write-ahead log, so the copy includes
    every committed change without checkpointing or touching the live file,
    and an unchanged database always produces the same bytes.
    """
    src = sqlite3.connect(DB_PATH, timeout=15)
    try:
        dst = sqlite3.connect(dest)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return _md5_file(dest)


def local_db_md5() -> str | None:
    if not DB_PATH.exists():
        return None
    with tempfile.TemporaryDirectory() as td:
        return snapshot_db(Path(td) / "snap.db")


def _att_files() -> list[tuple[str, Path]]:
    out = []
    for d in ATTACHMENT_DIRS:
        root = APP_DIR / d          # where app.py saves them
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*")):
            if p.is_file():
                out.append((f"{d}/{p.relative_to(root).as_posix()}", p))
    return out


def attachments_signature() -> str:
    """Cheap change check (names + sizes + mtimes) before building a zip."""
    h = hashlib.md5()
    for rel, p in _att_files():
        s = p.stat()
        h.update(f"{rel}|{s.st_size}|{int(s.st_mtime)}\n".encode())
    return h.hexdigest()


def build_attachments_zip(dest: Path) -> str | None:
    """Zip every attachment deterministically (sorted, fixed timestamps) so
    the same files always give the same MD5. None when there are none."""
    files = _att_files()
    if not files:
        return None
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_STORED) as z:
        for rel, p in files:
            zi = zipfile.ZipInfo(rel, date_time=(2000, 1, 1, 0, 0, 0))
            z.writestr(zi, p.read_bytes())
    return _md5_file(dest)


def extract_attachments(zip_path: Path) -> int:
    """Add the cloud's attachments beside this install's. Never deletes: a
    file only this computer has survives and goes up with the next push."""
    n = 0
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            top, _, rest = name.partition("/")
            if top not in ATTACHMENT_DIRS or not rest or ".." in Path(rest).parts:
                continue
            target = APP_DIR / top / rest
            target.parent.mkdir(parents=True, exist_ok=True)
            data = z.read(name)
            if not target.exists() or target.read_bytes() != data:
                target.write_bytes(data)
                n += 1
    return n


def db_summary(path: Path) -> dict:
    """Trade count and newest entry, for showing the two sides of a choice."""
    try:
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            n = c.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
            last = c.execute("SELECT MAX(COALESCE(exit_date, entry_date)) FROM trades").fetchone()[0]
        finally:
            c.close()
        return {"trades": int(n or 0), "last": last}
    except Exception:
        return {"trades": None, "last": None}


# ── Backends ──────────────────────────────────────────────────────────────────

class SyncError(Exception):
    pass


class FolderBackend:
    """A folder on disk — usually one a cloud client keeps in sync."""

    kind = "folder"

    def __init__(self, folder: str):
        self.root = Path(folder).expanduser()

    def describe(self) -> str:
        return str(self.root)

    def _check(self):
        if not self.root.parent.exists():
            raise SyncError(f"Can't find {self.root.parent} — is the cloud drive running?")
        self.root.mkdir(parents=True, exist_ok=True)

    def info(self, name: str) -> dict | None:
        self._check()
        p = self.root / name
        if not p.exists():
            return None
        return {"md5": _md5_file(p),
                "modified": _dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")}

    def download(self, name: str, dest: Path) -> None:
        self._check()
        shutil.copyfile(self.root / name, dest)

    def upload(self, name: str, src: Path) -> dict:
        self._check()
        # Copy beside the target, then rename: the sync client never sees a
        # half-written file under the real name.
        tmp = self.root / f".{name}.uploading"
        shutil.copyfile(src, tmp)
        os.replace(tmp, self.root / name)
        return self.info(name)

    def read_json(self, name: str) -> dict | None:
        self._check()
        try:
            return json.loads((self.root / name).read_text(encoding="utf-8"))
        except Exception:
            return None

    def write_json(self, name: str, data: dict) -> None:
        self._check()
        tmp = self.root / f".{name}.uploading"
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, self.root / name)

    def delete(self, name: str) -> None:
        try:
            (self.root / name).unlink()
        except FileNotFoundError:
            pass


class GDriveBackend:
    """Google Drive over its REST API, limited to files Trade Log created."""

    kind = "gdrive"

    def __init__(self):
        self._folder_id = None
        self._ids: dict[str, str] = {}

    def describe(self) -> str:
        email = (load_gdrive_token() or {}).get("email")
        return f"Google Drive{f' ({email})' if email else ''} › {REMOTE_FOLDER}"

    # ── HTTP ──
    def _req(self, method: str, url: str, **kw):
        if requests is None:
            raise SyncError("The 'requests' library is missing.")
        tok = gdrive_access_token()
        headers = kw.pop("headers", {})
        headers["Authorization"] = f"Bearer {tok}"
        try:
            r = requests.request(method, url, headers=headers, timeout=60, **kw)
        except Exception as e:
            raise SyncError(f"Couldn't reach Google Drive ({e.__class__.__name__}).")
        if r.status_code == 401:
            # Access token rejected — refresh once and retry.
            tok = gdrive_access_token(force_refresh=True)
            headers["Authorization"] = f"Bearer {tok}"
            r = requests.request(method, url, headers=headers, timeout=60, **kw)
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", {}).get("message") or r.text[:200]
            except Exception:
                msg = r.text[:200]
            raise SyncError(f"Google Drive error {r.status_code}: {msg}")
        return r

    def _folder(self) -> str:
        if self._folder_id:
            return self._folder_id
        q = (f"name = '{REMOTE_FOLDER}' and mimeType = 'application/vnd.google-apps.folder' "
             "and trashed = false and 'root' in parents")
        r = self._req("GET", f"{_API}/files", params={"q": q, "fields": "files(id)",
                                                      "spaces": "drive"}).json()
        if r.get("files"):
            self._folder_id = r["files"][0]["id"]
        else:
            r = self._req("POST", f"{_API}/files", json={
                "name": REMOTE_FOLDER, "mimeType": "application/vnd.google-apps.folder"}).json()
            self._folder_id = r["id"]
        return self._folder_id

    def _find(self, name: str) -> dict | None:
        q = f"name = '{name}' and '{self._folder()}' in parents and trashed = false"
        r = self._req("GET", f"{_API}/files", params={
            "q": q, "fields": "files(id,md5Checksum,modifiedTime)",
            "orderBy": "modifiedTime desc", "spaces": "drive"}).json()
        files = r.get("files") or []
        if not files:
            self._ids.pop(name, None)
            return None
        self._ids[name] = files[0]["id"]
        return files[0]

    def info(self, name: str) -> dict | None:
        f = self._find(name)
        if not f:
            return None
        return {"md5": f.get("md5Checksum"), "modified": f.get("modifiedTime")}

    def download(self, name: str, dest: Path) -> None:
        f = self._find(name)
        if not f:
            raise SyncError(f"{name} isn't in Google Drive.")
        r = self._req("GET", f"{_API}/files/{f['id']}", params={"alt": "media"}, stream=True)
        with open(dest, "wb") as out:
            for chunk in r.iter_content(1 << 20):
                out.write(chunk)

    def _upload_bytes(self, name: str, data: bytes, mime: str) -> dict:
        fid = self._ids.get(name) or (self._find(name) or {}).get("id")
        params = {"uploadType": "resumable", "fields": "id,md5Checksum,modifiedTime"}
        if fid:
            r = self._req("PATCH", f"{_UPLOAD}/files/{fid}", params=params, json={})
        else:
            r = self._req("POST", f"{_UPLOAD}/files", params=params,
                          json={"name": name, "parents": [self._folder()]})
        session = r.headers.get("Location")
        if not session:
            raise SyncError("Google Drive didn't start the upload.")
        r = self._req("PUT", session, data=data, headers={"Content-Type": mime})
        j = r.json()
        self._ids[name] = j["id"]
        return {"md5": j.get("md5Checksum"), "modified": j.get("modifiedTime")}

    def upload(self, name: str, src: Path) -> dict:
        return self._upload_bytes(name, Path(src).read_bytes(), "application/octet-stream")

    def read_json(self, name: str) -> dict | None:
        f = self._find(name)
        if not f:
            return None
        try:
            return self._req("GET", f"{_API}/files/{f['id']}", params={"alt": "media"}).json()
        except Exception:
            return None

    def write_json(self, name: str, data: dict) -> None:
        self._upload_bytes(name, json.dumps(data).encode(), "application/json")

    def delete(self, name: str) -> None:
        f = self._find(name)
        if f:
            self._req("DELETE", f"{_API}/files/{f['id']}")
            self._ids.pop(name, None)


def backend_from_state(st: dict | None = None):
    st = load_state() if st is None else st
    if st.get("mode") == "gdrive" and load_gdrive_token():
        return GDriveBackend()
    if st.get("mode") == "folder" and st.get("folder"):
        return FolderBackend(st["folder"])
    return None


# ── Google sign-in (installed-app loopback flow with PKCE) ────────────────────

def load_gdrive_token() -> dict | None:
    try:
        return json.loads(GDRIVE_TOKEN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_gdrive_token(tok: dict) -> None:
    GDRIVE_TOKEN_PATH.write_text(json.dumps(tok), encoding="utf-8")


def gdrive_access_token(force_refresh: bool = False) -> str:
    tok = load_gdrive_token()
    if not tok or not tok.get("refresh_token"):
        raise SyncError("Not signed in to Google Drive.")
    if not force_refresh and tok.get("access_token") and tok.get("expires_at", 0) > time.time() + 60:
        return tok["access_token"]
    cid, secret = google_client()
    try:
        r = requests.post(_TOKEN_URL, data={
            "client_id": cid, "client_secret": secret,
            "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"}, timeout=30)
    except Exception as e:
        raise SyncError(f"Couldn't reach Google ({e.__class__.__name__}).")
    j = r.json() if r.content else {}
    if r.status_code != 200:
        if j.get("error") == "invalid_grant":
            raise SyncError("Google sign-in has expired or was revoked — reconnect Google Drive "
                            "in Settings → Cloud Sync.")
        raise SyncError(f"Google sign-in failed: {j.get('error_description') or j.get('error') or r.status_code}")
    tok["access_token"] = j["access_token"]
    tok["expires_at"] = time.time() + int(j.get("expires_in", 3600))
    _save_gdrive_token(tok)
    return tok["access_token"]


_signin: dict = {}     # the one sign-in in progress: state, verifier, port, result


class _Callback(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        ok = False
        if q.get("state", [""])[0] == _signin.get("state"):
            if "code" in q:
                _signin["code"] = q["code"][0]
                ok = True
            else:
                _signin["error"] = q.get("error", ["cancelled"])[0]
        body = ("<h2>Trade Log is connected to Google Drive.</h2><p>You can close this tab.</p>"
                if ok else "<h2>Google sign-in didn't complete.</h2><p>Close this tab and try "
                "again from Trade Log.</p>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(f"<html><body style='font-family:sans-serif;padding:2rem'>{body}"
                         "</body></html>".encode())

    def log_message(self, *a):
        pass


def start_google_signin() -> str:
    """Start a sign-in and return the Google URL to open in the browser.

    Google redirects back to a one-shot web server on 127.0.0.1, which only
    this computer can reach; ``poll_google_signin`` finishes the exchange.
    """
    cid, _ = google_client()
    if not cid:
        raise SyncError("Google Drive sign-in isn't set up in this copy of Trade Log.")
    old = _signin.get("server")
    if old:
        threading.Thread(target=old.shutdown, daemon=True).start()
    _signin.clear()
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    server = http.server.HTTPServer(("127.0.0.1", 0), _Callback)
    port = server.server_address[1]
    redirect = f"http://127.0.0.1:{port}"
    _signin.update(state=secrets.token_urlsafe(24), verifier=verifier, redirect=redirect,
                   server=server, started=time.time())

    def _serve():
        server.timeout = 1
        while "code" not in _signin and "error" not in _signin and \
                time.time() - _signin.get("started", 0) < 600:
            server.handle_request()
        server.server_close()

    threading.Thread(target=_serve, daemon=True).start()
    return f"{_AUTH_URL}?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code",
        "scope": GOOGLE_SCOPE, "state": _signin["state"],
        "code_challenge": challenge, "code_challenge_method": "S256",
        "access_type": "offline", "prompt": "consent",
    })


def poll_google_signin() -> tuple[str, str]:
    """('waiting'|'done'|'error'|'idle', message)."""
    if not _signin:
        return "idle", ""
    if "error" in _signin:
        return "error", f"Google sign-in didn't complete ({_signin['error']})."
    if "code" not in _signin:
        if time.time() - _signin.get("started", 0) > 600:
            return "error", "Google sign-in timed out — try again."
        return "waiting", ""
    if _signin.get("finished"):
        return "done", _signin.get("email", "")
    cid, secret = google_client()
    r = requests.post(_TOKEN_URL, data={
        "client_id": cid, "client_secret": secret, "code": _signin["code"],
        "code_verifier": _signin["verifier"], "redirect_uri": _signin["redirect"],
        "grant_type": "authorization_code"}, timeout=30)
    j = r.json() if r.content else {}
    if r.status_code != 200 or "refresh_token" not in j:
        _signin["error"] = j.get("error_description") or j.get("error") or f"HTTP {r.status_code}"
        return "error", f"Google sign-in failed: {_signin['error']}"
    tok = {"refresh_token": j["refresh_token"], "access_token": j["access_token"],
           "expires_at": time.time() + int(j.get("expires_in", 3600))}
    _save_gdrive_token(tok)
    try:
        about = requests.get(f"{_API}/about", params={"fields": "user(emailAddress)"},
                             headers={"Authorization": f"Bearer {tok['access_token']}"},
                             timeout=30).json()
        tok["email"] = about.get("user", {}).get("emailAddress", "")
        _save_gdrive_token(tok)
    except Exception:
        pass
    _signin["finished"] = True
    _signin["email"] = tok.get("email", "")
    return "done", _signin["email"]


def disconnect_google() -> None:
    tok = load_gdrive_token()
    if tok and requests is not None:
        try:
            requests.post(_REVOKE_URL, params={"token": tok.get("refresh_token")}, timeout=15)
        except Exception:
            pass
    try:
        GDRIVE_TOKEN_PATH.unlink()
    except FileNotFoundError:
        pass


# ── Sync decisions ────────────────────────────────────────────────────────────

def check(backend) -> dict:
    """Compare both sides with the last sync. Never writes anything.

    Returns {remote_exists, local_changed, remote_changed, first_sync,
    local_md5, remote, lock}. ``first_sync`` means this install has never
    synced with this location, so neither side can be called "newer".
    """
    st = load_state()
    remote = backend.info(REMOTE_DB)
    lmd5 = local_db_md5()
    base = st.get("db_md5") if st.get("location") == location_id(backend) else None
    return {
        "remote_exists":  remote is not None,
        "remote":         remote,
        "local_md5":      lmd5,
        "first_sync":     base is None,
        "local_changed":  base is not None and lmd5 != base,
        "remote_changed": base is not None and remote is not None and remote["md5"] != base,
        "lock":           other_lock(backend),
    }


def location_id(backend) -> str:
    return f"{backend.kind}:{backend.describe() if backend.kind == 'folder' else 'drive'}"


def push(backend, force: bool = False) -> dict:
    """Upload the local log (and attachments). Unless ``force``, refuses when
    the cloud copy changed since this install last synced — that's a conflict
    for the user to settle, not something to overwrite."""
    with _state_lock:
        st = load_state()
        with tempfile.TemporaryDirectory() as td:
            snap = Path(td) / "snap.db"
            md5 = snapshot_db(snap)
            remote = backend.info(REMOTE_DB)
            base = st.get("db_md5") if st.get("location") == location_id(backend) else None
            if remote and not force and remote["md5"] not in (base, md5):
                raise SyncError("The cloud copy changed since this computer last synced.")
            if remote and force and remote["md5"] != md5:
                # Keep the copy being overwritten, locally, as a way back.
                BACKUP_DIR.mkdir(exist_ok=True)
                backend.download(REMOTE_DB, BACKUP_DIR / f"before-cloud-upload-{_stamp()}.db")
            if not remote or remote["md5"] != md5:
                backend.upload(REMOTE_DB, snap)
            sig = attachments_signature()
            att_md5 = st.get("att_md5")
            if sig != st.get("att_sig"):
                z = Path(td) / "att.zip"
                att_md5 = build_attachments_zip(z)
                if att_md5 and att_md5 != (backend.info(REMOTE_ATT) or {}).get("md5"):
                    backend.upload(REMOTE_ATT, z)
        return update_state(location=location_id(backend), db_md5=md5, att_sig=sig,
                            att_md5=att_md5, last_push=_now(), last_error=None,
                            pending=None)


def pull(backend, replace_db: Callable[[str], str]) -> dict:
    """Replace the local log with the cloud copy. ``replace_db`` is app.py's
    replace_database: it validates nothing itself, so the download is checked
    here first, and it keeps a safety copy of what it replaces."""
    with _state_lock:
        with tempfile.TemporaryDirectory() as td:
            dl = Path(td) / "cloud.db"
            backend.download(REMOTE_DB, dl)
            if db_summary(dl)["trades"] is None:
                raise SyncError("The cloud copy isn't a readable Trade Log database — "
                                "nothing was changed.")
            md5 = _md5_file(dl)
            safety = replace_db(str(dl))
            att = backend.info(REMOTE_ATT)
            if att:
                z = Path(td) / "att.zip"
                backend.download(REMOTE_ATT, z)
                extract_attachments(z)
        # The local database is now byte-for-byte the cloud copy, but a
        # migration in replace_db may have touched it — record what the
        # snapshot really is so the next check isn't a false "changed".
        local = local_db_md5()
        st = update_state(location=location_id(backend), db_md5=local,
                          att_sig=attachments_signature(), att_md5=(att or {}).get("md5"),
                          last_pull=_now(), last_error=None, pending=None)
        if local != md5:
            try:
                push(backend)
            except SyncError:
                pass
        st["safety"] = safety
        return st


def remote_summary(backend) -> dict:
    """db_summary of the cloud copy (downloads it to a temp file)."""
    with tempfile.TemporaryDirectory() as td:
        dl = Path(td) / "cloud.db"
        backend.download(REMOTE_DB, dl)
        out = db_summary(dl)
    info = backend.info(REMOTE_DB) or {}
    out["modified"] = info.get("modified")
    return out


def _stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


# ── "Open on another computer" lock ──────────────────────────────────────────

def other_lock(backend) -> dict | None:
    """The lock another computer holds, if it's recent enough to matter."""
    try:
        lk = backend.read_json(REMOTE_LOCK)
    except SyncError:
        return None
    if not lk or lk.get("machine") == machine_name():
        return None
    try:
        age = (_dt.datetime.now() - _dt.datetime.fromisoformat(lk["heartbeat"])).total_seconds() / 60
    except Exception:
        return None
    if age > LOCK_STALE_MIN:
        return None
    lk["minutes_ago"] = int(age)
    return lk


def take_lock(backend) -> None:
    backend.write_json(REMOTE_LOCK, {"machine": machine_name(), "heartbeat": _now()})


def release_lock(backend) -> None:
    try:
        lk = backend.read_json(REMOTE_LOCK)
        if lk and lk.get("machine") == machine_name():
            backend.delete(REMOTE_LOCK)
    except Exception:
        pass


# ── Background sync ──────────────────────────────────────────────────────────
# One thread per process. Every CHECK_SEC it snapshots the log; if that
# differs from the last sync it uploads — unless the cloud changed too, in
# which case it records a conflict for the UI and stops. It never downloads:
# swapping the database under an open page is left to startup or the user.

_worker: dict = {"thread": None, "stop": threading.Event()}


def status() -> dict:
    """What the sidebar and banners show."""
    return load_state()


def _tick() -> None:
    st = load_state()
    backend = backend_from_state(st)
    if backend is None:
        return
    try:
        c = check(backend)
        if c["first_sync"]:
            return
        if c["local_changed"] and c["remote_changed"]:
            update_state(pending="conflict", last_error=None)
        elif c["local_changed"] or not c["remote_exists"]:
            push(backend)
        elif c["remote_changed"]:
            update_state(pending="remote_newer", last_error=None)
        else:
            update_state(last_check=_now(), last_error=None,
                         pending=None if st.get("pending") != "conflict" else "conflict")
        if time.time() - _worker.get("hb", 0) > HEARTBEAT_SEC:
            take_lock(backend)
            _worker["hb"] = time.time()
    except SyncError as e:
        update_state(last_error=str(e))
    except Exception as e:           # never let the thread die
        update_state(last_error=f"{e.__class__.__name__}: {e}")


def start_background() -> None:
    t = _worker.get("thread")
    if t and t.is_alive():
        return

    def _loop():
        while not _worker["stop"].wait(CHECK_SEC):
            _tick()

    _worker["stop"].clear()
    t = threading.Thread(target=_loop, name="trade-log-cloud-sync", daemon=True)
    _worker["thread"] = t
    t.start()


def sync_now() -> None:
    _tick()


def shutdown() -> None:
    """Final upload and lock release when the app exits (best effort)."""
    _worker["stop"].set()
    backend = backend_from_state()
    if backend is None:
        return
    try:
        c = check(backend)
        if not c["first_sync"] and c["local_changed"] and not c["remote_changed"]:
            push(backend)
    except Exception:
        pass
    release_lock(backend)


# ── Connecting ───────────────────────────────────────────────────────────────

def first_sync(backend, replace_db: Callable[[str], str]) -> str:
    """The first sync between this install and a location. Nothing to compare
    against yet, so: an empty cloud gets this log, an empty log here takes the
    cloud's, and when both hold trades the user picks. Returns the action."""
    if backend.info(REMOTE_DB) is None:
        push(backend)
        return "pushed"
    if not db_summary(DB_PATH)["trades"]:
        pull(backend, replace_db)
        return "pulled"
    update_state(pending="choose")
    return "choose"


def connect(mode: str, replace_db: Callable[[str], str], folder: str | None = None) -> str:
    """Switch this install to a location and run its first sync."""
    update_state(mode=mode, folder=folder if mode == "folder" else None,
                 location=None, db_md5=None, att_sig=None, att_md5=None,
                 pending=None, last_error=None)
    backend = backend_from_state()
    try:
        action = first_sync(backend, replace_db)
        take_lock(backend)
    except SyncError as e:
        update_state(last_error=str(e))
        raise
    start_background()
    return action


def disconnect() -> None:
    backend = backend_from_state()
    if backend is not None:
        release_lock(backend)
    if load_state().get("mode") == "gdrive":
        disconnect_google()
    update_state(mode=None, folder=None, location=None, db_md5=None, pending=None,
                 last_error=None)


def detect_cloud_folders() -> list[tuple[str, str]]:
    """[(label, path)] for cloud-drive folders found on this computer."""
    home = Path.home()
    found: list[tuple[str, str]] = []

    def add(label, p):
        p = Path(p)
        if p.is_dir() and str(p) not in {f for _, f in found}:
            found.append((label, str(p)))

    if os.name == "nt":
        import string
        for letter in string.ascii_uppercase:
            add("Google Drive", Path(f"{letter}:/") / "My Drive")
        for env in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
            if os.environ.get(env):
                add("OneDrive", os.environ[env])
        add("iCloud Drive", home / "iCloudDrive")
    else:
        cs = home / "Library" / "CloudStorage"
        if cs.is_dir():
            for d in sorted(cs.iterdir()):
                if d.name.startswith("GoogleDrive"):
                    add("Google Drive", d / "My Drive")
                elif d.name.startswith("OneDrive"):
                    add("OneDrive", d)
                elif d.name.startswith("Dropbox"):
                    add("Dropbox", d)
        add("iCloud Drive", home / "Library" / "Mobile Documents" / "com~apple~CloudDocs")
    add("Google Drive", home / "Google Drive" / "My Drive")
    add("Google Drive", home / "Google Drive")
    add("Dropbox", home / "Dropbox")
    add("OneDrive", home / "OneDrive")
    return found


# ── Startup ──────────────────────────────────────────────────────────────────

_startup: dict = {}


def startup(replace_db: Callable[[str], str]) -> dict:
    """Run once per process, before the app reads any data.

    Pulls a newer cloud copy, uploads local changes, or reports what needs a
    decision. Returns {"action": ..., "message": ...} for the UI to show.
    """
    if _startup:
        return _startup
    import atexit
    _startup["action"] = "off"
    backend = backend_from_state()
    if backend is None:
        return _startup
    atexit.register(shutdown)
    try:
        c = check(backend)
        _startup["lock"] = c["lock"]
        if c["first_sync"]:
            _startup["action"] = first_sync(backend, replace_db)
        elif c["remote_changed"] and c["local_changed"]:
            update_state(pending="conflict")
            _startup["action"] = "conflict"
        elif c["remote_changed"]:
            if c["lock"]:
                # Still open elsewhere: pulling now would just set up a
                # conflict. Say so and let the user choose.
                update_state(pending="remote_newer")
                _startup["action"] = "remote_newer"
            else:
                pull(backend, replace_db)
                _startup["action"] = "pulled"
        elif c["local_changed"] or not c["remote_exists"]:
            push(backend)
            _startup["action"] = "pushed"
        else:
            _startup["action"] = "in_sync"
            update_state(last_check=_now(), last_error=None, pending=None)
        if not c["lock"]:
            take_lock(backend)
            _worker["hb"] = time.time()
    except SyncError as e:
        update_state(last_error=str(e))
        _startup["action"] = "error"
        _startup["message"] = str(e)
    start_background()
    return _startup
