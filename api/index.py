"""Vercel Python serverless entry point.

Vercel looks for a callable named `handler` in api/index.py and invokes it
for every request matched by the /api/* route in vercel.json.

How it works
------------
1. We add the monorepo root to sys.path so `backend.app` is importable.
2. We import the FastAPI `app` object (the same one used in Docker).
3. Mangum translates between Vercel's AWS-Lambda-style event envelope and
   ASGI, then delegates to FastAPI.

Cold-start note
---------------
The first request after a Vercel cold-start will load all Python modules and
the pre-fetched data snapshots from disk (~100-300 ms typically).  Subsequent
warm requests are fast because the module-level cache is reused.
"""

import os
import sys

# Make 'backend' importable as a top-level package from the repo root,
# and also add backend/ itself so that intra-package imports like
# `from app.config import settings` (used inside backend/app/*.py) resolve.
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_backend_dir = os.path.join(_repo_root, "backend")
for _p in (_repo_root, _backend_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from mangum import Mangum  # noqa: E402 – must come after sys.path patch
from backend.app.main import app  # noqa: E402

# lifespan="off" tells Mangum not to attempt ASGI lifespan events, which
# are not supported in the Vercel Lambda environment.
handler = Mangum(app, lifespan="off")
