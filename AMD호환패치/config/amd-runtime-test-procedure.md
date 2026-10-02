# Separate AMD runtime test procedure (not executed)

This is a preparation checklist for a future test after dependency lock, source/transformer review, and explicit approval to install the exact listed software in an isolated copy. It does not authorize or start downloads, installation, NAIA, ComfyUI, model inference, or GPU diagnostics now. Do not target the original NAIA install or NAIA Python 3.12.10.

## Proposed isolated locations

- Read-only source: the NAIA 2.0.48 folder supplied by the user
- Fresh test copy: `D:\NAIA-AMD-Trial\NAIA-Portable-2.0.48`
- Separate managed runtime root: `D:\NAIA-AMD-Trial\managed-runtime`
- Temporary verified-download cache: `D:\NAIA-AMD-Trial\download-cache`
- Test output/diagnostics: `D:\NAIA-AMD-Trial\test-results`

These are planned names. Before execution, confirm available capacity; the present known floor is at least **12,078,212,274 bytes** if a full NAIA copy, known compressed files, AMD archive expansion, and all three model files coexist, plus unmeasured ComfyUI sources/dependencies, installed Python/runtime footprint and transient duplicate files. With exact-hash model reuse, download less; model files still occupy their existing disk space. A full finite bound cannot be requested/approved until the full ComfyUI lock and expanded runtime sizes are known.

## Steps after prerequisites and approval

1. Record source `RELEASE_MANIFEST.json`/`CHECKSUMS.sha256` results, NAIA version, selected source file hashes, Windows edition/build, exact Display Adapter PnP instance ID, driver version/date, and available disk space. Use Device Manager or the read-only `Get-PnpDevice -Class Display` / `pnputil /enum-devices /class Display /connected /drivers` output supplied by the user. Do not use WMI/CIM or try to bypass a denied query.
2. With NAIA closed, make a new test copy from the source into the proposed test directory. Preserve the source as read-only and never point the installer at it. Keep the managed runtime root outside the copy and outside `%APPDATA%`.
3. Resolve and pin every Python 3.13 Windows AMD wheel/source in a separate offline lock before install. Verify official URLs, tags, publisher metadata, license, hashes, and exact byte sizes; reject redirects and all unpinned transitive artifacts. Fetch only into `download-cache`; validate every byte digest before extraction. Do not include or execute any `.sdist` until its complete build closure is locked and reviewed. The current partial static metadata adds five exact root candidates but leaves the direct/transitive closure incomplete and no finite size ceiling is available.
4. Check model reuse before downloading. Reuse only a user-selected existing copy of each required model after size + exact SHA-256 verification and confirmation of the model license. Otherwise present each separately licensed official source URL and exact size for the user's selection. Do not ship them in the patch package.
5. Once the installer path is connected and the disabled-manifest gates have received their independent review, run the install command against the **test-copy** root with the managed runtime set to `D:\NAIA-AMD-Trial\managed-runtime`. Keep NVIDIA path and the original app untouched. No machine drivers, Defender, execution policy, PATH, or system environment settings are to be changed.
6. Before launching NAIA, run a read-only runtime-local preflight with the exact runtime Python executable (this is an example to execute only after approval):

```powershell
$Runtime = 'D:\NAIA-AMD-Trial\managed-runtime\runtime\r1-comfyui-0.22.0-amd-rocm10.0-py313\ComfyUI_windows_portable'
& "$Runtime\python_embeded\python.exe" -B -c "import json,torch; i=torch.cuda.current_device(); p=torch.cuda.get_device_properties(i); print(json.dumps({'torch':torch.__version__,'hip':torch.version.hip,'rocm':getattr(torch.version,'rocm',None),'cuda_available':torch.cuda.is_available(),'device_count':torch.cuda.device_count(),'current_device':i,'name':torch.cuda.get_device_name(i),'gfx':getattr(p,'gcnArchName',None),'total_memory':p.total_memory}, sort_keys=True))"
```

   Expected preflight: `torch.__version__ == "2.13.0+rocm10.0.0"`, `torch.version.rocm == "10.0.0"`, `torch.version.hip == "7.15.26333"` for the currently reviewed wheel candidate, CUDA API available, one visible device, logical device 0 after the approved HIP device selection, exact `gfx == "gfx1201"`, and matching ComfyUI `/system_stats` `pytorch_version` with exact equality plus device `type=cuda`, `index=0`, positive VRAM. The candidate launcher also passes `--disable-dynamic-vram` until comfy-aimdo's AMD runtime behavior has been reviewed. Save sanitized JSON. The runtime executable is absolute and local; do not use `rocminfo` from PATH as proof. This only validates that ROCm PyTorch sees a selected device; it does not validate ANIMA inference.
7. Launch only the NAIA **test copy**, select its managed ANIMA profile, and run one small, fixed 512×512 or lowest accepted resolution, batch 1, low-step noncommercial test prompt with one seed and no optional LoRAs. First identify the exact model license and use constraints. Avoid spending or network features. If and only if the exact models are unavailable, ask the user to select a separately licensed checkpoint and include its exact sizes in the consent scope; do not improvise with an incompatible small model.
8. Capture ComfyUI and NAIA logs, the prompt/job result, pre/post `/system_stats`, runtime-local PyTorch/HIP/gfx probe, GPU/VRAM graph during the run (Task Manager GPU performance or AMD Adrenalin; not `nvidia-smi`), and CPU utilization. Verify the generated output is valid and logs show GPU model execution, not only device enumeration. Compare idle vs generation VRAM and GPU engine load; record any CPU fallback/unsupported operator. Run a separate Boost/Assist Vulkan GPU-vs-CPU comparison only under its own diagnostic plan; ANIMA evidence does not establish Vulkan acceleration.

## Rollback and preservation

1. Stop generation, close NAIA in the test copy, and confirm its managed ComfyUI child process exits.
2. Run the package `Uninstall.cmd` only with the explicit test-copy root. The transaction should restore only files that still match its installed hashes; record any conflict rather than overwriting user changes.
3. Verify the three patched-file hashes match `config/source-baseline.json`, verify the install receipt/journal reports restoration, and check no process references the managed runtime root.
4. Keep the runtime, download cache, diagnostic logs, and backups until validation is reviewed. If cleanup is approved later, remove only installer-created paths under `D:\NAIA-AMD-Trial`; preserve any existing/selected model asset, user-added files, or conflict report.

## Current execution blockers

- The patcher is a foundation and manifest/trust policy remains disabled; it currently cannot install the AMD profile.
- No full ComfyUI 0.22.0 Python 3.13 AMD dependency lock or expanded runtime capacity estimate exists yet.
- The `comfy-aimdo==0.3.0` PyPI description claims Nvidia/CUDA support, although its v0.3.0 Python source recognizes `+rocm` and selects an `aimdo_rocm` library. The exact Windows wheel payload, license, and AMD behavior remain uninspected; candidate runs must keep dynamic VRAM disabled pending that review.
- Candidate health gate now distinguishes HIP runtime `7.15.26333` from ROCm package `10.0.0`; this metadata match is synthetic and has not been hardware-validated.
- Windows 11 26H2 is unverified pending a controlled test; that does not block preparation. Keep it out of any supported release profile until verified.
- Exact PnP ID/driver, extension/workflow import, actual inference, performance and no-CPU-fallback evidence are not yet available.


