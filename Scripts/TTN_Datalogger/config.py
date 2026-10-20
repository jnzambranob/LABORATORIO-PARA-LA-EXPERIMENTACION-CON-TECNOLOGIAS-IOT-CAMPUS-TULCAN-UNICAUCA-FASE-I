"""
Configuration manager for TTN Data Collector.
Loads settings from .env file and environment variables with built-in fallback.
"""

import os
from pathlib import Path
import sys

# Base directory for the collector script
BASE_DIR = Path(__file__).resolve().parent

# Ensure the module directory is in sys.path
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def _load_env_fallback(file_path: Path):
    """Simple built-in .env parser if python-dotenv is not available."""
    if not file_path.exists():
        return
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


# Try loading .env
env_path = BASE_DIR / ".env"
try:
    from dotenv import load_dotenv
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()
except ImportError:
    _load_env_fallback(env_path)


class Config:
    # TTN Server URL
    TTN_SERVER_URL: str = os.getenv("TTN_SERVER_URL", "https://nam1.cloud.thethings.network").rstrip("/")

    # Authentication
    TTN_API_KEY: str = os.getenv("TTN_API_KEY", "")

    # Target Application and Gateway IDs
    TTN_APP_ID: str = os.getenv("TTN_APP_ID", "")
    TTN_GATEWAY_ID: str = os.getenv("TTN_GATEWAY_ID", "")

    # Collection settings
    COLLECTION_MODE: str = os.getenv("COLLECTION_MODE", "continuous").lower()  # 'continuous' or 'count'
    MAX_PACKETS: int = int(os.getenv("MAX_PACKETS", "1000"))

    # Gateway stats polling interval in seconds
    GW_STATS_INTERVAL_S: int = int(os.getenv("GW_STATS_INTERVAL_S", "60"))

    # Periodic auto-export interval in seconds (0 to disable)
    AUTO_EXPORT_INTERVAL_S: int = int(os.getenv("AUTO_EXPORT_INTERVAL_S", "3600"))

    # Storage paths
    DATA_DIR: Path = BASE_DIR / os.getenv("DATA_DIR", "data")
    DB_PATH: Path = DATA_DIR / "ttn_data.db"
    LOG_PATH: Path = DATA_DIR / "collector.log"

    @classmethod
    def validate(cls, require_app: bool = True, require_gateway: bool = False):
        """Validate required configuration parameters."""
        errors = []

        if not cls.TTN_API_KEY or cls.TTN_API_KEY == "NNSXS.YOUR_API_KEY_HERE":
            errors.append("TTN_API_KEY no está configurada o contiene el valor por defecto. Añade tu API Key en scripts/ttn_data_collector/.env")

        if require_app and (not cls.TTN_APP_ID or cls.TTN_APP_ID == "your-application-id"):
            errors.append("TTN_APP_ID no está configurada. Añade el Application ID en scripts/ttn_data_collector/.env")

        if require_gateway and (not cls.TTN_GATEWAY_ID or cls.TTN_GATEWAY_ID == "your-gateway-id"):
            errors.append("TTN_GATEWAY_ID no está configurada. Añade el Gateway ID en scripts/ttn_data_collector/.env")

        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)

        if errors:
            raise ValueError("\n" + "\n".join(f"  ❌ {err}" for err in errors))

    @classmethod
    def get_events_url(cls) -> str:
        return f"{cls.TTN_SERVER_URL}/api/v3/events"

    @classmethod
    def get_gateway_stats_url(cls) -> str:
        return f"{cls.TTN_SERVER_URL}/api/v3/gs/gateways/{cls.TTN_GATEWAY_ID}/connection/stats"

    @classmethod
    def get_headers(cls) -> dict:
        return {
            "Authorization": f"Bearer {cls.TTN_API_KEY}",
            "Accept": "text/event-stream",
            "Content-Type": "application/json; charset=utf-8",
        }

    @classmethod
    def get_rest_headers(cls) -> dict:
        return {
            "Authorization": f"Bearer {cls.TTN_API_KEY}",
            "Accept": "application/json",
        }
