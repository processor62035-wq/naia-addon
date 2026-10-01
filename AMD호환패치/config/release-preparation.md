# Release preparation and candidate evidence

This remains a disabled, untrusted candidate. On 2026-10-01 UTC, all nine reported wheel URLs, filenames, versions, and sizes were confirmed from AMD's official `stable.repo.amd.com` ROCm package index pages and direct HTTPS `HEAD` responses. Both additional records, `rocm-bootstrap` and the `rocm` source archive, were resolved from their official index links and confirmed the same way. Every artifact response was HTTP 200, had the exact candidate URL as its final URL, and returned the recorded `Content-Length`. Redirects were rejected for artifact requests.

All eleven approved artifacts were staged locally under `config/다운로드/candidate-staging/`. The 9 wheels total 1,512,827,661 bytes; the two additional files add 51,795 bytes, for 1,512,879,456 bytes total. The folder must remain locally ignored and its payloads must not be committed, pushed, or included in a public package. The `.keep` placeholder is retained. Official URL/size evidence is in `config/release-evidence/amd-official-head-check.json` and `amd-observed-only-official-urls.json`; per-file observed digest records are in `config/release-evidence/observed-hashes/`.

Each local digest is computed from the downloaded bytes by this project. Following independent review of the AMD component index links, exact target/version/size, direct HEAD behavior, staged bytes, and internal archive metadata, all eleven exact files have a developer_sha256 content-identity pin. This is not an AMD signature or vendor-published checksum. The publisher sha256 fields remain null. The production manifest remains enabled=false and trust-policy.json retains an empty production manifest pin and artifact allowlist; no installer code calls the candidate fetch API.

## Static package inspection

`config/scripts/candidate_stage.py` is a standard-library-only opt-in staging and archive metadata tool. It rejects redirects, rejects unsafe/reparse paths, writes to `.part`, compares both the received `Content-Length` (when present) and actual received size to the confirmed size, computes a project-observed SHA-256, and emits JSON progress events. It refuses retry on HTTP 3xx, 401, 403, or 429. The fetch API takes no expected hash and cannot change production trust settings. `inspect` reads ZIP wheel `METADATA`/`WHEEL` and TAR members as bytes; it never extracts an archive, imports package code, invokes pip, or runs a PEP 517 build.

For a future, separately reviewed candidate, fetch is explicit: run the script's `fetch` subcommand with one artifact name from the lock and explicit staging/evidence directories. `inspect` accepts a single local archive. Neither command is called from `Install.cmd` or the production installer.

The static metadata output for all eleven candidates is `config/release-evidence/metadata/all-candidate-metadata.json`. All six platform wheels and three ROCm SDK wheels report `cp313-cp313-win_amd64` or `py3-none-win_amd64` as expected. The `rocm` archive's `pyproject.toml` declares `setuptools>=70.2.0` and `setuptools.build_meta`; no build was attempted.

Relevant static dependency findings:

- `torch` has normal requirements `filelock`, `typing-extensions>=4.10.0`, `setuptools>=77.0.3`, `sympy>=1.13.3`, `networkx>=2.5.1`, `jinja2`, `fsspec>=0.8.5`, `rocm[libraries]==10.0.0`, and `rocm-bootstrap`. Its `device-gfx1201` extra declares both `amd-torch-device-gfx1201` and `amd-torch-device-gfx12-0`, each pinned to `2.13.0+rocm10.0.0`.
- `torchvision` has normal requirements `numpy`, `torch`, `pillow!=8.3.*,>=5.3.0`, and `rocm-bootstrap`. Its `device-gfx1201` extra declares `amd-torchvision-device-gfx1201==0.28.0+rocm10.0.0`.
- `amd-torch-device-gfx1201` and `amd-torchvision-device-gfx1201` both require `rocm-sdk-device-gfx1201==10.0.0`; that SDK device wheel requires `rocm-sdk-libraries==10.0.0`. The core SDK wheel has no declared Python dependencies in its metadata.
- `rocm` requires `rocm-sdk-core==10.0.0`; its `libraries` extra requires `rocm-sdk-libraries==10.0.0`. Its device extras include many other GPU families. Marker entries restricted to Linux (gfx1250, gfx942, gfx950) do not apply to Windows, but no third-party marker evaluator or resolver was run.
- `rocm-bootstrap` declares only the `pytest` development extra; that extra is not part of the runtime closure.

