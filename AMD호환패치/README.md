# NAIA AMD Patch Foundation

This is a reversible installer foundation, not an enabled AMD release. The checked-in manifest is disabled and the trust policy has no manifest pin or artifact URL allowlist. `Install.cmd` therefore stops before selecting or changing an application. No ROCm wheel, NAIA source code, model, driver, or third-party runtime is bundled.

## Safety model

- Production installation requires an exact SHA-256 pin of the whole manifest and exact URL allowlisting. Redirects are rejected. Artifact bytes are hashed before publication from temporary `.part` files.
- The NAIA build marker is `resources/app.asar` plus exact SHA-256 matches for the three ANIMA integration files in `config/source-baseline.json`. A different build or edited file is rejected.
- Every production patch plan must cover all three files and their exact baseline hashes. All files are checked and staged before app mutation. The first byte-exact backup is stored next to the app in `.naia-amd-patch-backup`, outside `config/다운로드/`.
- Durable receipt/journal files support interrupted install rollback and idempotent partial restore. Restore replaces a file only if its current hash matches the recorded installed hash. User edits are reported and preserved.
- GPU enumeration reports exact PnP ID and driver version for diagnostics. Eligibility requires an exact manifest PnP ID, driver version, and Windows build match; friendly-name or gfx-family inference is not used.
- The launcher elevates only its PowerShell process. It does not change machine execution policy, Defender, drivers, or system security settings. Python is required locally; the installer never fetches an interpreter.

## Candidate ROCm artifacts

The nine reported Windows wheels total 1,512,827,661 bytes. Including the two additional observed-only records (`rocm-bootstrap` and a `rocm` source archive), the eleven candidates total 1,512,879,456 bytes. The nine wheel records now carry the supplied direct URLs, filenames, versions, and sizes, but no trusted SHA-256 values. The two additional hashes are observed values, not vendor signatures or install trust decisions. This package does not convert any observed checksum into an allowlisted trusted pin. `rocm` is an sdist whose build chain must also be locked and reviewed; binary-only pip mode is not valid for it. A future release-preparation workflow must independently verify official metadata, save bytes without executing them, compute SHA-256, and emit a *candidate* lock clearly marked untrusted for review. Python 3.13.16 installer provenance also needs Authenticode/Sigstore validation. Windows 11 26H2 remains unverified because the cited AMD ROCm 10.0 matrix names 25H2.

## Local synthetic tests

With Python 3 available, run from this directory:

```powershell
python .\config\scripts\test_patch_engine.py
```

Tests use temporary synthetic app files only. They do not launch the elevated entry points, access the source app, download artifacts, or install runtime dependencies. The most recent local run used the Python bundled with the protected NAIA copy with bytecode writing disabled: **15 tests run, 14 passed, 1 skipped** because this account could not create a symlink. These are fixture-engine tests, not NAIA or AMD hardware validation.

The manifest remains disabled. A functional AMD release still requires an independently trusted manifest digest, trusted artifact hashes and complete dependency locks, reviewed patch payload bytes, and an exact supported Windows/GPU/driver profile. No AMD acceleration or Boost/Assist Vulkan behavior has been validated on hardware.
