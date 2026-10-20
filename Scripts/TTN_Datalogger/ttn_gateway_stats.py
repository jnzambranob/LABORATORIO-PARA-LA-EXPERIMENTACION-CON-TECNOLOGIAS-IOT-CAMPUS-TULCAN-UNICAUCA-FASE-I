"""
Gateway connection statistics poller for TTN.
Periodically fetches GS (Gateway Server) statistics such as packet counters,
connection timestamps, and status updates.
"""

from datetime import datetime, timezone
import logging
import threading
import time
from typing import Any, Dict, Optional
import requests

from config import Config
from db_storage import Database

logger = logging.getLogger("ttn_collector")


class GatewayStatsPoller:
    """Polls TTN Gateway Server connection stats at configured intervals."""

    def __init__(self, db: Database, session_id: Optional[str] = None):
        self.db = db
        self.session_id = session_id
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Starts the gateway stats poller thread."""
        if not Config.TTN_GATEWAY_ID or Config.TTN_GATEWAY_ID == "your-gateway-id":
            logger.info("Gateway ID no especificado. Omitiendo sondeo de estadísticas del Gateway.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stops the gateway stats poller thread."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def fetch_stats_once(self) -> Optional[Dict[str, Any]]:
        """Makes a single GET request to retrieve gateway connection stats."""
        if not Config.TTN_GATEWAY_ID or Config.TTN_GATEWAY_ID == "your-gateway-id":
            return None

        url = Config.get_gateway_stats_url()
        headers = Config.get_rest_headers()

        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                stats_json = response.json()
                processed = {
                    "session_id": self.session_id,
                    "polled_at": datetime.now(timezone.utc).isoformat(),
                    "gateway_id": Config.TTN_GATEWAY_ID,
                    "connected_at": stats_json.get("connected_at"),
                    "last_uplink_received_at": stats_json.get("last_uplink_received_at"),
                    "last_downlink_received_at": stats_json.get("last_downlink_received_at"),
                    "last_status_received_at": stats_json.get("last_status_received_at"),
                    "uplink_count": stats_json.get("uplink_count") or stats_json.get("rx_ok", 0),
                    "downlink_count": stats_json.get("downlink_count") or stats_json.get("tx_in", 0),
                    "raw_json": stats_json,
                }
                self.db.insert_gateway_stats(processed, session_id=self.session_id)
                logger.debug(f"Estadísticas del gateway actualizadas: {processed['uplink_count']} rx / {processed['downlink_count']} tx")
                return processed
            elif response.status_code == 404:
                logger.debug(f"Gateway {Config.TTN_GATEWAY_ID} no encontrado o desconectado en este momento.")
            else:
                logger.debug(f"Error consultando stats del gateway ({response.status_code}): {response.text[:100]}")
        except Exception as e:
            logger.debug(f"Error en consulta de gateway stats: {e}")
        return None

    def _run_poll_loop(self):
        """Background polling loop."""
        interval = max(10, Config.GW_STATS_INTERVAL_S)
        logger.info(f"Iniciando sondeo de estadísticas del Gateway cada {interval}s...")

        # Immediate first fetch
        self.fetch_stats_once()

        while not self._stop_event.is_set():
            if self._stop_event.wait(timeout=interval):
                break
            self.fetch_stats_once()
