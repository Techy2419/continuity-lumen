"""
Launches ADK Web the same way `adk web` does, but through python.exe
directly instead of the adk.exe wrapper (which Smart App Control blocks
on some machines).

Run with: python run_web.py
"""
import sys

from google.adk.cli.cli_tools_click import main

if __name__ == "__main__":
    sys.argv = [
        "adk", "web",
        "--port", "8001",
        "--allow_origins", "http://localhost:5500",
    ]
    main()
