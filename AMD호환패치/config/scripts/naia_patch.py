"""Conservative NAIA patch transaction engine. Standard library only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import contextlib
import functools
import hmac
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import socket
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Iterable


class PatchError(RuntimeError):
    pass


# Filled only in a reviewed release build. A mutable JSON sidecar alone is not a trust anchor.
TRUSTED_MANIFEST_SHA256 = ""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest().upper()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def reject_link(path: Path) -> None:
    cur = path
    while True:
        if cur.exists() or cur.is_symlink():
            if cur.is_symlink():
                raise PatchError(f"Symlink/reparse path rejected: {cur}")
            try:
                attrs = cur.stat(follow_symlinks=False).st_file_attributes
                if attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                    raise PatchError(f"Reparse point rejected: {cur}")
            except AttributeError:
                pass
        if cur.parent == cur:
            break
        cur = cur.parent


def safe_target(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or not relative or any(p in ("..", "") for p in rel.parts):
        raise PatchError(f"Unsafe relative path: {relative!r}")
    reject_link(root)
    resolved_root = root.resolve()
    target = root.joinpath(rel)
    if os.path.commonpath((str(resolved_root), str(target.resolve(strict=False)))) != str(resolved_root):
        raise PatchError(f"Path escapes application root: {relative}")
    reject_link(target.parent)
    if target.exists():
        reject_link(target)
    return target


def verify_manifest(package_root: Path) -> dict:
    manifest_path = package_root / "config" / "manifest.json"
    policy_path = package_root / "config" / "trust-policy.json"
    manifest_bytes = manifest_path.read_bytes()
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    pin = policy.get("manifest_sha256", "")
    if (not TRUSTED_MANIFEST_SHA256 or policy.get("trust_status") != "reviewed" or
            pin.upper() != TRUSTED_MANIFEST_SHA256.upper() or
            sha256_bytes(manifest_bytes) != TRUSTED_MANIFEST_SHA256.upper()):
        raise PatchError("Manifest trust pin is absent or does not match; no install writes were made.")
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("enabled") is not True:
        raise PatchError("AMD support manifest is disabled.")
    if not manifest.get("profiles") or not manifest.get("patches"):
        raise PatchError("Enabled manifest must include reviewed hardware profiles and patches.")
    allowlist = policy.get("allowed_artifact_urls", [])
    for item in manifest.get("artifacts", []):
        parsed = urllib.parse.urlparse(item.get("url", ""))
        if parsed.scheme != "https" or item.get("url") not in allowlist or not is_hash(item.get("sha256")):
            raise PatchError("Every artifact requires an allowlisted HTTPS URL and SHA-256 pin.")
    return manifest


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def is_hash(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdefABCDEF" for c in value)


def progress_line(name: str, received: int, total: int | None, elapsed: float) -> str:
    speed = received / max(elapsed, 0.001)
    if total is None:
        ratio = "size unknown"
        size = "?"
    elif total == 0:
        ratio = "invalid zero-byte size"
        size = "0"
    else:
        ratio = f"{min(100.0, received * 100.0 / total):5.1f}%"
        size = str(total)
    return f"{name}: {received}/{size} bytes ({ratio}) {speed:.0f} bytes/s"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def download_verified(url: str, destination: Path, expected_sha256: str,
                      allowed_urls: set[str], progress: Callable[[str], None] = print) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or url not in allowed_urls or not is_hash(expected_sha256):
        raise PatchError("Download blocked: exact HTTPS URL allowlist and explicit SHA-256 pin are required.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".part")
    try:
        opener = urllib.request.build_opener(NoRedirect())
        with opener.open(url, timeout=30) as response, temp.open("wb") as out:
            if response.geturl() != url:
                raise PatchError("Redirected artifact URL rejected.")
            length = response.headers.get("Content-Length")
            total = int(length) if length is not None and length.isdigit() else None
            if total == 0:
                raise PatchError("Server advertised an empty artifact.")
            start = time.monotonic()
            count = 0
            digest = hashlib.sha256()
            while True:
                block = response.read(128 * 1024)
                if not block:
                    break
                out.write(block)
                digest.update(block)
                count += len(block)
                progress(progress_line(destination.name, count, total, time.monotonic() - start))
            out.flush()
            os.fsync(out.fileno())
            if total is not None and count != total:
                raise PatchError("Downloaded byte count does not match Content-Length.")
            if digest.hexdigest().upper() != expected_sha256.upper():
                raise PatchError("Artifact SHA-256 mismatch.")
        os.replace(temp, destination)
    finally:
        if temp.exists():
            temp.unlink()


def locate_naia() -> list[Path]:
    candidates = [Path.home() / "Desktop", Path.home() / "Downloads", Path("C:/NAIA"), Path("D:/NAIA")]
    found: list[Path] = []
    for base in candidates:
        if not base.is_dir():
            continue
        try:
            for child in base.iterdir():
                if child.is_dir() and child.name.casefold() in ("naia-portable", "naia-portable-2.0.48"):
                    found.append(child)
        except OSError:
            continue
    return found


def choose_naia() -> Path:
    found = locate_naia()
    for candidate in found:
        print(f"Detected candidate: {candidate}")
    if len(found) == 1:
        answer = input("Use this NAIA folder? [Y/n] ").strip().casefold()
        if answer in ("", "y", "yes"):
            return found[0]
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw()
        selected = filedialog.askdirectory(title="Select NAIA Portable folder")
        root.destroy()
        if selected:
            return Path(selected)
    except Exception:
        pass
    raw = input("NAIA folder path: ").strip().strip('"')
    if not raw:
        raise PatchError("No NAIA folder selected.")
    return Path(raw)


def validate_app_root(root: Path, expected_version: str, protected_root: str | None = None) -> Path:
    reject_link(root)
    root = root.resolve(strict=True)
    if protected_root:
        protected = Path(protected_root)
        reject_link(protected)
        if os.path.normcase(str(root)) == os.path.normcase(str(protected.resolve(strict=False))):
            raise PatchError("This locally protected app root cannot be modified.")
    if not (root / "resources" / "app.asar").is_file():
        raise PatchError("Selected folder lacks the expected resources/app.asar marker.")
    baseline_path = Path(__file__).resolve().parents[1] / "source-baseline.json"
    try:
        baseline = json.loads(baseline_path.resolve().read_text(encoding="utf-8"))
    except Exception as exc:
        raise PatchError("Fixture source baseline is unavailable; cannot identify this NAIA build.") from exc
    for row in baseline:
        target = safe_target(root, row["path"])
        if not target.is_file(): raise PatchError(f"NAIA build file missing: {row['path']}")
        digest = sha256_file(target)
        expected = row["sha256"].upper()
        if digest != expected:
            state_root = state_root_for_app(root, ".naia-amd-patch-backup")
            if not ((state_root / "receipt.json").is_file() or (state_root / "journal.json").is_file()):
                raise PatchError(f"Unknown NAIA build or edited protected source: {row['path']}")
    return root


def state_root_for_app(root: Path, base_name: str) -> Path:
    identity = os.path.normcase(str(Path(root).resolve(strict=True))).encode("utf-8")
    suffix = hashlib.sha256(identity).hexdigest()[:16]
    return Path(root).parent / f"{base_name}-{suffix}"


def diagnose_gpu() -> list[dict[str, str]]:
    print("Display adapter enumeration (diagnostic only; this does not assert AMD support):")
    try:
        command = "Get-PnpDevice -Class Display | ForEach-Object { $v=(Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_DriverVersion' -ErrorAction SilentlyContinue).Data; [pscustomobject]@{FriendlyName=$_.FriendlyName;InstanceId=$_.InstanceId;DriverVersion=$v} } | ConvertTo-Json -Compress"
        result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command],
                                capture_output=True, text=True, timeout=10, check=False)
        records = json.loads(result.stdout) if result.stdout.strip() else []
        if isinstance(records, dict): records = [records]
        if result.returncode or not records:
            print("GPU enumeration unavailable.")
            return []
        else:
            for item in records: print(f"  {item.get('FriendlyName','(unknown)')} [{item.get('InstanceId','')}]" )
            return [{"name": str(item.get("FriendlyName", "")), "pnp_id": str(item.get("InstanceId", "")),
                     "driver_version": str(item.get("DriverVersion", ""))} for item in records]
    except Exception:
        print("GPU enumeration unavailable.")
        return []


def select_language(package_root: Path) -> dict[str, str]:
    options = {"1": "en", "2": "ja", "3": "ko"}
    choice = input("Choose language: 1 English, 2 日本語, 3 한국어: ").strip()
    code = options.get(choice, "en")
    return json.loads((package_root / "config" / "resources" / f"{code}.json").read_text(encoding="utf-8"))


def make_patch_plan(package_root: Path, manifest: dict, profile: dict) -> list[dict]:
    """Load payloads only from config/patches; verify every baseline and payload before writes."""
    plan = []
    seen = set()
    for item in manifest["patches"]:
        rel = item["path"]
        if rel in seen: raise PatchError("Duplicate patch target in manifest.")
        seen.add(rel)
        payload_rel = Path(item["payload_file"])
        if payload_rel.is_absolute() or ".." in payload_rel.parts:
            raise PatchError("Patch payload path escapes package.")
        payload_path = package_root / "config" / "patches" / payload_rel
        reject_link(package_root / "config" / "patches")
        reject_link(payload_path)
        payload = payload_path.read_bytes()
        if sha256_bytes(payload) != item["installed_sha256"].upper():
            raise PatchError(f"Patch payload hash mismatch: {rel}")
        expected = profile.get("base_files", {}).get(rel)
        if not is_hash(expected) or expected.upper() != item.get("original_sha256", "").upper():
            raise PatchError(f"No exact reviewed baseline hash for {rel}")
        plan.append({"path": rel, "original_sha256": expected.upper(),
                     "installed_sha256": item["installed_sha256"].upper(), "bytes": payload})
    if not plan: raise PatchError("The selected support profile has no patch payloads.")
    return plan


def match_profile(manifest: dict, gpu_records: list[dict[str, str]], os_version: str) -> dict:
    for profile in manifest.get("profiles", []):
        # Exact strings only. Require exact PnP ID, driver and Windows build.
        if os_version not in profile.get("windows_builds", []): continue
        if not profile.get("driver_versions"): continue
        if any(gpu["pnp_id"] in profile.get("pnp_ids", []) and gpu["driver_version"] in profile["driver_versions"] for gpu in gpu_records):
            return profile
    raise PatchError("No exact hardware and Windows profile matches this system.")


def windows_release() -> str:
    if os.name != "nt": return "unsupported-host"
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
        display, _ = winreg.QueryValueEx(key, "DisplayVersion")
        build, _ = winreg.QueryValueEx(key, "CurrentBuildNumber")
        return f"Windows-{display}-build-{build}"
    except Exception:
        return "unknown-windows-build"


def assert_not_running() -> None:
    if os.name != "nt":
        return
    result = subprocess.run(["tasklist.exe", "/FO", "CSV", "/NH"],
                            capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise PatchError("Could not verify whether NAIA is running; refusing file changes.")
    if any(line.strip().strip('"').split('","', 1)[0].strip('"').casefold().startswith("naia")
           for line in result.stdout.splitlines() if line.strip()):
        raise PatchError("Close NAIA before patching.")


def exclusive_transaction(method):
    @functools.wraps(method)
    def guarded(self, *args, **kwargs):
        self.state.mkdir(parents=True, exist_ok=True)
        lock_path = self.state / ".transaction.lock"
        with lock_path.open("a+b") as stream:
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"\0"); stream.flush()
            stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    unlock = lambda: msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    unlock = lambda: fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            except (OSError, ImportError) as exc:
                raise PatchError("Another transaction is active, or transaction locking is unavailable.") from exc
            try:
                return method(self, *args, **kwargs)
            finally:
                unlock()
    return guarded


class Transaction:
    """Applies only explicitly supplied byte patches, with durable backups and conflict-safe restore."""
    def __init__(self, app_root: Path, state_root: Path, fixture_mode: bool = False):
        reject_link(Path(app_root))
        reject_link(Path(state_root))
        self.root = Path(app_root).resolve(strict=True)
        self.state = Path(state_root).resolve(strict=False)
        self.fixture_mode = fixture_mode
        if os.path.commonpath((str(self.root), str(self.state))) == str(self.root):
            raise PatchError("Backup/state directory must be outside the application root.")
        if self.root == self.state or os.path.commonpath((str(self.root), str(self.state))) == str(self.state):
            raise PatchError("App and state directories must be separate.")
        self.backup = self.state / "originals"
        self.receipt = self.state / "receipt.json"
        self.journal = self.state / "journal.json"
        marker = self.root / "resources" / "app.asar"
        self.identity = {"app_root": os.path.normcase(str(self.root)),
                         "app_marker_sha256": sha256_file(marker) if marker.is_file() else None}

    def _key(self, create=False):
        path = self.state / ".state-key"
        if path.exists():
            reject_link(path)
            key = path.read_bytes()
            if len(key) != 32: raise PatchError("State authentication key is invalid.")
            return key
        if not create: raise PatchError("State authentication key is missing.")
        self.state.mkdir(parents=True, exist_ok=True)
        key = os.urandom(32)
        with path.open("xb") as stream:
            stream.write(key); stream.flush(); os.fsync(stream.fileno())
        return key

    def _write_state(self, path: Path, document: dict) -> None:
        payload = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        signed = {"document": document, "hmac_sha256": hmac.new(self._key(create=True), payload, hashlib.sha256).hexdigest().upper()}
        atomic_json(path, signed)

    def _read_state(self, path: Path) -> dict:
        reject_link(path)
        try: envelope = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc: raise PatchError(f"State file is unreadable: {path.name}") from exc
        document = envelope.get("document")
        if not isinstance(document, dict): raise PatchError("State document is malformed.")
        payload = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        expected = hmac.new(self._key(), payload, hashlib.sha256).hexdigest().upper()
        if not hmac.compare_digest(expected, str(envelope.get("hmac_sha256", "")).upper()):
            raise PatchError("Receipt/journal authentication failed; no files were changed.")
        if document.get("schema_version") != 1 or document.get("app_identity") != self.identity:
            raise PatchError("Receipt/journal belongs to another app identity.")
        return document

    def _ensure_identity(self):
        identity_path = self.state / "identity.json"
        if identity_path.exists():
            saved = self._read_state(identity_path)
            if saved.get("kind") != "identity": raise PatchError("State identity record is invalid.")
        else:
            if self.receipt.exists() or self.journal.exists():
                raise PatchError("Transaction state has no identity record.")
            self._write_state(identity_path, {"schema_version": 1, "kind": "identity", "app_identity": self.identity})

    def _validate_rows(self, rows):
        expected = {
            "resources/naia-backend/core/anima_engine/manifest.py": "6685DCFCDA685056E64445CD062176B273CF2D35002B52EB5A9EAD1E04254335",
            "resources/naia-backend/core/anima_engine/install.py": "FDE63683E5FDBDFFF1B9C541A035C66B2D7DDD53CCB0EE3FB1F74929019148D0",
            "resources/naia-backend/core/anima_engine/runtime.py": "748EA6520BFE14D571AF39D2B6A71ECCDF5F8F979E0C386E1A5065BEDAA1A27B",
        }
        if not isinstance(rows, list) or not rows: raise PatchError("Receipt/journal rows are empty or malformed.")
        paths = []
        for row in rows:
            rel = row.get("path")
            if not isinstance(rel, str) or not is_hash(row.get("original_sha256")) or not is_hash(row.get("installed_sha256")):
                raise PatchError("Receipt/journal row is malformed.")
            if row.get("backup") != rel: raise PatchError("Backup path must exactly match a validated app-relative target.")
            safe_target(self.root, rel)
            safe_target(self.backup, row["backup"])
            if not self.fixture_mode and (rel not in expected or row["original_sha256"].upper() != expected[rel]):
                raise PatchError("Receipt/journal contains a non-allowlisted target or baseline hash.")
            paths.append(rel)
        if len(set(paths)) != len(paths): raise PatchError("Duplicate paths in receipt/journal.")
        if not self.fixture_mode and set(paths) != set(expected):
            raise PatchError("Production receipt/journal must contain all three integration targets.")

    @exclusive_transaction
    def install(self, patches: list[dict], expected_app_version: str, actual_app_version: str) -> None:
        if actual_app_version != expected_app_version:
            raise PatchError("Unknown app version; refusing to write.")
        expected_paths = {
            "resources/naia-backend/core/anima_engine/manifest.py": "6685DCFCDA685056E64445CD062176B273CF2D35002B52EB5A9EAD1E04254335",
            "resources/naia-backend/core/anima_engine/install.py": "FDE63683E5FDBDFFF1B9C541A035C66B2D7DDD53CCB0EE3FB1F74929019148D0",
            "resources/naia-backend/core/anima_engine/runtime.py": "748EA6520BFE14D571AF39D2B6A71ECCDF5F8F979E0C386E1A5065BEDAA1A27B",
        }
        if not self.fixture_mode:
            provided = {p["path"]: p.get("original_sha256", "").upper() for p in patches}
            if provided != expected_paths:
                raise PatchError("Production patch must include all three exact baseline targets and hashes.")
        if self.journal.exists():
            self._ensure_identity()
            journal = self._read_state(self.journal)
            if journal.get("operation") != "install":
                raise PatchError("An unfinished restore exists; resume restore before reinstalling.")
            self.recover_install(journal)
        if self.receipt.exists():
            raise PatchError("A patch receipt already exists; restore before reinstall/update.")
        # Validate every source and destination before staging or any application mutation.
        checked = []
        seen = set()
        for item in patches:
            rel = item["path"]
            if rel in seen or not is_hash(item.get("original_sha256")) or not is_hash(item.get("installed_sha256")):
                raise PatchError("Duplicate path or missing SHA-256 in patch plan.")
            seen.add(rel)
            target = safe_target(self.root, rel)
            if not target.is_file() or sha256_file(target) != item["original_sha256"].upper():
                raise PatchError(f"Baseline mismatch: {rel}")
            payload = item["bytes"]
            if sha256_bytes(payload) != item["installed_sha256"].upper():
                raise PatchError(f"Patch payload hash mismatch: {rel}")
            checked.append((item, target, payload))
        self._ensure_identity()
        self.backup.mkdir(parents=True, exist_ok=True)
        rows = []
        staged = []
        try:
            for item, target, payload in checked:
                rel = item["path"]
                original = target.read_bytes()
                if sha256_bytes(original) != item["original_sha256"].upper():
                    raise PatchError(f"File changed during staging: {rel}")
                backup_path = safe_target(self.backup, rel)
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                if backup_path.exists():
                    if sha256_file(backup_path) != item["original_sha256"].upper():
                        raise PatchError(f"Existing first backup conflicts: {rel}")
                else:
                    with backup_path.open("xb") as bf:
                        bf.write(original)
                        bf.flush()
                        os.fsync(bf.fileno())
                fd, name = tempfile.mkstemp(prefix=".naia-stage-", dir=target.parent)
                with os.fdopen(fd, "wb") as f:
                    f.write(payload); f.flush(); os.fsync(f.fileno())
                stage = Path(name)
                if sha256_file(stage) != item["installed_sha256"].upper():
                    raise PatchError(f"Staged payload verification failed: {rel}")
                staged.append((stage, target, item))
                rows.append({"path": rel, "original_sha256": item["original_sha256"].upper(),
                             "installed_sha256": item["installed_sha256"].upper(),
                             "backup": rel, "status": "staged"})
            doc = {"schema_version": 1, "app_identity": self.identity, "operation": "install", "rows": rows}
            self._validate_rows(rows)
            self._write_state(self.journal, doc)
            applied = []
            try:
                for stage, target, item in staged:
                    if sha256_file(target) != item["original_sha256"].upper():
                        raise PatchError(f"Changed before replace: {item['path']}")
                    os.replace(stage, target)
                    applied.append((target, item))
                    rows[len(applied)-1]["status"] = "installed"
                    self._write_state(self.journal, doc)
                self._write_state(self.receipt, {"schema_version": 1, "app_identity": self.identity, "rows": rows})
                self.journal.unlink(missing_ok=True)
            except Exception:
                clean = True
                for target, item in reversed(applied):
                    backup_path = self.backup / item["path"]
                    if not backup_path.is_file() or sha256_file(backup_path) != item["original_sha256"].upper():
                        clean = False
                        continue
                    if target.exists() and sha256_file(target) == item["installed_sha256"].upper():
                        restore_atomic(target, backup_path.read_bytes())
                    elif not target.exists() or sha256_file(target) != item["original_sha256"].upper():
                        clean = False
                if clean and self.journal.exists():
                    self.journal.unlink()
                raise
        finally:
            for stage, _, _ in staged:
                if stage.exists(): stage.unlink()
            # Keep journal after a failure so a retry cannot overwrite recovery evidence.

    @exclusive_transaction
    def restore(self) -> list[str]:
        self._ensure_identity()
        if self.journal.exists():
            journal = self._read_state(self.journal)
            if journal.get("operation") == "install":
                self.recover_install(journal)
                return []
            if journal.get("operation") != "restore": raise PatchError("Unknown interrupted transaction operation.")
            rows = journal["rows"]
        elif not self.receipt.exists():
            return []
        else:
            receipt = self._read_state(self.receipt)
            rows = receipt["rows"]
        self._validate_rows(rows)
        doc = {"schema_version": 1, "app_identity": self.identity, "operation": "restore", "rows": rows}
        if not self.journal.exists(): self._write_state(self.journal, doc)
        conflicts = []
        for i, row in enumerate(rows):
            target = safe_target(self.root, row["path"])
            original = safe_target(self.backup, row["backup"])
            if not original.is_file() or sha256_file(original) != row["original_sha256"]:
                raise PatchError(f"Backup missing or corrupt: {row['path']}")
            if not target.exists():
                raise PatchError(f"Installed file is missing: {row['path']}")
            current_hash = sha256_file(target)
            if current_hash == row["original_sha256"]:
                row["status"] = "already-original"
            elif current_hash == row["installed_sha256"]:
                restore_atomic(target, original.read_bytes())
                row["status"] = "restored"
            else:
                row["status"] = "conflict-preserved"
                conflicts.append(row["path"])
            self._write_state(self.journal, doc)
        if conflicts:
            self._write_state(self.receipt, {"schema_version": 1, "app_identity": self.identity, "rows": rows})
            self.journal.unlink(missing_ok=True)
        else:
            self.receipt.unlink(missing_ok=True)
            self.journal.unlink(missing_ok=True)
            # Delete only known unchanged staged/generated files, never arbitrary directory contents.
        return conflicts

    def recover_install(self, journal: dict | None = None) -> None:
        journal = journal or self._read_state(self.journal)
        if journal.get("operation") != "install":
            raise PatchError("No interrupted install transaction to recover.")
        self._validate_rows(journal.get("rows"))
        conflicts = []
        for row in reversed(journal["rows"]):
            target = safe_target(self.root, row["path"])
            backup = safe_target(self.backup, row["backup"])
            if not backup.is_file() or sha256_file(backup) != row["original_sha256"]:
                raise PatchError(f"Recovery backup missing or corrupt: {row['path']}")
            if not target.exists():
                conflicts.append(row["path"])
                continue
            current = sha256_file(target)
            if current == row["installed_sha256"]:
                restore_atomic(target, backup.read_bytes())
            elif current != row["original_sha256"]:
                conflicts.append(row["path"])
        if conflicts:
            raise PatchError("Interrupted install has user conflicts; preserved: " + ", ".join(conflicts))
        self.journal.unlink(missing_ok=True)


def restore_atomic(target: Path, data: bytes) -> None:
    fd, name = tempfile.mkstemp(prefix=".naia-restore-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(name, target)
    finally:
        if os.path.exists(name): os.unlink(name)


def cli() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("install", "uninstall", "diagnose"))
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--app-root", type=Path)
    args = parser.parse_args()
    package = args.package_root.resolve()
    cfg = json.loads((package / "config" / "settings.json").read_text(encoding="utf-8"))
    if args.command == "diagnose": diagnose_gpu(); return 0
    if args.command == "install":
        text = select_language(package)
        print(text["title"])
        gpu_records = diagnose_gpu()
        manifest = verify_manifest(package)  # Disabled default exits before asking to elevate/write.
        protected = os.environ.get(cfg.get("protected_root_env", "NAIA_AMD_PROTECTED_ROOT"))
        root = validate_app_root(args.app_root or choose_naia(), cfg["expected_naia_version"], protected)
        assert_not_running()
        profile = match_profile(manifest, gpu_records, windows_release())
        plan = make_patch_plan(package, manifest, profile)
        state = state_root_for_app(root, cfg["backup_directory_name"])
        Transaction(root, state).install(plan, cfg["expected_naia_version"], manifest["app"]["version"])
        print(text["install_done"])
        return 0
    protected = os.environ.get(cfg.get("protected_root_env", "NAIA_AMD_PROTECTED_ROOT"))
    app = validate_app_root(args.app_root or choose_naia(), cfg["expected_naia_version"], protected)
    assert_not_running()
    state = state_root_for_app(app, cfg["backup_directory_name"])
    tx = Transaction(app, state)
    conflicts = tx.restore()
    if conflicts: print("Conflicts preserved: " + ", ".join(conflicts))
    else: print("Restore complete (or nothing to restore).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(cli())
    except PatchError as exc:
        print(f"Stopped safely: {exc}", file=sys.stderr)
        raise SystemExit(2)
