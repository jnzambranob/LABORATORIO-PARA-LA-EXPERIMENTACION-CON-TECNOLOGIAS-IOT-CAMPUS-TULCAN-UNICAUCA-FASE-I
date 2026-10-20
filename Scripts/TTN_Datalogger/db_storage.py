"""
SQLite Storage module for TTN Data Collector.
Provides thread-safe persistence and session-isolated metric tracking for uplinks, downlinks, and gateway stats.
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class Database:
    """Thread-safe SQLite wrapper for TTN metrics persistence with multi-session support."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")  # Better concurrent read/write performance
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def init_db(self):
        """Initializes database tables, indexes, views, and performs schema migrations & repairs."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 0. Sessions table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id          TEXT PRIMARY KEY,
                    started_at          TEXT NOT NULL,
                    ended_at            TEXT,
                    app_id              TEXT,
                    gateway_id          TEXT,
                    collection_mode     TEXT,
                    notes               TEXT
                );
                """)

                # 1. Uplinks table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS uplinks (
                    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id              TEXT,
                    timestamp_utc           TEXT NOT NULL,
                    device_id               TEXT NOT NULL,
                    gateway_id              TEXT,
                    rssi_dbm                REAL,
                    snr_db                  REAL,
                    gateway_time            TEXT,
                    concentrator_us         INTEGER,
                    received_at             TEXT,
                    airtime_s               REAL,
                    network_delay_s         REAL,
                    total_uplink_delay_s    REAL,
                    sf                      INTEGER,
                    bw_hz                   INTEGER,
                    coding_rate             TEXT,
                    frequency_hz            INTEGER,
                    f_cnt                   INTEGER,
                    channel_idx             INTEGER,
                    is_confirmed            INTEGER DEFAULT 0,
                    payload_raw             TEXT,
                    decoded_json            TEXT,
                    correlation_id          TEXT
                );
                """)

                # 2. Downlinks table (Tracks ACK lifecycles)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS downlinks (
                    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id              TEXT,
                    timestamp_utc           TEXT NOT NULL,
                    device_id               TEXT NOT NULL,
                    event_name              TEXT NOT NULL,
                    correlation_id          TEXT,
                    f_port                  INTEGER,
                    is_confirmed            INTEGER DEFAULT 0,
                    airtime_downlink_s      REAL,
                    schedule_attempt_at     TEXT,
                    schedule_success_at     TEXT,
                    gs_send_at              TEXT,
                    tx_success_at           TEXT,
                    raw_json                TEXT
                );
                """)

                # 3. Gateway Stats table (Periodic snapshots)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS gateway_stats (
                    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id                  TEXT,
                    polled_at                   TEXT NOT NULL,
                    gateway_id                  TEXT NOT NULL,
                    connected_at                TEXT,
                    last_uplink_received_at     TEXT,
                    last_downlink_received_at   TEXT,
                    last_status_received_at     TEXT,
                    uplink_count                INTEGER,
                    downlink_count              INTEGER,
                    raw_json                    TEXT
                );
                """)

                # Run migrations in case tables existed previously without columns
                for table in ("uplinks", "downlinks", "gateway_stats"):
                    cursor.execute(f"PRAGMA table_info({table});")
                    cols = [row["name"] for row in cursor.fetchall()]
                    if "session_id" not in cols:
                        cursor.execute(f"ALTER TABLE {table} ADD COLUMN session_id TEXT;")

                cursor.execute("PRAGMA table_info(uplinks);")
                uplink_cols = [row["name"] for row in cursor.fetchall()]
                if "total_uplink_delay_s" not in uplink_cols:
                    cursor.execute("ALTER TABLE uplinks ADD COLUMN total_uplink_delay_s REAL;")

                cursor.execute("PRAGMA table_info(downlinks);")
                downlink_cols = [row["name"] for row in cursor.fetchall()]
                if "airtime_downlink_s" not in downlink_cols:
                    cursor.execute("ALTER TABLE downlinks ADD COLUMN airtime_downlink_s REAL;")

                # Auto-calculate and update total_uplink_delay_s (E2E Uplink Latency = Airtime + Network Delay)
                cursor.execute("""
                UPDATE uplinks SET
                    total_uplink_delay_s = ROUND(airtime_s + network_delay_s, 6)
                WHERE airtime_s IS NOT NULL AND network_delay_s IS NOT NULL;
                """)

                # Indexes for fast lookup and join performance
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_uplinks_dev ON uplinks(device_id);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_uplinks_sess ON uplinks(session_id);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_uplinks_time ON uplinks(timestamp_utc);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_uplinks_cid ON uplinks(correlation_id);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_downlinks_dev ON downlinks(device_id);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_downlinks_sess ON downlinks(session_id);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_downlinks_cid ON downlinks(correlation_id);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_gw_stats_polled ON gateway_stats(polled_at);")

                # View: Uplink to Downlink ACK RTT Analysis
                cursor.execute("DROP VIEW IF EXISTS uplink_downlink_rtt;")
                cursor.execute("""
                CREATE VIEW uplink_downlink_rtt AS
                SELECT 
                    u.id AS uplink_id,
                    u.session_id,
                    u.timestamp_utc,
                    u.device_id,
                    u.gateway_id,
                    u.rssi_dbm,
                    u.snr_db,
                    u.sf,
                    u.bw_hz,
                    u.frequency_hz,
                    u.f_cnt,
                    u.airtime_s,
                    u.network_delay_s,
                    u.total_uplink_delay_s,
                    u.is_confirmed,
                    u.gateway_time,
                    u.received_at,
                    COALESCE(d.airtime_downlink_s, 0.0182) AS airtime_downlink_s,
                    d.schedule_attempt_at,
                    d.schedule_success_at,
                    d.gs_send_at,
                    d.tx_success_at,
                    -- Network Infrastructure RTT (From Gateway Uplink RX to Gateway Downlink ACK Schedule) in seconds
                    CASE 
                        WHEN d.tx_success_at IS NOT NULL AND u.gateway_time IS NOT NULL 
                        THEN (julianday(d.tx_success_at) - julianday(u.gateway_time)) * 86400.0
                        WHEN d.tx_success_at IS NOT NULL AND u.received_at IS NOT NULL
                        THEN (julianday(d.tx_success_at) - julianday(u.received_at)) * 86400.0
                        ELSE NULL
                    END AS rtt_s,
                    -- Complete Physical RTT (Uplink Airtime + Network RTT + Downlink Airtime) in seconds
                    CASE 
                        WHEN d.tx_success_at IS NOT NULL AND u.gateway_time IS NOT NULL 
                        THEN (julianday(d.tx_success_at) - julianday(u.gateway_time)) * 86400.0 + COALESCE(u.airtime_s, 0.0719) + COALESCE(d.airtime_downlink_s, 0.0182)
                        WHEN d.tx_success_at IS NOT NULL AND u.received_at IS NOT NULL
                        THEN (julianday(d.tx_success_at) - julianday(u.received_at)) * 86400.0 + COALESCE(u.airtime_s, 0.0719) + COALESCE(d.airtime_downlink_s, 0.0182)
                        ELSE NULL
                    END AS rtt_phy_complete,
                    -- Effective Downlink Window Buffer Delay AU915 (5000 ms - rtt_s) in seconds
                    CASE 
                        WHEN d.tx_success_at IS NOT NULL AND u.gateway_time IS NOT NULL 
                        THEN 5.0 - ((julianday(d.tx_success_at) - julianday(u.gateway_time)) * 86400.0)
                        WHEN d.tx_success_at IS NOT NULL AND u.received_at IS NOT NULL
                        THEN 5.0 - ((julianday(d.tx_success_at) - julianday(u.received_at)) * 86400.0)
                        ELSE NULL
                    END AS effective_dl_window_delay_au915,
                    -- Server Cloud Turnaround Time (Internal TTN Processing: received_at to gs_send_at) in seconds
                    CASE 
                        WHEN d.gs_send_at IS NOT NULL AND u.received_at IS NOT NULL
                        THEN (julianday(d.gs_send_at) - julianday(u.received_at)) * 86400.0
                        ELSE NULL
                    END AS cloud_turnaround_s,
                    -- Network Server Scheduling Latency in seconds
                    CASE 
                        WHEN d.schedule_success_at IS NOT NULL AND d.schedule_attempt_at IS NOT NULL
                        THEN (julianday(d.schedule_success_at) - julianday(d.schedule_attempt_at)) * 86400.0
                        ELSE NULL
                    END AS ns_scheduling_s,
                    -- Gateway Transmission Transit Delay in seconds
                    CASE 
                        WHEN d.tx_success_at IS NOT NULL AND d.gs_send_at IS NOT NULL
                        THEN (julianday(d.tx_success_at) - julianday(d.gs_send_at)) * 86400.0
                        ELSE NULL
                    END AS tx_delay_s
                FROM uplinks u
                LEFT JOIN downlinks d ON (
                    u.correlation_id IS NOT NULL AND d.correlation_id IS NOT NULL AND u.correlation_id = d.correlation_id
                ) OR (
                    u.correlation_id IS NULL AND u.device_id = d.device_id 
                    AND abs((julianday(d.timestamp_utc) - julianday(u.timestamp_utc)) * 86400.0) < 5.0
                );
                """)
                conn.commit()

    # --------------------------------------------------------------------------
    # Session Management Methods
    # --------------------------------------------------------------------------
    def start_session(self, session_id: str, app_id: str = "", gateway_id: str = "", mode: str = "continuous") -> str:
        """Registers a new execution session in the database."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT OR REPLACE INTO sessions (
                    session_id, started_at, app_id, gateway_id, collection_mode
                ) VALUES (?, ?, ?, ?, ?);
                """, (session_id, datetime.now(timezone.utc).isoformat(), app_id, gateway_id, mode))
                conn.commit()
                return session_id

    def end_session(self, session_id: str):
        """Marks a session as completed with the current timestamp."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                UPDATE sessions SET ended_at = ? WHERE session_id = ?;
                """, (datetime.now(timezone.utc).isoformat(), session_id))
                conn.commit()

    def get_latest_session_id(self) -> Optional[str]:
        """Returns the most recent session_id from the database."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT session_id FROM sessions ORDER BY started_at DESC LIMIT 1;")
                row = cursor.fetchone()
                if row:
                    return row["session_id"]
                # Fallback to uplinks if sessions table was empty
                cursor.execute("SELECT session_id FROM uplinks WHERE session_id IS NOT NULL ORDER BY id DESC LIMIT 1;")
                row = cursor.fetchone()
                return row["session_id"] if row else None

    def fetch_all_sessions(self) -> List[Dict[str, Any]]:
        """Returns a list of all recorded sessions with packet summary and PDR."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM sessions ORDER BY started_at DESC;")
                sessions = [dict(row) for row in cursor.fetchall()]
                for s in sessions:
                    sid = s["session_id"]
                    cursor.execute("SELECT COUNT(*) FROM uplinks WHERE session_id = ?;", (sid,))
                    s["uplinks_count"] = cursor.fetchone()[0]
                    cursor.execute("SELECT COUNT(*) FROM downlinks WHERE session_id = ?;", (sid,))
                    s["downlinks_count"] = cursor.fetchone()[0]
                    # Calculate session PDR
                    pdr_stats = self.get_pdr_statistics(session_id=sid)
                    total_expected = sum(d["expected_count"] for d in pdr_stats) if pdr_stats else 0
                    total_received = sum(d["received_count"] for d in pdr_stats) if pdr_stats else 0
                    s["pdr_percent"] = round((total_received / total_expected * 100.0), 2) if total_expected > 0 else 100.0
                return sessions

    # --------------------------------------------------------------------------
    # Data Ingestion Methods
    # --------------------------------------------------------------------------
    def insert_uplink(self, data: Dict[str, Any], session_id: Optional[str] = None) -> int:
        """Inserts an uplink record into SQLite with complete deduplication and updating."""
        correlation_id = data.get("correlation_id")
        dev_id = data.get("device_id", "unknown_device")
        sess_id = session_id or data.get("session_id")

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Deduplication check by correlation_id
                if correlation_id:
                    cursor.execute("SELECT id, device_id FROM uplinks WHERE correlation_id = ? LIMIT 1;", (correlation_id,))
                    row = cursor.fetchone()
                    if row:
                        target_dev = dev_id if dev_id not in ("unknown_device", "unknown") else row["device_id"]
                        cursor.execute("""
                        UPDATE uplinks SET
                            device_id = :device_id,
                            session_id = COALESCE(:session_id, session_id),
                            gateway_id = COALESCE(:gateway_id, gateway_id),
                            rssi_dbm = COALESCE(:rssi_dbm, rssi_dbm),
                            snr_db = COALESCE(:snr_db, snr_db),
                            gateway_time = COALESCE(:gateway_time, gateway_time),
                            concentrator_us = COALESCE(:concentrator_us, concentrator_us),
                            received_at = COALESCE(:received_at, received_at),
                            airtime_s = COALESCE(:airtime_s, airtime_s),
                            network_delay_s = COALESCE(:network_delay_s, network_delay_s),
                            total_uplink_delay_s = COALESCE(:total_uplink_delay_s, total_uplink_delay_s),
                            sf = COALESCE(:sf, sf),
                            bw_hz = COALESCE(:bw_hz, bw_hz),
                            coding_rate = COALESCE(:coding_rate, coding_rate),
                            frequency_hz = COALESCE(:frequency_hz, frequency_hz),
                            f_cnt = COALESCE(:f_cnt, f_cnt),
                            channel_idx = COALESCE(:channel_idx, channel_idx),
                            is_confirmed = :is_confirmed,
                            payload_raw = COALESCE(:payload_raw, payload_raw),
                            decoded_json = COALESCE(:decoded_json, decoded_json)
                        WHERE id = :id;
                        """, {
                            "id": row["id"],
                            "device_id": target_dev,
                            "session_id": sess_id,
                            "gateway_id": data.get("gateway_id"),
                            "rssi_dbm": data.get("rssi_dbm"),
                            "snr_db": data.get("snr_db"),
                            "gateway_time": data.get("gateway_time"),
                            "concentrator_us": data.get("concentrator_us"),
                            "received_at": data.get("received_at"),
                            "airtime_s": data.get("airtime_s"),
                            "network_delay_s": data.get("network_delay_s"),
                            "total_uplink_delay_s": data.get("total_uplink_delay_s"),
                            "sf": data.get("sf"),
                            "bw_hz": data.get("bw_hz"),
                            "coding_rate": data.get("coding_rate"),
                            "frequency_hz": data.get("frequency_hz"),
                            "f_cnt": data.get("f_cnt"),
                            "channel_idx": data.get("channel_idx"),
                            "is_confirmed": 1 if data.get("is_confirmed") else 0,
                            "payload_raw": data.get("payload_raw"),
                            "decoded_json": json.dumps(data.get("decoded_json")) if isinstance(data.get("decoded_json"), dict) else data.get("decoded_json"),
                        })
                        conn.commit()
                        return row["id"]

                cursor.execute("""
                INSERT INTO uplinks (
                    session_id, timestamp_utc, device_id, gateway_id, rssi_dbm, snr_db,
                    gateway_time, concentrator_us, received_at, airtime_s,
                    network_delay_s, total_uplink_delay_s, sf, bw_hz,
                    coding_rate, frequency_hz, f_cnt, channel_idx,
                    is_confirmed, payload_raw, decoded_json, correlation_id
                ) VALUES (
                    :session_id, :timestamp_utc, :device_id, :gateway_id, :rssi_dbm, :snr_db,
                    :gateway_time, :concentrator_us, :received_at, :airtime_s,
                    :network_delay_s, :total_uplink_delay_s, :sf, :bw_hz,
                    :coding_rate, :frequency_hz, :f_cnt, :channel_idx,
                    :is_confirmed, :payload_raw, :decoded_json, :correlation_id
                );
                """, {
                    "session_id": sess_id,
                    "timestamp_utc": data.get("timestamp_utc") or datetime.now(timezone.utc).isoformat(),
                    "device_id": dev_id,
                    "gateway_id": data.get("gateway_id"),
                    "rssi_dbm": data.get("rssi_dbm"),
                    "snr_db": data.get("snr_db"),
                    "gateway_time": data.get("gateway_time"),
                    "concentrator_us": data.get("concentrator_us"),
                    "received_at": data.get("received_at"),
                    "airtime_s": data.get("airtime_s"),
                    "network_delay_s": data.get("network_delay_s"),
                    "total_uplink_delay_s": data.get("total_uplink_delay_s"),
                    "sf": data.get("sf"),
                    "bw_hz": data.get("bw_hz"),
                    "coding_rate": data.get("coding_rate"),
                    "frequency_hz": data.get("frequency_hz"),
                    "f_cnt": data.get("f_cnt"),
                    "channel_idx": data.get("channel_idx"),
                    "is_confirmed": 1 if data.get("is_confirmed") else 0,
                    "payload_raw": data.get("payload_raw"),
                    "decoded_json": json.dumps(data.get("decoded_json")) if isinstance(data.get("decoded_json"), dict) else data.get("decoded_json"),
                    "correlation_id": correlation_id
                })
                conn.commit()
                return cursor.lastrowid

    def insert_or_update_downlink(self, data: Dict[str, Any], session_id: Optional[str] = None) -> int:
        """Inserts or updates a downlink event by correlation_id or device_id."""
        correlation_id = data.get("correlation_id")
        event_name = data.get("event_name", "")
        event_time = data.get("timestamp_utc") or datetime.now(timezone.utc).isoformat()
        sess_id = session_id or data.get("session_id")

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                row = None
                if correlation_id:
                    cursor.execute("SELECT id FROM downlinks WHERE correlation_id = ? ORDER BY id DESC LIMIT 1;", (correlation_id,))
                    row = cursor.fetchone()

                if row:
                    record_id = row["id"]
                    col_map = {
                        "ns.down.data.schedule.attempt": "schedule_attempt_at",
                        "ns.down.data.schedule.success": "schedule_success_at",
                        "gs.down.send": "gs_send_at",
                        "gs.down.tx.success": "tx_success_at",
                    }
                    col = col_map.get(event_name)
                    if col:
                        cursor.execute(f"UPDATE downlinks SET {col} = ? WHERE id = ?;", (event_time, record_id))
                    if data.get("airtime_downlink_s") is not None:
                        cursor.execute("UPDATE downlinks SET airtime_downlink_s = ? WHERE id = ?;", (data.get("airtime_downlink_s"), record_id))
                    conn.commit()
                    return record_id
                else:
                    cursor.execute("""
                    INSERT INTO downlinks (
                        session_id, timestamp_utc, device_id, event_name, correlation_id,
                        f_port, is_confirmed, airtime_downlink_s, schedule_attempt_at, schedule_success_at,
                        gs_send_at, tx_success_at, raw_json
                    ) VALUES (
                        :session_id, :timestamp_utc, :device_id, :event_name, :correlation_id,
                        :f_port, :is_confirmed, :airtime_downlink_s, :schedule_attempt_at, :schedule_success_at,
                        :gs_send_at, :tx_success_at, :raw_json
                    );
                    """, {
                        "session_id": sess_id,
                        "timestamp_utc": event_time,
                        "device_id": data.get("device_id", "unknown"),
                        "event_name": event_name,
                        "correlation_id": correlation_id,
                        "f_port": data.get("f_port"),
                        "is_confirmed": 1 if data.get("is_confirmed") else 0,
                        "airtime_downlink_s": data.get("airtime_downlink_s"),
                        "schedule_attempt_at": event_time if event_name == "ns.down.data.schedule.attempt" else data.get("schedule_attempt_at"),
                        "schedule_success_at": event_time if event_name == "ns.down.data.schedule.success" else data.get("schedule_success_at"),
                        "gs_send_at": event_time if event_name == "gs.down.send" else data.get("gs_send_at"),
                        "tx_success_at": event_time if event_name == "gs.down.tx.success" else data.get("tx_success_at"),
                        "raw_json": json.dumps(data.get("raw_json")) if isinstance(data.get("raw_json"), dict) else data.get("raw_json")
                    })
                    conn.commit()
                    return cursor.lastrowid

    def insert_gateway_stats(self, data: Dict[str, Any], session_id: Optional[str] = None) -> int:
        """Inserts a gateway connection stats snapshot."""
        sess_id = session_id or data.get("session_id")
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO gateway_stats (
                    session_id, polled_at, gateway_id, connected_at, last_uplink_received_at,
                    last_downlink_received_at, last_status_received_at,
                    uplink_count, downlink_count, raw_json
                ) VALUES (
                    :session_id, :polled_at, :gateway_id, :connected_at, :last_uplink_received_at,
                    :last_downlink_received_at, :last_status_received_at,
                    :uplink_count, :downlink_count, :raw_json
                );
                """, {
                    "session_id": sess_id,
                    "polled_at": data.get("polled_at") or datetime.now(timezone.utc).isoformat(),
                    "gateway_id": data.get("gateway_id", "unknown"),
                    "connected_at": data.get("connected_at"),
                    "last_uplink_received_at": data.get("last_uplink_received_at"),
                    "last_downlink_received_at": data.get("last_downlink_received_at"),
                    "last_status_received_at": data.get("last_status_received_at"),
                    "uplink_count": data.get("uplink_count"),
                    "downlink_count": data.get("downlink_count"),
                    "raw_json": json.dumps(data.get("raw_json")) if isinstance(data.get("raw_json"), dict) else data.get("raw_json")
                })
                conn.commit()
                return cursor.lastrowid

    # --------------------------------------------------------------------------
    # Retrieval and Statistics Methods (Session-Filtered)
    # --------------------------------------------------------------------------
    def get_counts(self, session_id: Optional[str] = None) -> Dict[str, int]:
        """Returns counts for uplinks, downlinks, and gateway stats for a session (or total)."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if session_id:
                    cursor.execute("SELECT COUNT(*) FROM uplinks WHERE session_id = ?;", (session_id,))
                    uplinks = cursor.fetchone()[0]
                    cursor.execute("SELECT COUNT(*) FROM downlinks WHERE session_id = ?;", (session_id,))
                    downlinks = cursor.fetchone()[0]
                    cursor.execute("SELECT COUNT(*) FROM gateway_stats WHERE session_id = ?;", (session_id,))
                    gw_stats = cursor.fetchone()[0]
                else:
                    cursor.execute("SELECT COUNT(*) FROM uplinks;")
                    uplinks = cursor.fetchone()[0]
                    cursor.execute("SELECT COUNT(*) FROM downlinks;")
                    downlinks = cursor.fetchone()[0]
                    cursor.execute("SELECT COUNT(*) FROM gateway_stats;")
                    gw_stats = cursor.fetchone()[0]
                return {"uplinks": uplinks, "downlinks": downlinks, "gateway_stats": gw_stats}

    def fetch_all_uplinks(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if session_id:
                    cursor.execute("SELECT * FROM uplinks WHERE session_id = ? ORDER BY id ASC;", (session_id,))
                else:
                    cursor.execute("SELECT * FROM uplinks ORDER BY id ASC;")
                return [dict(row) for row in cursor.fetchall()]

    def fetch_all_downlinks(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if session_id:
                    cursor.execute("SELECT * FROM downlinks WHERE session_id = ? ORDER BY id ASC;", (session_id,))
                else:
                    cursor.execute("SELECT * FROM downlinks ORDER BY id ASC;")
                return [dict(row) for row in cursor.fetchall()]

    def fetch_rtt_view(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if session_id:
                    cursor.execute("SELECT * FROM uplink_downlink_rtt WHERE session_id = ? ORDER BY uplink_id ASC;", (session_id,))
                else:
                    cursor.execute("SELECT * FROM uplink_downlink_rtt ORDER BY uplink_id ASC;")
                return [dict(row) for row in cursor.fetchall()]

    def fetch_gateway_stats(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if session_id:
                    cursor.execute("SELECT * FROM gateway_stats WHERE session_id = ? ORDER BY id ASC;", (session_id,))
                else:
                    cursor.execute("SELECT * FROM gateway_stats ORDER BY id ASC;")
                return [dict(row) for row in cursor.fetchall()]

    def get_pdr_statistics(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Calculates Packet Delivery Rate (PDR) and Packet Loss Rate (PLR) per device
        isolated specifically to the given session_id, robust against counter resets/reboots.
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if session_id:
                    cursor.execute("""
                    SELECT id, device_id, f_cnt
                    FROM uplinks
                    WHERE session_id = ?
                    ORDER BY id ASC;
                    """, (session_id,))
                else:
                    cursor.execute("""
                    SELECT id, device_id, f_cnt
                    FROM uplinks
                    ORDER BY id ASC;
                    """)
                rows = cursor.fetchall()

                # Group chronologically by device_id
                dev_packets: Dict[str, List[Optional[int]]] = {}
                for row in rows:
                    dev_id = row["device_id"]
                    if dev_id not in dev_packets:
                        dev_packets[dev_id] = []
                    dev_packets[dev_id].append(row["f_cnt"])

                results = []
                for dev_id, fcnt_list in sorted(dev_packets.items()):
                    recv_count = len(fcnt_list)
                    if not fcnt_list:
                        continue

                    # Segment into monotonic epochs (handles resets/reboots)
                    segments: List[List[int]] = []
                    current_segment: List[int] = []
                    none_count = 0

                    for f in fcnt_list:
                        if f is None:
                            none_count += 1
                            continue

                        if not current_segment:
                            current_segment.append(f)
                        else:
                            last_f = current_segment[-1]
                            if f > last_f:
                                # Monotonic progression
                                current_segment.append(f)
                            else:
                                # Counter reset / node reboot detected!
                                segments.append(current_segment)
                                current_segment = [f]

                    if current_segment:
                        segments.append(current_segment)

                    # Compute expected packets across all sequence segments
                    expected_count = 0
                    segment_ranges = []
                    for seg in segments:
                        s_min = seg[0]
                        s_max = max(seg)
                        expected_count += (s_max - s_min) + 1
                        segment_ranges.append(f"{s_min}-{s_max}")

                    expected_count += none_count
                    if expected_count < recv_count:
                        expected_count = recv_count

                    lost_count = max(0, expected_count - recv_count)
                    pdr = (recv_count / expected_count * 100.0) if expected_count > 0 else 100.0
                    pdr = min(100.0, pdr)
                    plr = max(0.0, 100.0 - pdr)
                    resets_detected = max(0, len(segments) - 1)

                    first_fcnt = segments[0][0] if segments else None
                    last_fcnt = segments[-1][-1] if segments else None
                    fcnt_range_str = ", ".join(segment_ranges) if segment_ranges else "N/A"

                    results.append({
                        "device_id": dev_id,
                        "min_fcnt": first_fcnt,
                        "max_fcnt": last_fcnt,
                        "fcnt_ranges": fcnt_range_str,
                        "resets_detected": resets_detected,
                        "expected_count": expected_count,
                        "received_count": recv_count,
                        "lost_count": lost_count,
                        "pdr_percent": round(pdr, 2),
                        "plr_percent": round(plr, 2),
                    })
                return results

    def get_summary_statistics(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Calculates statistical summary for RSSI, SNR, Delays, Airtime, E2E Latency, RTT, and PDR."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if session_id:
                    cursor.execute("""
                    SELECT 
                        COUNT(*) AS total_uplinks,
                        MIN(rssi_dbm) AS min_rssi,
                        AVG(rssi_dbm) AS avg_rssi,
                        MAX(rssi_dbm) AS max_rssi,
                        MIN(snr_db) AS min_snr,
                        AVG(snr_db) AS avg_snr,
                        MAX(snr_db) AS max_snr,
                        MIN(airtime_s) AS min_airtime,
                        AVG(airtime_s) AS avg_airtime,
                        MAX(airtime_s) AS max_airtime,
                        MIN(network_delay_s) AS min_delay,
                        AVG(network_delay_s) AS avg_delay,
                        MAX(network_delay_s) AS max_delay,
                        MIN(total_uplink_delay_s) AS min_total_uplink_delay,
                        AVG(total_uplink_delay_s) AS avg_total_uplink_delay,
                        MAX(total_uplink_delay_s) AS max_total_uplink_delay
                    FROM uplinks
                    WHERE session_id = ?;
                    """, (session_id,))
                    uplink_stats = dict(cursor.fetchone())

                    cursor.execute("""
                    SELECT 
                        COUNT(*) AS total_rtt_samples,
                        MIN(rtt_s) AS min_rtt,
                        AVG(rtt_s) AS avg_rtt,
                        MAX(rtt_s) AS max_rtt,
                        MIN(rtt_phy_complete) AS min_rtt_phy_complete,
                        AVG(rtt_phy_complete) AS avg_rtt_phy_complete,
                        MAX(rtt_phy_complete) AS max_rtt_phy_complete,
                        AVG(effective_dl_window_delay_au915) AS avg_effective_dl_window_delay_au915,
                        AVG(ns_scheduling_s) AS avg_ns_scheduling,
                        AVG(cloud_turnaround_s) AS avg_cloud_turnaround,
                        AVG(tx_delay_s) AS avg_tx_delay
                    FROM uplink_downlink_rtt
                    WHERE rtt_s IS NOT NULL AND session_id = ?;
                    """, (session_id,))
                    rtt_stats = dict(cursor.fetchone())
                else:
                    cursor.execute("""
                    SELECT 
                        COUNT(*) AS total_uplinks,
                        MIN(rssi_dbm) AS min_rssi,
                        AVG(rssi_dbm) AS avg_rssi,
                        MAX(rssi_dbm) AS max_rssi,
                        MIN(snr_db) AS min_snr,
                        AVG(snr_db) AS avg_snr,
                        MAX(snr_db) AS max_snr,
                        MIN(airtime_s) AS min_airtime,
                        AVG(airtime_s) AS avg_airtime,
                        MAX(airtime_s) AS max_airtime,
                        MIN(network_delay_s) AS min_delay,
                        AVG(network_delay_s) AS avg_delay,
                        MAX(network_delay_s) AS max_delay,
                        MIN(total_uplink_delay_s) AS min_total_uplink_delay,
                        AVG(total_uplink_delay_s) AS avg_total_uplink_delay,
                        MAX(total_uplink_delay_s) AS max_total_uplink_delay
                    FROM uplinks;
                    """)
                    uplink_stats = dict(cursor.fetchone())

                    cursor.execute("""
                    SELECT 
                        COUNT(*) AS total_rtt_samples,
                        MIN(rtt_s) AS min_rtt,
                        AVG(rtt_s) AS avg_rtt,
                        MAX(rtt_s) AS max_rtt,
                        MIN(rtt_phy_complete) AS min_rtt_phy_complete,
                        AVG(rtt_phy_complete) AS avg_rtt_phy_complete,
                        MAX(rtt_phy_complete) AS max_rtt_phy_complete,
                        AVG(effective_dl_window_delay_au915) AS avg_effective_dl_window_delay_au915,
                        AVG(ns_scheduling_s) AS avg_ns_scheduling,
                        AVG(cloud_turnaround_s) AS avg_cloud_turnaround,
                        AVG(tx_delay_s) AS avg_tx_delay
                    FROM uplink_downlink_rtt
                    WHERE rtt_s IS NOT NULL;
                    """)
                    rtt_stats = dict(cursor.fetchone())

                # Calculate PDR (isolated to session if provided)
                pdr_devices = self.get_pdr_statistics(session_id=session_id)
                total_expected = sum(d["expected_count"] for d in pdr_devices) if pdr_devices else 0
                total_received = sum(d["received_count"] for d in pdr_devices) if pdr_devices else 0
                total_lost = sum(d["lost_count"] for d in pdr_devices) if pdr_devices else 0

                global_pdr = (total_received / total_expected * 100.0) if total_expected > 0 else (100.0 if total_received > 0 else 0.0)
                global_pdr = min(100.0, global_pdr)
                global_plr = max(0.0, 100.0 - global_pdr) if total_expected > 0 else 0.0

                pdr_stats = {
                    "session_id": session_id,
                    "total_expected_packets": total_expected,
                    "total_received_packets": total_received,
                    "total_lost_packets": total_lost,
                    "global_pdr_percent": round(global_pdr, 2),
                    "global_plr_percent": round(global_plr, 2),
                    "devices_pdr": pdr_devices,
                }

                return {**uplink_stats, **rtt_stats, **pdr_stats}

    def clear_database(self, session_id: Optional[str] = None):
        """Clears records from tables (for a specific session or entire database)."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if session_id:
                    cursor.execute("DELETE FROM uplinks WHERE session_id = ?;", (session_id,))
                    cursor.execute("DELETE FROM downlinks WHERE session_id = ?;", (session_id,))
                    cursor.execute("DELETE FROM gateway_stats WHERE session_id = ?;", (session_id,))
                    cursor.execute("DELETE FROM sessions WHERE session_id = ?;", (session_id,))
                else:
                    cursor.execute("DELETE FROM uplinks;")
                    cursor.execute("DELETE FROM downlinks;")
                    cursor.execute("DELETE FROM gateway_stats;")
                    cursor.execute("DELETE FROM sessions;")
                conn.commit()
