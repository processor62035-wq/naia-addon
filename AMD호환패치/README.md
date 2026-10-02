# NAIA AMD Patch Foundation

This is a reversible installer foundation, not an enabled AMD release. The checked-in manifest is disabled and the trust policy has no manifest pin or artifact URL allowlist. `Install.cmd` launches the local PowerShell controller; it selects a language, detects or asks for the NAIA folder, shows read-only GPU diagnostics, then stops before any patch because the AMD manifest is disabled. Choosing the existing NVIDIA profile leaves the app unchanged. No ROCm wheel, NAIA source code, model, driver, or third-party runtime is bundled.

## Source and provenance

The package contains the installer and a small local source transformer, not NAIA application modules or runtime binaries. See [`config/provenance.md`](config/provenance.md) for the target-file baseline and license boundary. No license for NAIA application code is granted by this package.

## Safety model

- Production installation requires an exact SHA-256 pin of the whole manifest and exact URL allowlisting. Redirects are rejected. Artifact bytes are hashed before publication from temporary `.part` files.
- The NAIA build marker is `resources/app.asar` plus exact SHA-256 matches for the three ANIMA integration files in `config/source-baseline.json`. A different build or edited file is rejected.
- Every production patch plan must cover all three files and their exact baseline hashes. All files are checked and staged before app mutation. The first byte-exact backup is stored next to the app in `.naia-amd-patch-backup-<16hex>`, outside `config/다운로드/`.
- The reviewed pure transformer is pinned in the patch engine and transforms only the three current app source files in memory after exact baseline checks. It is unreachable until the manifest trust pin is deliberately reviewed and enabled; no full modified app sources are bundled.
- Durable receipt/journal files support interrupted install rollback and idempotent partial restore. Restore replaces a file only if its current hash matches the recorded installed hash. User edits are reported and preserved.
- GPU enumeration reports exact PnP ID and driver version for diagnostics. Eligibility requires an exact manifest PnP ID, driver version, and Windows build match; friendly-name or gfx-family inference is not used.
- The launcher elevates only its PowerShell process. It does not change machine execution policy, Defender, drivers, or system security settings. The system Python launcher (`py.exe` with Python 3) is required; the installer never fetches an interpreter.

## Candidate ROCm artifacts

The nine reported Windows wheels total 1,512,827,661 bytes. Including rocm-bootstrap and the rocm source archive, the eleven AMD candidate files total 1,512,879,456 compressed bytes. An independent static review approved developer-computed SHA-256 pins for these exact bytes after official AMD index/HEAD and archive metadata checks. These are developer content-identity pins, not AMD-published checksums or manufacturer signatures. The producer-published SHA-256 fields remain null. The production manifest and artifact allowlist remain disabled because there is no production manifest pin, dependency closure and runtime integration are incomplete, and Windows 11 26H2 is unverified.

The AMD archive listings contain 4,187,515,915 uncompressed payload bytes. Python and the 11 PyPI dependency candidates add known download metadata totaling another 60,059,198 bytes; the actual Python installed footprint, complete ComfyUI dependency closure, ANIMA model assets, and build outputs are not yet sized. See config/release-candidate-lock-plan.json and config/release-preparation.md for candidate scope and limits.

The rocm archive is an sdist whose build chain must be locked and reviewed. The download staging folder is temporary and ignored; no ROCm wheel, NAIA application source, model, driver, or runtime is bundled.

The five additional direct PyPI wheel records inspected for ComfyUI (frontend, workflow templates, embedded docs, comfy-aimdo and torchsde) add 36,198,798 bytes by publisher metadata. The resulting known candidate download subtotal is 1,609,137,452 bytes, or 7,237,323,136 bytes with the three workflow models; the known peak disk floor is 12,078,212,274 bytes. These are lower bounds only: the full ComfyUI direct/transitive dependency closure and finite upper bound remain unresolved. See the adjacent dependency lock and plan.

## Local synthetic tests

With Python 3 available, run from this directory:

```powershell
python -B .\config\scripts\test_patch_engine.py
python -B .\config\scripts\test_candidate_stage.py
```

Tests use temporary synthetic app files only. They do not launch the elevated entry points, access the source app, download artifacts, or install runtime dependencies. The most recent local run used the Python bundled with the protected NAIA copy with bytecode writing disabled: **21 tests run, 20 passed, 1 skipped** because this account could not create a symlink. The separate candidate-stage suite passes 15/15 mocked tests. These are synthetic fixture tests, not NAIA or AMD hardware validation.

The manifest remains disabled. A functional AMD release still requires an independently trusted manifest digest, trusted artifact hashes and complete dependency locks, reviewed patch payload bytes, and an exact supported Windows/GPU/driver profile. No AMD acceleration or Boost/Assist Vulkan behavior has been validated on hardware.
## Runtime closure and hardware-test scope

[`config/comfyui-0.22.0-dependency-lock.json`](config/comfyui-0.22.0-dependency-lock.json) records the exact ComfyUI 0.22.0 requirement roots, managed ANIMA workflow, pinned Spectrum node, model sizes/licensing, known AMD candidate totals, and per-scope closure blockers. It is deliberately marked **source-roots-only / incomplete / not installable**; it is not a package lock. See [`config/comfyui-0.22.0-dependency-plan.md`](config/comfyui-0.22.0-dependency-plan.md) for PyTorch HIP vs ComfyUI `cuda` device reporting and full size accounting.

[`config/amd-runtime-test-procedure.md`](config/amd-runtime-test-procedure.md) is a concrete, non-executed test plan for a separate NAIA copy, a separate runtime path, exact HIP/gfx checks, model selection, inference/GPU/VRAM evidence, and rollback. No ROCm runtime has been installed or executed.

