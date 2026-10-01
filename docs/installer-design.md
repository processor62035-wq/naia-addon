# Windows installer and reversible patch requirements

This is the implementation contract for the requested package. It is a specification, not an installer: the current repository scaffold does not patch NAIA or install ROCm.

## User flow

1. `Install.cmd` starts PowerShell with an explicit UAC prompt. The PowerShell UI offers English, Japanese, and Korean. A matching `Uninstall.cmd` invokes the safe restore flow with the same language selection.
2. Detect a supported NAIA Portable folder from the installer location and a small set of known locations. If there is no single clear match, open a folder picker. Never search the entire disk.
3. Confirm the selected folder is a complete, stopped NAIA Portable installation at the supported baseline. Refuse to modify a running app or an unknown version.
4. Detect installed display adapters and let the user choose an AMD adapter when more than one is present. Resolve exact device ID / `gfx` architecture, Windows version, and driver against the maintained support matrix. Do not infer support from RX generation alone. Unknown or unsupported combinations stop with a diagnostic report.
5. Select only artifacts for the verified GPU and platform. Downloads must use an allowlist of official AMD/ComfyUI sources and pinned versions; validate SHA-256 against a trusted manifest before extraction or patching. Do not bundle ROCm wheels, ComfyUI runtimes, or models with unclear redistribution terms.
6. Stage changes beside a separate app copy, back up every target file, then apply atomically. Record the original app version, backup location, original and installed hashes, created files, and changed-file list in an install receipt. Verify the expected post-patch hashes and preserve the original NVIDIA runtime as a selectable option.
7. `Uninstall.cmd` restores original files only when their current hashes still match the installed receipt. If the user or NAIA changed a patched file after installation, stop on that conflict and explain the safe recovery choices; never overwrite the newer file silently. Remove only package-created files that still match their recorded hashes. Preserve backups by default so the user can recover manually.

## Safety requirements

- Default to dry-run until version, target, GPU, and download checks pass.
- Do not target symlinks/junctions, a running application, the source folder, or an unrecognized NAIA version.
- Do not install ROCm/PyTorch into NAIA's embedded Python 3.12. Keep the AMD ComfyUI/Python 3.13 environment isolated from the NVIDIA package.
- Do not change Windows Defender, execution policy, driver settings, or global Python configuration.
- Never log or upload account tokens, app settings, prompts, generated images, or user history. A diagnostic report may include app version, selected GPU model/device ID, OS version, and artifact hashes only.
- Keep an explicit selection for the pre-existing NVIDIA runtime. A failed AMD start must report failure; any CPU fallback must be a visible user choice and must not be reported as AMD acceleration.
- Reinstall/update must retain the first clean backup and use an explicit, versioned transaction receipt. A failed or interrupted update must be recoverable. Do not delete backup files during uninstall.

## Test contract

Cloud tests should mock Windows discovery and downloads. They must cover language selection, ambiguous path selection, path traversal and link rejection, running-app rejection, multi-GPU selection, unsupported/unknown GPU refusal, artifact URL/hash mismatch refusal, staging atomicity, backup/restore byte equality, uninstall conflict refusal, removal of unchanged created files, reinstall/update, interrupted apply and partial restore recovery, NVIDIA profile preservation, and AMD profile selection. Tests must not run UAC, download packages, or touch a real NAIA installation.

Real hardware verification is a separate stage: record the exact Radeon model, OS build, driver, detected `gfx`, ROCm/PyTorch versions, `torch.version.hip`, device enumeration, a small tensor operation, a bounded ANIMA generation, GPU utilization/VRAM, and the final runtime log. Cloud CPU checks are not a substitute.

