# ComfyUI 0.22.0 AMD dependency and workflow plan

Status: **partial static metadata only; incomplete and not installable**. No dependency resolver was run and no additional artifacts were downloaded. Five PyPI roots have publisher JSON metadata recorded in the adjacent lock; the remaining requirement set does not have a closed Windows cp313 artifact graph.

## Target identity and interpreter split

- NAIA is the 2.0.48 baseline pinned in `source-baseline.json`; its bundled backend interpreter is CPython 3.12.10 (`resources/python/NAIA_PYTHON_RUNTIME_MANIFEST.json`; release manifest totals 653,373,223 bytes for the staged NAIA payload). The managed ANIMA profile separately names the ComfyUI portable runtime as Python 3.13 (`core/anima_engine/manifest.py`). Do not install ROCm into NAIA's Python 3.12 environment.
- Existing ANIMA runtime identity is `r1-comfyui-0.22.0-nvidia`; the profile pins ComfyUI portable NVIDIA 7z at 2,008,033,059 compressed bytes and a CUDA 13.0 runtime. This binary must not be used as the AMD runtime.
- AMD runtime target candidate: Windows x86_64, CPython 3.13 ABI `cp313-cp313-win_amd64`, ROCm 10.0.0; gfx1201 only where the exact machine/driver/OS profile is supported. Python installer candidate is CPython 3.13.16 Windows x86-64, publisher metadata size 29,935,584 bytes; its bytes and signature have not been fetched or verified.
- ComfyUI tag `v0.22.0` resolves to source commit `a8d2519058ea766ca3b14916bcc01ecef5efd235`. Tag and source are not proof that the AMD wheel combination works with NAIA.

## Exact managed ANIMA graph

Source: NAIA `core/anima_engine/manifest.py` pinned `GRAPH_TEMPLATE`, `MODELS`, and `SPECTRUM_FILES`.

| Node | Type | Inputs/dependency |
|---|---|---|
| 8 | VAEDecode | output image decode |
| 11, 12 | CLIPTextEncode | positive and negative text via node 45 |
| 15 | VAELoader | `qwen_image_vae.safetensors` |
| 28 | EmptyLatentImage | initial 960 × 1408 latent |
| 44 | UNETLoader | `naiANIMA2d_v03.safetensors` |
| 45 | CLIPLoader | `qwen_3_06b_base.safetensors`, stable-diffusion mode |
| 48 | SpectrumSPDKSampler | custom node; `euler`, `simple`, SPD single split; no calibrator/adapter input in this graph |
| 52 | RescaleCFG | model rescale multiplier 0.5 |
| 53 | SaveImage | output `NAIA_ANIMA` |

The selected node uses Spectrum's pinned custom-node files at commit `f6a21456eeb8581ecba3f2041ba83213835512e8` (11 files, 116,638 bytes as pinned in the NAIA manifest). Its pinned `pyproject.toml` says `dependencies = []`. The standard SPD graph does not select its optional first-use calibration/adapter downloads. Do not include optional Spectrum assets unless a different graph explicitly selects them.

The model sizes pinned by the profile are: UNet 4,182,244,342 bytes; Qwen 3 0.6B text encoder 1,192,135,096 bytes; Qwen Image VAE 253,806,246 bytes. Total model payload is **5,628,185,684 bytes**. These are license-controlled model downloads; do not redistribute or bundle them. Reuse is allowed only after the selected file's exact hash is verified and its license is accepted for that use.

## ComfyUI core requirement roots

