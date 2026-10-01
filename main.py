"""NAIA API v1 entry point for the AMD runtime project."""


def register(ctx):
    """Register the scaffold without changing the selected NAIA backend."""
    ctx.log("NAIA ROCm runtime scaffold loaded; no backend changes applied.")

