"""Synthetic, network-free tests for candidate staging and static metadata reads."""
from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
import tempfile
import threading
import unittest
import zipfile
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from email.message import Message
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import candidate_stage as stage


URL = "https://stable.repo.amd.com/rocm/pytorch/whl-next/torch/demo.whl"
SOURCE = "https://stable.repo.amd.com/rocm/whl-next/torch/"


class Response:
    def __init__(self, payload=b"candidate-bytes", length=None, final_url=URL, status=200,
                 fail_after=None):
        self.payload, self.offset = payload, 0
        self.status, self.final_url, self.fail_after = status, final_url, fail_after
        self.headers = Message()
        if length is not None:
            self.headers["Content-Length"] = str(length)

    def geturl(self):
        return self.final_url

    def read(self, n=-1):
        if self.fail_after is not None and self.offset >= self.fail_after:
            raise OSError("synthetic interrupted connection")
        if self.offset >= len(self.payload):
            return b""
        end = min(len(self.payload), self.offset + n)
        if self.fail_after is not None:
            end = min(end, self.fail_after)
        data = self.payload[self.offset:end]
        self.offset = end
        return data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Opener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    def open(self, url, timeout=0):
        self.calls += 1
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class SyntheticHTTP:
    """Local HTTP-only fixture; the production URL remains the official HTTPS URL."""
    def __init__(self):
        self.counts = {}
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                route = self.path.split("?", 1)[0]
                owner.counts[route] = owner.counts.get(route, 0) + 1
                if route == "/redirect":
                    self.send_response(302); self.send_header("Location", "/known"); self.end_headers(); return
                if route == "/retry" and owner.counts[route] == 1:
                    self.send_response(503); self.end_headers(); return
                if route == "/zero":
                    self.send_response(200); self.send_header("Content-Length", "0"); self.end_headers(); return
                body = b"synthetic-HTTP-payload"
                self.send_response(200)
                if route != "/unknown":
                    self.send_header("Content-Length", str(len(body) + (7 if route == "/truncate" else 0)))
                self.end_headers()
                if route == "/interrupt":
                    self.wfile.write(body[:3]); self.wfile.flush(); self.close_connection = True; return
                self.wfile.write(body)
            def log_message(self, *args):
                pass
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def opener(self, route):
        parent = self
        real = urllib.request.build_opener(stage.NoRedirect())
        class Proxy:
            def open(self, url, timeout=0):
                # Rewrite only the transport endpoint. Candidate policy still sees
                # and validates the exact official HTTPS URL before this is called.
                response = real.open(parent.base + route, timeout=timeout)
                class Wrapped:
                    headers = response.headers
                    status = response.status
                    def read(self, size=-1): return response.read(size)
                    def geturl(self): return url
                    def __enter__(self): return self
                    def __exit__(self, *exc): return response.__exit__(*exc)
                return Wrapped()
        return Proxy()

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)


def metadata(filename="demo.whl", size=15, url=URL):
    return {"status": "confirmed", "url": url, "filename": filename,
            "size_bytes": size, "source_url": SOURCE, "name": "demo", "version": "1",
            "http_status": 200, "final_url": url, "content_length_bytes": size}


