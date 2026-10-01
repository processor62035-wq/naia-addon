# Patch source and provenance

This repository contains the installer and a small source transformer written for the NAIA Portable 2.0.48 ANIMA integration points. It does not include the NAIA application, complete source modules, models, or runtime binaries.

The transformer refers to three exact baseline file hashes in `source-baseline.json` and uses short function/signature anchors to construct changes against files already present in the user's local application. It does not carry replacement copies of the source files. Before any future enabled release, review whether the target application's exact files and these minimal anchors may be used and distributed under applicable terms.

The exact v2.0.48 target tag resolves to DNT-LAB/NAIA2.0 commit 6e97c7f4f37e495ad21657ed29d28dd9993a808e; its root LICENSE is GNU GPL version 3. The transformer carries a GPL-3.0-only notice and the upstream license text is retained in THIRD_PARTY_LICENSES/GPL-3.0.txt. This does not add a repository-wide license or grant rights to other application or third-party components. The locally staged AMD wheels and source archive are excluded from the public tree; their observed hashes are provenance evidence only and are not trusted publisher checksums.

The current manifest is disabled and has no accepted artifact list or trusted manifest pin. This is an experimental, non-installable foundation.
