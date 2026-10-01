"""Opt-in, untrusted staging and static archive metadata inspection.

This module is deliberately disconnected from the installer. It never installs,
imports, or executes candidate package code. Downloaded digests are observations,
not trust pins.
"""
from __future__ import annotations

import argparse
import email.parser
import hashlib
import json
import os
import stat
import tarfile
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable


class CandidateError(RuntimeError):
    pass


def _reject_reparse(path: Path) -> None:
    cur = path
    while True:
        if cur.is_symlink():
            raise CandidateError(f"symlink rejected: {cur}")
        if cur.exists():
            try:
                attrs = cur.stat(follow_symlinks=False).st_file_attributes
                if attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                    raise CandidateError(f"reparse point rejected: {cur}")
            except AttributeError:
                pass
        if cur.parent == cur:
            break
        cur = cur.parent


def _contained(root: Path, filename: str) -> Path:
    if not filename or filename in (".", "..") or Path(filename).name != filename or any(c in filename for c in ("/", "\\", ":")):
        raise CandidateError("artifact filename must be a single safe path component")
    _reject_reparse(root)
    resolved = root.resolve()
    target = root / filename
    if os.path.commonpath((str(resolved), str(target.resolve(strict=False)))) != str(resolved):
        raise CandidateError("artifact path escapes the staging directory")
    _reject_reparse(target)
    _reject_reparse(target.with_name(target.name + ".part"))
    return target


def _official_metadata_gate(url: str, filename: str, expected_size: int,
                            metadata: dict) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "stable.repo.amd.com":
        raise CandidateError("candidate URL must use the exact official HTTPS host")
    if metadata.get("status") != "confirmed" or metadata.get("url") != url:
        raise CandidateError("official URL metadata has not been confirmed")
    if metadata.get("filename") != filename or metadata.get("size_bytes") != expected_size:
        raise CandidateError("official filename/size metadata does not match the candidate lock")
    status = metadata.get("http_status", metadata.get("status_code"))
    final_url = metadata.get("final_url")
    content_length = metadata.get("content_length_bytes", metadata.get("content_length"))
    if status != 200 or final_url != url or str(content_length) != str(expected_size):
        raise CandidateError("direct official HEAD status, final URL, or size evidence is incomplete")
    if not metadata.get("name") or not metadata.get("version"):
        raise CandidateError("candidate name and version metadata are required")
    source = metadata.get("source_url", "")
    if not (source.startswith("https://stable.repo.amd.com/rocm/whl-next/") or
            source.startswith("https://stable.repo.amd.com/rocm/core/whl-next/") or
            source.startswith("https://stable.repo.amd.com/rocm/pytorch/whl-next/")):
        raise CandidateError("metadata source is not an official ROCm index page")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def progress_event(name: str, state: str, received: int, total: int | None,
                   elapsed: float, attempt: int) -> dict:
    speed = received / max(elapsed, 0.001)
    percent = None if total is None or total <= 0 else min(100.0, received * 100.0 / total)
    return {"event": state, "artifact": name, "received_bytes": received,
            "total_bytes": total, "percent": percent, "bytes_per_second": speed,
            "elapsed_seconds": elapsed, "attempt": attempt}


