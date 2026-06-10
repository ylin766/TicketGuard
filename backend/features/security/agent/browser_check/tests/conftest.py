"""Put the repo root (parent of ``backend``) on sys.path for these tests.

The browser-check modules use intra-package relative imports, so they must be
imported as ``backend.features.security.agent.browser_check.*``. Adding the repo
root lets ``import backend...`` resolve regardless of where pytest is invoked.
"""

import os
import sys

# .../backend/features/security/agent/browser_check/tests -> up 6 = repo root.
_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "..")
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
