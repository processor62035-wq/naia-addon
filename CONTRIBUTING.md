# Development notes

- Keep the existing NVIDIA route available and default unless a user explicitly selects another backend.
- Do not copy NAIA binaries, embedded runtimes, models, generated outputs, or `user-data` into this repository.
- Do not copy the installed `naia_exten` implementation; use only its documented API v1 shape as an interface reference.
- Do not commit account tokens, local settings, logs, SQLite/Parquet history, machine-specific paths, or downloaded assets.
- Keep AMD runtimes and dependencies isolated from the host's embedded Python and from the NVIDIA runtime.
- Run unit tests and compile checks in cloud. Label GPU integration as unverified until tested on the exact Radeon model/OS/driver.
- Do not modify the source app in place. Any patch workflow must target a separate copy and provide backup plus restore.
- Repository license is pending owner selection; do not add a license file or reuse third-party code until licensing is resolved.