def fetch_candidate(url: str, staging_root: Path, filename: str, expected_size: int,
                    metadata: dict, *, observed_root: Path | None = None,
                    progress: Callable[[dict], None] | None = None,
                    cancel: Callable[[], bool] | None = None, retries: int = 0,
                    opener=None, chunk_size: int = 256 * 1024) -> dict:
    """Fetch one independently verified candidate URL, recording an untrusted digest.

    ``metadata`` must contain an explicit confirmed URL, filename, size and official
    index source. There is intentionally no expected-hash argument.
    An injected opener is for deterministic synthetic tests only.
    """
    _official_metadata_gate(url, filename, expected_size, metadata)
    if expected_size <= 0 or retries < 0 or chunk_size <= 0:
        raise CandidateError("invalid size/retry/chunk setting")
    staging_root = Path(staging_root)
    staging_root.mkdir(parents=True, exist_ok=True)
    target = _contained(staging_root, filename)
    part = target.with_name(target.name + ".part")
    if target.exists():
        raise CandidateError("staged artifact already exists; refusing to overwrite")
    emit = progress or (lambda event: None)
    request_opener = opener or urllib.request.build_opener(NoRedirect())
    attempts = retries + 1
    last_error = None
    for attempt in range(1, attempts + 1):
        received = 0
        digest = hashlib.sha256()
        started = time.monotonic()
        emit(progress_event(filename, "start", 0, None, 0, attempt))
        try:
            _reject_reparse(staging_root)
            _reject_reparse(part)
            with request_opener.open(url, timeout=60) as response:
                final_url = response.geturl()
                if final_url != url:
                    raise CandidateError("redirected artifact URL rejected")
                status = getattr(response, "status", 200)
                if status != 200:
                    raise CandidateError(f"unexpected HTTP status {status}")
                raw_length = response.headers.get("Content-Length")
                total = int(raw_length) if raw_length and raw_length.isdigit() else None
                if total == 0:
                    raise CandidateError("server advertised a zero-byte artifact")
                with part.open("wb") as out:
                    while True:
                        if cancel and cancel():
                            raise InterruptedError("candidate fetch cancelled")
                        block = response.read(chunk_size)
                        if not block:
                            break
                        out.write(block)
                        digest.update(block)
                        received += len(block)
                        emit(progress_event(filename, "progress", received, total,
                                            time.monotonic() - started, attempt))
                    out.flush()
                    os.fsync(out.fileno())
                if received == 0:
                    raise CandidateError("received a zero-byte artifact")
                if total is not None and received != total:
                    raise CandidateError(f"truncated response: received {received}, Content-Length {total}")
                if received != expected_size:
                    raise CandidateError(f"candidate size mismatch: received {received}, expected {expected_size}")
                os.replace(part, target)
            record = {
                "schema_version": 1, "status": "observed-project-computed-not-trusted",
                "name": metadata.get("name"), "version": metadata.get("version"),
                "url": url, "source_url": metadata["source_url"], "filename": filename,
                "expected_size_bytes": expected_size, "received_size_bytes": received,
                "sha256": digest.hexdigest(), "trust": "unverified",
                "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            if observed_root is not None:
                observed_root = Path(observed_root)
                observed_root.mkdir(parents=True, exist_ok=True)
                _reject_reparse(observed_root)
                (observed_root / (filename + ".observed.json")).write_text(
                    json.dumps(record, indent=2) + "\n", encoding="utf-8")
            emit(progress_event(filename, "complete", received, expected_size,
                                time.monotonic() - started, attempt))
            return record
        except InterruptedError as exc:
            last_error = exc
            emit(progress_event(filename, "cancelled", received, None,
                                time.monotonic() - started, attempt))
            part.unlink(missing_ok=True)
            raise CandidateError("candidate fetch cancelled") from exc
        except Exception as exc:
            last_error = exc
            part.unlink(missing_ok=True)
            emit(progress_event(filename, "error", received, None,
                                time.monotonic() - started, attempt))
            if isinstance(exc, urllib.error.HTTPError):
                exc.close()
            if isinstance(exc, urllib.error.HTTPError) and (exc.code in (401, 403, 429) or 300 <= exc.code < 400):
                reason = "redirected artifact URL rejected" if 300 <= exc.code < 400 else f"HTTP {exc.code} refused; retries are disabled for this response"
                raise CandidateError(reason) from exc
            if attempt == attempts:
                if isinstance(exc, CandidateError):
                    raise
                raise CandidateError(f"candidate fetch failed: {exc}") from exc
    raise CandidateError(f"candidate fetch failed: {last_error}")


def _safe_member(name: str) -> bool:
    p = Path(name.replace("\\", "/"))
    return not p.is_absolute() and ".." not in p.parts


def analyze_archive(path: Path) -> dict:
    """Read package metadata only; archive members are never extracted or imported."""
    path = Path(path)
    result = {"filename": path.name, "archive_type": None, "name": None,
              "version": None, "requires_dist": [], "requires_python": None,
              "license": None, "license_expression": None, "license_classifiers": [],
              "wheel_tags": [],
              "build_system_requires": [], "build_backend": None,
              "metadata_files": [], "license_files": []}
    if zipfile.is_zipfile(path):
        result["archive_type"] = "wheel/zip"
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if _safe_member(n)]
            metadata_names = [n for n in names if n.endswith(".dist-info/METADATA")]
            wheel_names = [n for n in names if n.endswith(".dist-info/WHEEL")]
            if len(metadata_names) != 1:
                raise CandidateError("wheel must contain exactly one dist-info/METADATA")
            msg = email.parser.Parser().parsestr(zf.read(metadata_names[0]).decode("utf-8", "replace"))
            result.update(name=msg.get("Name"), version=msg.get("Version"),
                          requires_dist=msg.get_all("Requires-Dist", []),
                          requires_python=msg.get("Requires-Python"), license=msg.get("License"),
                          license_expression=msg.get("License-Expression"),
                          license_classifiers=[c for c in msg.get_all("Classifier", []) if "License ::" in c],
                          metadata_files=metadata_names)
            if wheel_names:
                wmsg = email.parser.Parser().parsestr(zf.read(wheel_names[0]).decode("utf-8", "replace"))
                result["wheel_tags"] = wmsg.get_all("Tag", [])
            result["license_files"] = [n for n in names if ".dist-info/licenses/" in n.lower() or n.lower().endswith(".dist-info/license")]
        return result
    if tarfile.is_tarfile(path):
        result["archive_type"] = "sdist/tar"
        with tarfile.open(path, "r:*") as tf:
            members = [m for m in tf.getmembers() if m.isfile() and _safe_member(m.name)]
            pyprojects = [m for m in members if Path(m.name).name == "pyproject.toml"]
            if pyprojects:
                raw = tf.extractfile(pyprojects[0]).read()
                # Parse TOML as data only. No build backend or setup.py is run.
                build = tomllib.loads(raw.decode("utf-8", "replace")).get("build-system", {})
                result["build_system_requires"] = build.get("requires", [])
                result["build_backend"] = build.get("build-backend")
            for member in members:
                base = Path(member.name).name
                if base == "PKG-INFO":
                    f = tf.extractfile(member)
                    msg = email.parser.Parser().parsestr(f.read().decode("utf-8", "replace"))
                    result.update(name=msg.get("Name"), version=msg.get("Version"),
                                  requires_dist=msg.get_all("Requires-Dist", []),
                                  requires_python=msg.get("Requires-Python"), license=msg.get("License"),
                                  license_expression=msg.get("License-Expression"),
                                  license_classifiers=[c for c in msg.get_all("Classifier", []) if "License ::" in c],
                                  metadata_files=[member.name])
                    break
            result["license_files"] = [m.name for m in members if "license" in Path(m.name).name.casefold()]
        return result
    raise CandidateError("unsupported or unreadable archive")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="read wheel/sdist metadata without extraction")
    inspect.add_argument("archive", type=Path)
    fetch = sub.add_parser("fetch", help="explicitly stage one confirmed candidate; never installs it")
    fetch.add_argument("--lock", type=Path, required=True)
    fetch.add_argument("--artifact", required=True, help="candidate name from release-candidate-lock.json")
    fetch.add_argument("--staging-root", type=Path, required=True)
    fetch.add_argument("--observed-root", type=Path, required=True)
    fetch.add_argument("--retries", type=int, default=0)
    args = parser.parse_args()
    if args.command == "inspect":
        print(json.dumps(analyze_archive(args.archive), indent=2))
        return 0
    if args.command == "fetch":
        lock = json.loads(args.lock.read_text(encoding="utf-8"))
        candidates = lock.get("reported_wheels", []) + lock.get("observed_only", [])
        matches = [item for item in candidates if item.get("name") == args.artifact]
        if len(matches) != 1:
            raise CandidateError("artifact name is absent or ambiguous in the candidate lock")
        item = matches[0]
        verification = item.get("official_verification")
        if not isinstance(verification, dict):
            verification = {}
        if item.get("official_index_page"):
            verification["index_page"] = item["official_index_page"]
        metadata = {"status": verification.get("status", "confirmed" if item.get("url") else "unconfirmed"),
                    "url": item.get("url"), "filename": item.get("filename"),
                    "size_bytes": item.get("size_bytes"), "name": item.get("name"),
                    "version": item.get("version"),
                    "http_status": verification.get("http_status"),
                    "final_url": verification.get("final_url"),
                    "content_length_bytes": verification.get("content_length_bytes"),
                    "source_url": verification.get("index_page", "")}
        def emit(event: dict) -> None:
            print(json.dumps(event, ensure_ascii=False), flush=True)
        result = fetch_candidate(item["url"], args.staging_root, item["filename"],
                                 item["size_bytes"], metadata,
                                 observed_root=args.observed_root, progress=emit,
                                 retries=args.retries)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