class CandidateStageTests(unittest.TestCase):
    def fetch(self, root, response, *, filename="demo.whl", size=15, **kwargs):
        return stage.fetch_candidate(URL, root / "bytes", filename, size,
                                     metadata(filename, size), opener=Opener(response), **kwargs)

    def test_known_length_hash_is_recorded_as_untrusted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            payload = b"candidate-bytes"
            events = []
            record = self.fetch(root, Response(payload, len(payload)), progress=events.append,
                                observed_root=root / "observed")
            self.assertEqual((root / "bytes" / "demo.whl").read_bytes(), payload)
            self.assertEqual(record["sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(record["trust"], "unverified")
            self.assertEqual(record["status"], "observed-project-computed-not-trusted")
            self.assertEqual(json.loads((root / "observed" / "demo.whl.observed.json").read_text())["sha256"], record["sha256"])
            self.assertIn("complete", [e["event"] for e in events])

    def test_unknown_content_length_and_unicode_filename(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            payload = b"candidate-bytes"
            self.fetch(root, Response(payload), filename="例示-wheel.whl", size=len(payload))
            self.assertTrue((root / "bytes" / "例示-wheel.whl").is_file())

    def test_truncation_and_size_mismatch_remove_part(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaises(stage.CandidateError):
                self.fetch(root, Response(b"short", 15), size=15)
            self.assertFalse((root / "bytes" / "demo.whl").exists())
            self.assertFalse((root / "bytes" / "demo.whl.part").exists())

    def test_zero_byte_response_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(stage.CandidateError):
                self.fetch(Path(td), Response(b"", 0), size=15)

    def test_redirect_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(stage.CandidateError, "redirect"):
                self.fetch(Path(td), Response(final_url="https://other.example/demo.whl"))

    def test_cancel_cleans_partial_and_emits_cancelled(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            events = []
            with self.assertRaisesRegex(stage.CandidateError, "cancelled"):
                self.fetch(root, Response(), cancel=lambda: True, progress=events.append)
            self.assertFalse((root / "bytes" / "demo.whl.part").exists())
            self.assertIn("cancelled", [e["event"] for e in events])

    def test_retry_after_transient_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            payload = b"candidate-bytes"
            opener = Opener(OSError("temporary"), Response(payload, len(payload)))
            record = stage.fetch_candidate(URL, root / "bytes", "demo.whl", len(payload),
                metadata(size=len(payload)), retries=1, opener=opener)
            self.assertEqual(opener.calls, 2)
            self.assertEqual(record["received_size_bytes"], len(payload))

    def test_http_429_is_never_retried(self):
        with tempfile.TemporaryDirectory() as td:
            opener = Opener(urllib.error.HTTPError(URL, 429, "slow down", {}, None), Response())
            with self.assertRaisesRegex(stage.CandidateError, "HTTP 429"):
                stage.fetch_candidate(URL, Path(td), "demo.whl", 15, metadata(), retries=3, opener=opener)
            self.assertEqual(opener.calls, 1)

    def test_synthetic_http_known_length_hash_observation_and_unicode_path(self):
        server = SyntheticHTTP()
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td); payload = b"synthetic-HTTP-payload"; events=[]
                meta = {**metadata("检验-wheel.whl", len(payload)), "source_url": SOURCE}
                result = stage.fetch_candidate(URL, root / "bytes", "检验-wheel.whl", len(payload),
                    meta, observed_root=root / "observed", progress=events.append,
                    opener=server.opener("/known"))
                self.assertEqual((root / "bytes" / "检验-wheel.whl").read_bytes(), payload)
                self.assertEqual(result["sha256"], hashlib.sha256(payload).hexdigest())
                self.assertEqual(json.loads((root / "observed" / "检验-wheel.whl.observed.json").read_text())["trust"], "unverified")
                self.assertEqual([e for e in events if e["event"] == "complete"][-1]["received_bytes"], len(payload))
        finally:
            server.close()

    def test_synthetic_http_unknown_length_and_truncated_length(self):
        server = SyntheticHTTP()
        try:
            with tempfile.TemporaryDirectory() as td:
                payload = b"synthetic-HTTP-payload"
                stage.fetch_candidate(URL, Path(td) / "unknown", "unknown.whl", len(payload),
                    metadata("unknown.whl", len(payload)), opener=server.opener("/unknown"))
                with self.assertRaises(stage.CandidateError):
                    stage.fetch_candidate(URL, Path(td) / "truncated", "truncated.whl", len(payload),
                        metadata("truncated.whl", len(payload)), opener=server.opener("/truncate"))
        finally:
            server.close()

    def test_synthetic_http_zero_redirect_retry_and_cancel(self):
        server = SyntheticHTTP()
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td); payload = b"synthetic-HTTP-payload"
                with self.assertRaisesRegex(stage.CandidateError, "zero-byte"):
                    stage.fetch_candidate(URL, root / "zero", "zero.whl", len(payload),
                        metadata("zero.whl", len(payload)), opener=server.opener("/zero"))
                with self.assertRaisesRegex(stage.CandidateError, "redirect"):
                    stage.fetch_candidate(URL, root / "redirect", "redirect.whl", len(payload),
                        metadata("redirect.whl", len(payload)), opener=server.opener("/redirect"))
                result = stage.fetch_candidate(URL, root / "retry", "retry.whl", len(payload),
                    metadata("retry.whl", len(payload)), retries=1, opener=server.opener("/retry"))
                self.assertEqual(result["received_size_bytes"], len(payload))
                self.assertEqual(server.counts["/retry"], 2)
                seen = [0]
                def stop_after_first_block():
                    return seen[0] > 0
                def progress(event):
                    if event["event"] == "progress": seen[0] += 1
                with self.assertRaisesRegex(stage.CandidateError, "cancelled"):
                    stage.fetch_candidate(URL, root / "cancel", "cancel.whl", len(payload),
                        metadata("cancel.whl", len(payload)), cancel=stop_after_first_block,
                        progress=progress, opener=server.opener("/known"), chunk_size=1)
                self.assertFalse((root / "cancel" / "cancel.whl.part").exists())
        finally:
            server.close()

    def test_synthetic_http_interrupted_response_is_rejected(self):
        server = SyntheticHTTP()
        try:
            with tempfile.TemporaryDirectory() as td:
                with self.assertRaises(stage.CandidateError):
                    stage.fetch_candidate(URL, Path(td), "interrupted.whl", len(b"synthetic-HTTP-payload"),
                        metadata("interrupted.whl", len(b"synthetic-HTTP-payload")),
                        opener=server.opener("/interrupt"))
                self.assertFalse((Path(td) / "interrupted.whl").exists())
                self.assertFalse((Path(td) / "interrupted.whl.part").exists())
        finally:
            server.close()

    def test_unconfirmed_metadata_and_unsafe_filename_are_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(stage.CandidateError):
                stage.fetch_candidate(URL, Path(td), "demo.whl", 15,
                    {**metadata(), "status": "unverified"}, opener=Opener(Response()))
            with self.assertRaises(stage.CandidateError):
                stage.fetch_candidate(URL, Path(td), "../demo.whl", 15,
                    metadata("../demo.whl"), opener=Opener(Response()))
            with self.assertRaisesRegex(stage.CandidateError, "HEAD"):
                stage.fetch_candidate(URL, Path(td), "demo.whl", 15,
                    {**metadata(), "content_length_bytes": 14}, opener=Opener(Response()))

    def test_wheel_metadata_static_analysis(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "fake.whl"
            with zipfile.ZipFile(p, "w") as zf:
                zf.writestr("demo-1.dist-info/METADATA", "Metadata-Version: 2.1\nName: demo\nVersion: 1\nRequires-Dist: torch>=2; extra == 'gfx1201'\n")
                zf.writestr("demo-1.dist-info/WHEEL", "Wheel-Version: 1.0\nTag: cp313-cp313-win_amd64\n")
                zf.writestr("demo-1.dist-info/licenses/LICENSE", "license")
            result = stage.analyze_archive(p)
            self.assertEqual(result["version"], "1")
            self.assertEqual(result["wheel_tags"], ["cp313-cp313-win_amd64"])
            self.assertIn("torch>=2; extra == 'gfx1201'", result["requires_dist"])
            self.assertTrue(result["license_files"])

    def test_sdist_build_metadata_static_analysis_without_extraction(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "demo.tar.gz"
            with tarfile.open(p, "w:gz") as tf:
                for name, payload in (("demo-1/pyproject.toml", b"[build-system]\nrequires=['setuptools>=70.2.0']\nbuild-backend='setuptools.build_meta'\n"),
                                      ("demo-1/PKG-INFO", b"Metadata-Version: 2.1\nName: demo\nVersion: 1\nRequires-Dist: packaging>=20\n"),
                                      ("demo-1/LICENSE", b"license")):
                    info = tarfile.TarInfo(name)
                    info.size = len(payload)
                    tf.addfile(info, io.BytesIO(payload))
            result = stage.analyze_archive(p)
            self.assertEqual(result["archive_type"], "sdist/tar")
            self.assertEqual(result["build_backend"], "setuptools.build_meta")
            self.assertEqual(result["build_system_requires"], ["setuptools>=70.2.0"])
            self.assertEqual(result["requires_dist"], ["packaging>=20"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
