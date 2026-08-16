"""
Launches ADK Web the same way `adk web` does, but through python.exe
directly instead of the adk.exe wrapper (which Smart App Control blocks
on some machines locally). Also works correctly on Cloud Run, which
assigns its own port via the PORT environment variable.

Run with: python run_web.py
"""
import os
import sys

from google.adk.cli.cli_tools_click import main

if __name__ == "__main__":
    port = os.environ.get("PORT", "8001")
    sys.argv = [
        "adk", "web",
        "--host", "0.0.0.0",
        "--port", port,
        "--allow_origins", "*",
    ]
    main()
