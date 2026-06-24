"""Central config for the discover tool — reads from environment variables
with sensible defaults."""
import os
from pathlib import Path

# Tool root = parent of this file's parent
TOOL_ROOT = Path(__file__).parent.parent

LITKIT_CONFIG = Path(os.environ.get(
    "LITKIT_CONFIG",
    str(TOOL_ROOT / "references" / "search-config-example.json")
))
LITKIT_OUTPUT = Path(os.environ.get(
    "LITKIT_OUTPUT",
    "/tmp/litkit-discover"
))
ENTREZ_EMAIL = os.environ.get("ENTREZ_EMAIL", "")
S2_API_KEY = os.environ.get("S2_API_KEY", "")
