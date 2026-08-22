"""
Vercel serverless entry point.

Vercel's Python runtime looks for a WSGI-compatible `app` object in this
file. We import the real Flask app from the project root and re-export it.

We also patch PuLP's bundled CBC solver binary to be executable — on
serverless platforms, files are often re-packaged and lose their
execute permission, which makes PuLP fail with a "solver not found" or
"permission denied" error even though the binary is right there.
"""
import os
import stat
import sys

# Make the project root importable (this file lives in /api)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def _fix_cbc_permissions():
    """Walk PuLP's install directory and chmod +x any solver binaries."""
    try:
        import pulp
        pulp_dir = os.path.dirname(pulp.__file__)
        for root, _dirs, files in os.walk(pulp_dir):
            for fname in files:
                if "cbc" in fname.lower() and not fname.endswith((".py", ".pyc", ".txt", ".md")):
                    fpath = os.path.join(root, fname)
                    try:
                        st = os.stat(fpath)
                        os.chmod(fpath, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
                    except OSError:
                        pass
    except Exception:
        pass  # best-effort — if this fails, the app will still try to run


_fix_cbc_permissions()

from app import app  # noqa: E402  (import after path/permission setup)

# Vercel's Python runtime serves this `app` object directly (WSGI).
