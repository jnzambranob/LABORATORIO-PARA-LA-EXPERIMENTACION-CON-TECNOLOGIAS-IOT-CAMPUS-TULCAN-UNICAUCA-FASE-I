"""
The Things Network Events Stream Client (HTTP SSE / gRPC-equivalent).
Subscribes to live uplink and downlink event streams with automatic reconnection.
"""

import json
import logging
import time
import threading
from typing import Callable, Optional
import requests

from config import Config
from data_processor import process_uplink_event, process_downlink_event, unwrap_event
from db_storage import Database

logger = logging.getLogger("ttn_collector")


class TTNEventsClient:
    """Manages the long-lived SSE connection to TTN /api/v3/events."""

    def __init__(self, db: Database, session_id: Optional[str] = None, on_event_callback: Optional[Callable[[str, dict], None]] = None):
        self.db = db
        self.session_id = session_id
        self.on_event_callback = on_event_callback
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._current_response: Optional[requests.Response] = None

    def _build_subscription_payload(self) -> dict:
        """Constructs the JSON body to subscribe to application and gateway events."""
        identifiers = []
        if Config.TTN_APP_ID:
            identifiers.append({"application_ids": {"application_id": Config.TTN_APP_ID}})
        if Config.TTN_GATEWAY_ID:
            identifiers.append({"gateway_ids": {"gateway_id": Config.TTN_GATEWAY_ID}})
        return {"identifiers": identifiers}

    def start(self):
        """Starts the event stream listener in a background thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_stream_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Signals the listener to stop and closes the active HTTP stream immediately."""
        self._stop_event.set()
        if self._current_response:
            try:
                self._current_response.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _run_stream_loop(self):
        """Continuous stream loop with exponential backoff for long-running sessions (up to 5 days)."""
        backoff_s = 2.0
        max_backoff_s = 30.0

        while not self._stop_event.is_set():
            url = Config.get_events_url()
            headers = Config.get_headers()
            payload = self._build_subscription_payload()

            logger.info(f"Conectando al stream de eventos de TTN ({url})...")
            try:
                with requests.post(url, headers=headers, json=payload, stream=True, timeout=(15, None)) as response:
                    self._current_response = response
                    if response.status_code == 401 or response.status_code == 403:
                        logger.error(f"Error de autenticación ({response.status_code}): {response.text[:200]}")
                        time.sleep(5.0)
                        continue

                    if response.status_code != 200:
                        logger.warning(f"Respuesta no esperada del servidor TTN: {response.status_code} - {response.text[:200]}")
                        time.sleep(backoff_s)
                        backoff_s = min(backoff_s * 1.5, max_backoff_s)
                        continue

                    logger.info("✅ Conexión establecida con el stream de eventos TTN. Esperando paquetes...")
                    backoff_s = 2.0  # Reset backoff on successful connection

                    for line in response.iter_lines(chunk_size=1, decode_unicode=True):
                        if self._stop_event.is_set():
                            break

                        if not line:
                            continue

                        # Clean line if it starts with SSE "data: " prefix
                        raw_line = line.strip()
                        if raw_line.startswith("data:"):
                            raw_line = raw_line[5:].strip()

                        if not raw_line or raw_line.startswith(":"):  # SSE comments / keepalives
                            continue

                        try:
                            raw_dict = json.loads(raw_line)
                            event_dict = unwrap_event(raw_dict)
                            self._handle_incoming_event(event_dict)
                        except json.JSONDecodeError:
                            logger.debug(f"Línea no decodificable como JSON: {raw_line[:100]}")
                        except Exception as e:
                            logger.error(f"Error procesando evento: {e}", exc_info=True)

            except requests.exceptions.RequestException as e:
                if not self._stop_event.is_set():
                    logger.warning(f"Pérdida de conexión con TTN: {e}. Reconectando en {backoff_s:.1f}s...")
                    time.sleep(backoff_s)
                    backoff_s = min(backoff_s * 1.5, max_backoff_s)
            except Exception as e:
                if not self._stop_event.is_set():
                    logger.error(f"Error inesperado en stream loop: {e}", exc_info=True)
                    time.sleep(backoff_s)

    def _handle_incoming_event(self, event_dict: dict):
        """Routes incoming events based on their name (uplink vs downlink ACK)."""
        event_name = event_dict.get("name", "")

        # 1. Uplink Events (Application or Gateway level)
        if event_name in ("as.up.data.forward", "as.up.data.receive", "as.up.join.receive") or event_name.startswith("as.up."):
            # Canonical Application Uplink (Contains resolved device_id, decrypted payload, and gateway metadata)
            processed = process_uplink_event(event_dict)
            row_id = self.db.insert_uplink(processed, session_id=self.session_id)
            rssi_str = f"{processed['rssi_dbm']:.1f}" if processed['rssi_dbm'] is not None else "N/A"
            snr_str = f"{processed['snr_db']:.1f}" if processed['snr_db'] is not None else "N/A"
            airtime_str = f"{processed['airtime_s']:.4f}" if processed['airtime_s'] is not None else "N/A"
            delay_str = f"{processed['network_delay_s']:.4f}" if processed['network_delay_s'] is not None else "N/A"
            sf_str = f"SF{processed['sf']}" if processed['sf'] is not None else "SF?"

            logger.info(
                f"[UPLINK #{row_id}] Dev: {processed['device_id']} | "
                f"RSSI: {rssi_str} dBm | SNR: {snr_str} dB | "
                f"{sf_str} | Airtime: {airtime_str}s | "
                f"Delay: {delay_str}s | FCnt: {processed['f_cnt']}"
            )
            if self.on_event_callback:
                self.on_event_callback("uplink", processed)

        elif event_name in ("gs.up.receive", "ns.up.data.receive"):
            # Gateway/Network layer reception:
            # When TTN_APP_ID is configured, the canonical as.up.data.forward event provides the complete decoded uplink.
            # We only insert gs.up.receive if running in gateway-only mode (no application ID configured).
            if not Config.TTN_APP_ID or Config.TTN_APP_ID == "your-application-id":
                processed = process_uplink_event(event_dict)
                row_id = self.db.insert_uplink(processed, session_id=self.session_id)
                logger.info(
                    f"[UPLINK GW #{row_id}] Dev: {processed['device_id']} | "
                    f"RSSI: {processed['rssi_dbm']} dBm | SNR: {processed['snr_db']} dB"
                )
                if self.on_event_callback:
                    self.on_event_callback("uplink", processed)

        # 2. Downlink ACK Lifecycle Events
        elif (
            any(event_name.startswith(pfx) for pfx in ("ns.down.data.schedule", "gs.down.send", "gs.down.tx", "as.down.data"))
            or ".down." in event_name
        ):
            processed = process_downlink_event(event_dict)
            row_id = self.db.insert_or_update_downlink(processed, session_id=self.session_id)
            logger.info(
                f"[DOWNLINK ACK #{row_id}] Event: {event_name} | "
                f"Dev: {processed['device_id']} | CID: {processed['correlation_id']}"
            )
            if self.on_event_callback:
                self.on_event_callback("downlink", processed)

        # 3. Gateway Status Updates
        elif event_name == "gs.status.receive":
            logger.debug(f"[GATEWAY STATUS] Gateway {Config.TTN_GATEWAY_ID} transmitió paquete de estado.")
