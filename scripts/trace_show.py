"""Run app.tools.trace_show from the repository root: python scripts/trace_show.py --help

The implementation lives in the api package (api/app/tools/trace_show.py) so the same command
also runs inside an api pod, where the trace volume is mounted:
    kubectl exec -n rahbar deploy/api -- python -m app.tools.trace_show ...
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from app.tools.trace_show import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