The read-only lock plan now records exact-version PyPI URLs, publisher sizes and SHA-256 metadata for the eleven direct/transitive candidates in the torch/vision closure. Those candidate PyPI wheel bytes were not downloaded or locally verified. The full ComfyUI Windows CPython 3.13 closure is still unresolved. Do not use pip to resolve or download this graph: building or preparing the rocm sdist can execute build-backend code. Lock its build inputs and output separately, or review a no-isolation build process; the global only-binary mode is incompatible with the source-only rocm requirement.

## Remaining release lock plan

1. Research the full `cp313-win_amd64` dependency closure from official metadata, evaluate environment markers for Windows and the selected `gfx1201` extras, resolve `rocm` build inputs/outputs, and record exact artifact URLs, sizes, and project-observed hashes. Seek separate authorization before fetching any additional large dependency artifacts.
2. Independently review license metadata and all redistributed license files, package provenance/yanked status, ROCm/driver/Windows compatibility, and the GPU/device mapping. The 11 current AMD content-identity digests have now received an independent second review and are recorded as developer_sha256, separate from AMD publisher fields. Review all dependency license texts before any redistribution; no candidate runtime artifacts are bundled.
3. Verify Python 3.13.16 installer provenance using Authenticode and Sigstore before planning runtime setup. No interpreter installer was fetched or run as part of staging.
4. For ComfyUI 0.22.0, verify the official tag and source digest, licenses, pinned requirements and all required nodes. Document how NAIA's ANIMA integration would connect to that exact ComfyUI build. No full ComfyUI source checkout, runtime, or node code was fetched or run.
5. The 11 AMD candidate bytes now have independent developer content pins, but they are not an install allowlist. Create a production manifest only after the complete runtime dependency closure/build process, licensing, NAIA integration, and exact OS/GPU/driver support row are reviewed. Keep the current production manifest disabled until those gates pass.
6. Hardware validation remains outstanding. The ComfyUI Windows ROCm guidance and current AMD compatibility matrix do not establish NAIA integration or Windows 11 26H2 support; keep 26H2 unsupported unless AMD adds it and NAIA inference tests pass. Validate ANIMA inference logs, GPU/VRAM activity, and CPU fallback behavior only in a later authorized hardware test.

