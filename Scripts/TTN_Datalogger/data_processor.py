"""
Data processor module for TTN Data Collector.
Parses raw event payloads, extracts RF and network metadata,
and computes latency, airtime, End-to-End Uplink Delay, and Round-Trip-Time (RTT) metrics.
"""

from datetime import datetime, timezone
import math
import re
from typing import Any, Dict, List, Optional


def parse_iso_timestamp(ts_str: Optional[str]) -> Optional[datetime]:
    """Parses an ISO 8601 string (with 'Z' or offset, fractional seconds up to nanoseconds) into a datetime."""
    if not ts_str:
        return None
    try:
        clean_ts = str(ts_str).strip()
        if clean_ts.endswith("Z"):
            clean_ts = clean_ts[:-1] + "+00:00"

        # Handle nanoseconds by truncating to microseconds (6 digits)
        match = re.match(r"^(.*\.\d{1,6})\d*([+-].*)$", clean_ts)
        if match:
            clean_ts = match.group(1) + match.group(2)
        elif "." in clean_ts:
            match_no_tz = re.match(r"^(.*\.\d{1,6})\d*$", clean_ts)
            if match_no_tz:
                clean_ts = match_no_tz.group(1) + "+00:00"

        dt = datetime.fromisoformat(clean_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def parse_duration_seconds(duration_val: Any) -> Optional[float]:
    """Converts a duration representation (e.g. '0.056576s' or float) to seconds."""
    if duration_val is None:
        return None
    if isinstance(duration_val, (int, float)):
        return float(duration_val)
    if isinstance(duration_val, str):
        cleaned = duration_val.strip().rstrip("s")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def calculate_time_diff_seconds(t_end_str: Optional[str], t_start_str: Optional[str]) -> Optional[float]:
    """Computes (t_end - t_start) in seconds between two ISO 8601 timestamp strings."""
    dt_end = parse_iso_timestamp(t_end_str)
    dt_start = parse_iso_timestamp(t_start_str)
    if dt_end and dt_start:
        return (dt_end - dt_start).total_seconds()
    return None


def calculate_lora_airtime_seconds(
    payload_bytes: int,
    sf: int = 7,
    bw_hz: int = 125000,
    cr_denom: int = 5,
    preamble_symbols: int = 8,
    header_explicit: bool = True,
    low_dr_opt: Optional[bool] = None,
) -> float:
    """
    Computes exact physical LoRa Time-on-Air (Airtime) in seconds following the Semtech specification:
    T_air = T_preamble + T_payload
    T_sym = (2^SF) / BW
    """
    sf = max(7, min(12, sf or 7))
    bw_hz = bw_hz or 125000
    t_sym = (2 ** sf) / float(bw_hz)
    t_preamble = (preamble_symbols + 4.25) * t_sym

    if low_dr_opt is None:
        # Standard LoRaWAN: Low Data Rate Optimization is enabled if symbol duration > 16ms (SF11/12 @ 125kHz)
        low_dr_opt = (t_sym > 0.016)

    de = 1 if low_dr_opt else 0
    ih = 0 if header_explicit else 1
    cr = max(1, min(4, cr_denom - 4))  # 4/5 -> 1, 4/6 -> 2, 4/7 -> 3, 4/8 -> 4

    num = 8 * payload_bytes - 4 * sf + 28 + 16 - 20 * ih
    den = 4 * (sf - 2 * de)
    if den <= 0:
        den = 1

    payload_sym_nb = 8 + max(math.ceil(num / den) * (cr + 4), 0)
    t_payload = payload_sym_nb * t_sym
    return round(t_preamble + t_payload, 6)


def extract_correlation_id(correlation_ids: Optional[List[str]]) -> Optional[str]:
    """
    Extracts the most relevant correlation ID (prioritizing 'as:up:' or 'ns:down:' prefixes).
    """
    if not correlation_ids:
        return None

    # Prioritize application / network correlation IDs
    for cid in correlation_ids:
        if any(cid.startswith(pfx) for pfx in ("as:up:", "ns:down:", "gs:uplink:", "gs:downlink:")):
            return cid

    # Fallback to the first correlation ID in the list
    return correlation_ids[0] if correlation_ids else None


def unwrap_event(event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Unwraps {"result": {...}} if present from TTN SSE event lines."""
    if isinstance(event_dict, dict) and "result" in event_dict and isinstance(event_dict["result"], dict):
        return event_dict["result"]
    return event_dict


def process_uplink_event(event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts LoRa RF parameters, timestamps, airtime, and delays from an uplink event.
    Compatible with:
    - as.up.data.forward / as.up.data.receive
    - gs.up.receive
    - ns.up.data.receive
    - as.up.join.receive
    """
    event = unwrap_event(event_dict)
    event_time = event.get("time")
    data = event.get("data", {}) or {}

    # Extract uplink message payload regardless of nesting level
    uplink_msg = data.get("uplink_message") or data.get("message") or data

    # RX Metadata (gateway level)
    rx_metadata_list = uplink_msg.get("rx_metadata") or data.get("rx_metadata") or []
    rx_meta = rx_metadata_list[0] if rx_metadata_list else {}

    # Settings (RF parameters)
    settings = uplink_msg.get("settings") or data.get("settings") or {}
    data_rate = settings.get("data_rate") or {}
    lora_settings = data_rate.get("lora") or {}

    sf = lora_settings.get("spreading_factor") or 7
    bw_hz = lora_settings.get("bandwidth") or 125000
    coding_rate_str = settings.get("coding_rate") or "4/5"
    cr_denom = 5
    if "/" in str(coding_rate_str):
        try:
            cr_denom = int(str(coding_rate_str).split("/")[1])
        except Exception:
            cr_denom = 5

    # Timestamps
    server_received_at = data.get("received_at") or uplink_msg.get("received_at") or event_time
    gateway_time = rx_meta.get("time")
    concentrator_us = rx_meta.get("timestamp") or settings.get("timestamp")

    # Raw / decoded payload
    payload_raw = uplink_msg.get("frm_payload") or data.get("raw_payload") or data.get("payload_raw")
    decoded_json = uplink_msg.get("decoded_payload") or data.get("decoded_payload")

    # Determine payload byte length
    payload_len = 24  # Standard default
    if payload_raw and isinstance(payload_raw, str):
        try:
            import base64
            payload_len = len(base64.b64decode(payload_raw))
        except Exception:
            payload_len = max(len(payload_raw) // 2, 12)

    # 1. Airtime LoRa (from TTN or exact theoretical formula fallback)
    airtime_raw = uplink_msg.get("consumed_airtime") or data.get("consumed_airtime")
    airtime_s = parse_duration_seconds(airtime_raw)
    if airtime_s is None:
        airtime_s = calculate_lora_airtime_seconds(
            payload_bytes=payload_len,
            sf=sf,
            bw_hz=bw_hz,
            cr_denom=cr_denom
        )

    # 2. Network Transit + Server Processing Delay (Gateway -> TTN Server)
    # Since gateway_time is stamped at the END of physical LoRa transmission,
    # (server_received_at - gateway_time) is purely the IP network transit and cloud processing delay.
    network_delay_s = None
    if server_received_at and gateway_time:
        network_delay_s = calculate_time_diff_seconds(server_received_at, gateway_time)

    # 3. Total End-to-End Uplink Latency (Physical Airtime + Network Transit/Server Processing)
    total_uplink_delay_s = None
    if network_delay_s is not None and airtime_s is not None:
        total_uplink_delay_s = round(airtime_s + network_delay_s, 6)

    # Device ID extraction
    end_device_ids = data.get("end_device_ids") or uplink_msg.get("end_device_ids") or {}
    device_id = end_device_ids.get("device_id")
    if not device_id:
        for ident in event.get("identifiers", []):
            dev_ids = ident.get("device_ids", {})
            if dev_ids.get("device_id"):
                device_id = dev_ids.get("device_id")
                break
            elif dev_ids.get("dev_eui"):
                device_id = f"eui-{dev_ids.get('dev_eui').lower()}"
                break
            elif dev_ids.get("dev_addr"):
                device_id = f"addr-{dev_ids.get('dev_addr').lower()}"
                break

    # Gateway ID extraction
    gateway_ids = rx_meta.get("gateway_ids", {}) or {}
    gateway_id = gateway_ids.get("gateway_id")
    if not gateway_id:
        for ident in event.get("identifiers", []):
            gw_ids = ident.get("gateway_ids", {})
            if gw_ids.get("gateway_id"):
                gateway_id = gw_ids.get("gateway_id")
                break

    # Frame counter (f_cnt)
    f_cnt = uplink_msg.get("f_cnt")
    if f_cnt is None:
        mac_payload = data.get("payload", {}).get("mac_payload", {}) or uplink_msg.get("payload", {}).get("mac_payload", {})
        f_cnt = mac_payload.get("f_hdr", {}).get("f_cnt")

    # Correlation ID
    correlation_id = extract_correlation_id(event.get("correlation_ids"))

    # Confirmed flag check
    is_confirmed = False
    if uplink_msg.get("confirmed") or data.get("confirmed"):
        is_confirmed = True

    return {
        "timestamp_utc": event_time or server_received_at or datetime.now(timezone.utc).isoformat(),
        "device_id": device_id or "unknown_device",
        "gateway_id": gateway_id,
        "rssi_dbm": rx_meta.get("rssi"),
        "snr_db": rx_meta.get("snr"),
        "gateway_time": gateway_time,
        "concentrator_us": concentrator_us,
        "received_at": server_received_at,
        "airtime_s": airtime_s,
        "network_delay_s": network_delay_s,
        "total_uplink_delay_s": total_uplink_delay_s,
        "sf": sf,
        "bw_hz": bw_hz,
        "coding_rate": coding_rate_str,
        "frequency_hz": settings.get("frequency"),
        "f_cnt": f_cnt,
        "channel_idx": rx_meta.get("channel_index"),
        "is_confirmed": is_confirmed,
        "payload_raw": payload_raw,
        "decoded_json": decoded_json,
        "correlation_id": correlation_id,
    }


def process_downlink_event(event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts downlink ACK scheduling and transmission timestamps.
    Handles:
    - ns.down.data.schedule.attempt / ns.down.data.schedule.success / ns.down.data.schedule.fail
    - gs.down.send
    - gs.down.tx.success / gs.down.tx.fail
    - as.down.data.forward / as.down.data.receive
    """
    event = unwrap_event(event_dict)
    event_name = event.get("name", "")
    event_time = event.get("time") or datetime.now(timezone.utc).isoformat()
    data = event.get("data", {}) or {}

    # Identifiers
    end_device_ids = data.get("end_device_ids") or {}
    device_id = end_device_ids.get("device_id")
    if not device_id:
        for ident in event.get("identifiers", []):
            dev_ids = ident.get("device_ids", {})
            if dev_ids.get("device_id"):
                device_id = dev_ids.get("device_id")
                break

    correlation_id = extract_correlation_id(event.get("correlation_ids"))
    downlink_msg = data.get("downlink_message") or data.get("message") or data

    # Extract downlink RF parameters to calculate downlink airtime
    raw_payload = downlink_msg.get("raw_payload") or data.get("raw_payload")
    payload_len = 12  # Standard ACK frame length (12 bytes)
    if raw_payload and isinstance(raw_payload, str):
        try:
            import base64
            payload_len = len(base64.b64decode(raw_payload))
        except Exception:
            payload_len = 12

    request_info = data.get("request", {}) or {}
    rx1_dr = request_info.get("rx1_data_rate", {}).get("lora", {}) or {}
    dl_sf = rx1_dr.get("spreading_factor") or 7
    dl_bw = rx1_dr.get("bandwidth") or 500000
    dl_cr = rx1_dr.get("coding_rate") or "4/5"
    cr_denom = 5
    if "/" in str(dl_cr):
        try:
            cr_denom = int(str(dl_cr).split("/")[1])
        except Exception:
            cr_denom = 5

    airtime_downlink_s = calculate_lora_airtime_seconds(
        payload_bytes=payload_len,
        sf=dl_sf,
        bw_hz=dl_bw,
        cr_denom=cr_denom
    )

    return {
        "timestamp_utc": event_time,
        "device_id": device_id or "unknown_device",
        "event_name": event_name,
        "correlation_id": correlation_id,
        "f_port": downlink_msg.get("f_port"),
        "is_confirmed": bool(downlink_msg.get("confirmed")),
        "airtime_downlink_s": airtime_downlink_s,
        "raw_json": event_dict,
    }