Source: [`requirements.txt` at ComfyUI v0.22.0](https://raw.githubusercontent.com/Comfy-Org/ComfyUI/v0.22.0/requirements.txt). These are upstream roots, not a resolved lock; wildcard/minimum ranges remain unpinned here.

```text
comfyui-frontend-package==1.43.18
comfyui-workflow-templates==0.9.79
comfyui-embedded-docs==0.5.0
torch
torchsde
torchvision
torchaudio
numpy>=1.25.0
einops
transformers>=4.50.3
tokenizers>=0.13.3
sentencepiece
safetensors>=0.4.2
aiohttp>=3.11.8
yarl>=1.18.0
pyyaml
Pillow
scipy
tqdm
psutil
alembic
SQLAlchemy>=2.0.0
filelock
av>=14.2.0
comfy-kitchen>=0.2.8
comfy-aimdo==0.3.0
requests
simpleeval>=1.0.0
blake3
kornia>=0.7.1  # non-essential upstream group
spandrel      # non-essential upstream group
pydantic~=2.0 # non-essential upstream group
pydantic-settings~=2.0 # non-essential upstream group
PyOpenGL      # non-essential upstream group
glfw          # non-essential upstream group
```

An AMD runtime must pin every selected direct and transitive wheel for Python 3.13/Windows x86_64, including any native wheels. The existing AMD candidate lock resolves only the PyTorch/ROCm-related portion; it is **not** the ComfyUI requirements closure. Do not use live latest resolution at install time.

## Candidate file and size accounting

The current AMD candidate lock has 11 AMD artifacts: developer-reviewed content pins cover the staged byte digests, with AMD publisher SHA-256/signatures recorded as unavailable. Preserve that distinction. The candidate byte total is 1,512,879,456 compressed bytes; the wheel/sdist payload inventory is 4,187,515,915 extracted bytes. The 11 PyPI candidates identified for the PyTorch/ROCm closure sum to 30,123,614 bytes and have PyPI-reported hashes/metadata but were not downloaded or locally hashed. Python 3.13.16 installer metadata contributes another 29,935,584 bytes, unverified.

- Five additional PyPI wheel records (frontend, workflow templates, embedded docs, comfy-aimdo, torchsde) contribute a further **36,198,798 bytes** of publisher-reported compressed sizes. Workflow templates additionally requires five version-pinned template subpackages whose artifact sizes/hashes are unresolved.
- Known candidate download sum including those five extra records: **1,609,137,452 bytes** (AMD artifacts + PyTorch/ROCm PyPI candidates + Python installer candidate + five additional PyPI candidates).
- Add all three model files if none can be reused: **5,628,185,684 bytes**, making the known download subtotal **7,237,323,136 bytes**.
- A rough known peak disk floor if the 653,373,223-byte NAIA test copy, compressed candidates, full AMD archive expansion, and all model files coexist is **12,078,212,274 bytes**, before ComfyUI source/expanded runtime, Python's installed footprint, unresolved direct and transitive requirement wheels, temporary build/install copies, logs, and user-selected model assets.
- These are lower bounds, **not a full size cap**. A defensible finite total download/disk ceiling cannot be stated until the exact ComfyUI direct/transitive lock and Python / ComfyUI installed sizes are resolved. If verified existing model files are reused, subtract their download sizes only; keep their installed bytes in disk accounting.

The existing pinned NVIDIA portable archive size is historical comparison only and is not additive to the AMD plan. AMD runtime must come from a documented AMD-compatible ComfyUI source/distribution and the locked AMD interpreter/dependencies. Source checkout size and expanded ComfyUI tree are unknown.

## Static ComfyUI ROCm behavior relevant to health checks

At ComfyUI v0.22.0, `comfy/model_management.py` uses `torch.device(torch.cuda.current_device())` as its ordinary GPU device; `torch.version.hip` is the HIP runtime version, `torch.version.rocm` is the ROCm package version, and `get_device_properties(...).gcnArchName` provides the gfx string. The reviewed candidate Torch wheel reports exact build `2.13.0+rocm10.0.0`, HIP `7.15.26333` and ROCm `10.0.0`; the health gate requires exact Torch build-string equality in both runtime probe and `/system_stats`, and checks HIP and ROCm separately. Thus AMD reports a PyTorch device type of `cuda` too. `server.py` `/system_stats` serializes device `type`/`index` and memory, but does not serialize HIP or gfx. A `type == hip` check is wrong, and `/system_stats` alone cannot prove HIP/AMD execution.

The private candidate transformer now invokes only the exact `runtime/python_embeded/python.exe` by absolute path with bytecode writes disabled and a fixed diagnostic snippet. It requires ROCm 10.0.0, HIP 7.15.26333, `torch.cuda.is_available()`, one visible device, current device 0 after HIP visibility mapping, exact `gcnArchName == gfx1201`, and agreement between that probe and `/system_stats` `devices[0]` (`type == cuda`, `index == 0`, positive VRAM). The candidate launcher explicitly disables ComfyUI dynamic VRAM/aimdo pending AMD validation. The gate is only in the unintegrated candidate transform: service/profile selection, receipt persistence, and the managed runtime factory still hardcode the NVIDIA identity. Keep probe JSON in a future managed runtime state/receipt and logs; never call bare `rocminfo` from PATH as an authority. Startup preflight proves runtime initialization only; successful managed ANIMA inference and measured GPU/VRAM use are still required.

## Remaining lock blockers

1. Resolve the full ComfyUI v0.22.0 requirements closure for CPython 3.13 Windows x86_64 with every URL, wheel tag, publisher hash, downloaded-byte observation, size, license, and dependency edge. The direct `comfy-aimdo==0.3.0` package has mixed evidence: PyPI README says Nvidia/CUDA only, while v0.3.0 source has a ROCm loader. The candidate command disables the optional dynamic-VRAM path, but its Windows wheel was not downloaded or inspected. The release portable archive's embedded inventory is not available in this source checkout.
2. Identify the official AMD-supported ComfyUI distribution/source corresponding to the proposed PyTorch 2.13.0/ROCm 10.0.0 wheel stack, and lock its exact source commit plus non-AMD package artifacts. Do not substitute the NVIDIA portable release.
3. Independently verify CPython installer signature/hash and total extracted Python/ComfyUI install footprint without running installers.
4. Keep Windows 11 26H2 marked unverified pending a controlled test. This does not block preparation; exclude 26H2 from any supported release profile until verified. Record the exact RX 9070 PnP ID, driver and gfx mapping for the test.
5. Wire and test the runtime profile through settings, install service, receipt validation, job creation and registry/restart paths. Current `settings.py::quick_receipt`, install journal/publish/receipt code, and `app/backend/server/anima_engine_service.py::_job` hardcode the NVIDIA identity. Test custom-node import and actual workflow on a separate NAIA copy; static Spectrum metadata does not prove GPU compatibility.