Reference material: [ComfyUI Windows ROCm 10.0 guidance](https://github.com/Comfy-Org/ComfyUI#amd-gpus-windows-rocm-100), [AMD ROCm compatibility matrix](https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html), and [AMD PyTorch installation guidance](https://rocm.docs.amd.com/projects/ai-ecosystem/en/latest/frameworks/pytorch/install.html). These references do not validate the NAIA patch or substitute for an artifact trust review.


## Read-only dependency, runtime, and ComfyUI lock plan (2026-10-01)

A separate research-only plan is in `config/release-candidate-lock-plan.json`. It records the torch/torchvision `gfx1201` transitive closure, PyPI-reported candidate versions, artifact URLs, publisher-reported sizes and SHA-256 values, Python 3.13.16 metadata, and ComfyUI v0.22.0 source metadata. PyPI hashes in that file are publisher-index records and the proposed PyPI wheels were not downloaded. AMD artifact developer_sha256 values are independently reviewed project-computed pins for the staged bytes; publisher SHA-256 is `null` because the inspected AMD index links did not publish one. These fields are deliberately separate.

PyPI file URLs in the plan were HEAD-checked against their PyPI JSON records (HTTP 200, exact URL, exact `Content-Length`). For CPython 3.13 on Windows x86_64, the planned closure is `filelock`, `typing-extensions`, `setuptools`, `sympy` plus `mpmath<1.4`, `networkx`, `jinja2` plus `MarkupSafe`, `fsspec`, `numpy`, and `Pillow`. Selected versions, exact wheel tags, versions, URLs, sizes, publisher hashes, full PyPI `Requires-Dist`, and license metadata are in the JSON. Base dependencies and `gfx1201` extras are included; test/docs/other optional extras are not. The 3.13 marker check accepts `networkx>=3.12, !=3.14.1` for Python 3.13.16. The `rocm` source distribution declares `setuptools>=70.2.0` build-system input; `setuptools==84.0.0` meets that declared lower bound, but its build backend and any dynamic requirements were not run and remain unproven.

Python.org identifies Python 3.13.16's 64-bit Windows installer at `https://www.python.org/ftp/python/3.13.16/python-3.13.16-amd64.exe`, reports SHA-256 `fb4f9f5d438b2396da0086dc70b935c530cb578e37adc6d354f7ad2037fee83b`, and provides Sigstore, GPG, and SPDX metadata. A read-only HEAD returned HTTP 200, exact final URL, and 29,935,584 bytes. No installer bytes were fetched and no Authenticode, Sigstore, or GPG signature was verified. Official release metadata describes a Python Software Foundation Authenticode certificate.

ComfyUI v0.22.0 resolves to commit `a8d2519058ea766ca3b14916bcc01ecef5efd235`, tree `b5484981facdb23a2687d0bf65bde5b22d7a2f20`; GitHub reports the commit unsigned. Its `requirements.txt` blob is `1c87690da8604675dc0a45b3bc9a54e130050ed1` (515 bytes), and root `LICENSE` blob is `f288702d2fa16d3cdf0035b15a9fcbc552cd88e7` (35,149 bytes; GPL-3.0). The tag contains ANIMA implementation files, but their presence does not prove the NAIA node/API integration. ComfyUI has many unpinned requirements outside this torch/vision closure, so its full Windows cp313 dependency/license/hash lock and NAIA node compatibility are still unresolved. The detailed requirements and source URLs are recorded in the plan.

No package installer, candidate wheel, build backend, or ComfyUI/Python runtime was executed in this research step. The research plan does not enable the manifest or set a trust pin. Remaining provenance and closure blockers are listed in the plan's `unresolved` array.


## Upstream source license and attribution

The three exact 2.0.48 ANIMA baseline files match the upstream DNT-LAB/NAIA2.0 tag commit 6e97c7f4f37e495ad21657ed29d28dd9993a808e. Its root LICENSE is GNU GPL version 3. The transformer is marked GPL-3.0-only; the full upstream license is retained under config/THIRD_PARTY_LICENSES/. Attribution and scope are in config/THIRD_PARTY_NOTICES.md. No complete upstream source module or runtime is included.


## Developer-reviewed artifact identity

An independent static review now approves developer-computed SHA-256 pins for all 11 staged AMD candidates. These hashes bind the exact observed bytes after AMD component-index/HEAD and internal archive metadata checks; they are not manufacturer-published checksums or signatures. The reviewed values are recorded separately as developer_sha256 in both lock files, while AMD publisher sha256 remains null. The production manifest stays disabled because the app runtime/ANIMA call path, full ComfyUI/Python closure, 26H2 support, and actual device/driver profile remain unresolved.

Static archive listings total 4,187,515,915 uncompressed payload bytes for the 1,512,879,456 compressed AMD candidates. The 11 PyPI candidate wheels add 30,123,614 reported bytes and the Python 3.13.16 installer metadata reports 29,935,584 bytes. These known artifacts total 1,572,938,654 bytes before extraction/install; this is not a complete disk-space estimate because the full ComfyUI closure, Python footprint, model assets, build outputs, and temporary copies are not locked.
