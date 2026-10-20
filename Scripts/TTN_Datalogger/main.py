"""
TTN Data Collector - Main Application Entry Point.
Collects LoRaWAN uplinks, downlink ACKs, and gateway statistics from The Things Network (TTN)
with isolated session tracking and accurate per-run PDR calculations.
"""

import argparse
from datetime import datetime, timezone
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import sys
import time

# Ensure directory is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# UTF-8 stdout encoding for Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from config import Config
from csv_exporter import DataExporter
from db_storage import Database
from ttn_events_client import TTNEventsClient
from ttn_gateway_stats import GatewayStatsPoller

# Setup logger
logger = logging.getLogger("ttn_collector")


def setup_logging():
    """Configures console and rotating file logging."""
    Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    # Formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 1. Console Handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # 2. Rotating File Handler (Max 10MB per file, up to 5 backups for 5-day sessions)
    rfh = RotatingFileHandler(
        Config.LOG_PATH,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    rfh.setLevel(logging.DEBUG)
    rfh.setFormatter(formatter)
    logger.addHandler(rfh)


def print_banner(session_id: str):
    banner = """
================================================================================
  [TTN DATA COLLECTOR] - RECOLECCION DE DATOS DE TESIS LORAWAN
================================================================================
  Sesión Activa:    {session_id}
  Cluster TTN:      {server}
  Application ID:   {app_id}
  Gateway ID:       {gw_id}
  Modo:             {mode}
  Base de Datos:    {db}
  Directorio Data:  {data_dir}
================================================================================
    """.format(
        session_id=session_id,
        server=Config.TTN_SERVER_URL,
        app_id=Config.TTN_APP_ID or "(No configurado)",
        gw_id=Config.TTN_GATEWAY_ID or "(No configurado)",
        mode=Config.COLLECTION_MODE,
        db=Config.DB_PATH,
        data_dir=Config.DATA_DIR,
    )
    print(banner, flush=True)


def list_sessions(db: Database):
    """Prints a table of all recorded sessions."""
    sessions = db.fetch_all_sessions()
    print("\n" + "=" * 80)
    print("  HISTORIAL DE SESIONES DE MEDICION REGISTRADAS")
    print("=" * 80)
    if not sessions:
        print("  No hay sesiones registradas en la base de datos.")
    else:
        print(f"  {'ID de Sesion':<25} | {'Inicio':<20} | {'Uplinks':<8} | {'Downlinks':<9} | {'PDR (%)':<8}")
        print("  " + "-" * 78)
        for s in sessions:
            start_str = s.get("started_at", "")[:19].replace("T", " ")
            print(f"  {s['session_id']:<25} | {start_str:<20} | {s.get('uplinks_count', 0):<8} | {s.get('downlinks_count', 0):<9} | {s.get('pdr_percent', 100.0):>6.2f} %")
    print("=" * 80 + "\n", flush=True)


def show_status(db: Database, session_id: str = None):
    """Displays database record counts and statistical summary for a session (or latest)."""
    target_session = session_id or db.get_latest_session_id()
    counts = db.get_counts(session_id=target_session)
    summary = db.get_summary_statistics(session_id=target_session)

    sess_display = target_session if target_session else "Global (Todas las sesiones)"
    print("\n" + "=" * 68)
    print(f"  ESTADO DE METRICAS DE TESIS - SESION: {sess_display}")
    print("=" * 68)
    print(f"  * Total Paquetes Uplink:    {counts['uplinks']}")
    print(f"  * Total Eventos Downlink:   {counts['downlinks']}")
    print(f"  * Snapshots de Gateway:     {counts['gateway_stats']}")
    print("-" * 68)
    if counts["uplinks"] > 0:
        print("  [METRICAS DE ENTREGA DE PAQUETES - PDR DE ESTA SESION]")
        print(f"  * PDR de Sesión (Packet Delivery Rate): {summary.get('global_pdr_percent', 0.0):.2f} %")
        print(f"  * PLR de Sesión (Packet Loss Rate):     {summary.get('global_plr_percent', 0.0):.2f} %")
        print(f"  * Paquetes Esperados en la Sesión:     {summary.get('total_expected_packets', 0)}")
        print(f"  * Paquetes Recibidos Exitosos:          {summary.get('total_received_packets', 0)}")
        print(f"  * Paquetes Perdidos Estimados:          {summary.get('total_lost_packets', 0)}")

        pdr_devs = summary.get("devices_pdr", [])
        if pdr_devs:
            print("\n  [DESGLOSE DE PDR POR NODO SENSOR EN ESTA SESION]")
            print(f"  {'Dispositivo':<16} | {'FCnt (Segmentos)':<22} | {'Reinicios':<9} | {'Recibidos':<9} | {'Esperados':<9} | {'PDR (%)':<8}")
            print("  " + "-" * 86)
            for d in pdr_devs:
                fcnt_str = d.get('fcnt_ranges', f"{d.get('min_fcnt')}-{d.get('max_fcnt')}")
                if len(fcnt_str) > 22:
                    fcnt_str = fcnt_str[:19] + "..."
                rst_cnt = str(d.get('resets_detected', 0))
                print(f"  {d['device_id']:<16} | {fcnt_str:<22} | {rst_cnt:<9} | {d['received_count']:<9} | {d['expected_count']:<9} | {d['pdr_percent']:>6.2f} %")

        print("\n  [CALIDAD RF Y LATENCIA]")
        print(f"  * RSSI Promedio:            {summary.get('avg_rssi', 0):.2f} dBm  (Min: {summary.get('min_rssi')}, Max: {summary.get('max_rssi')})")
        print(f"  * SNR Promedio:             {summary.get('avg_snr', 0):.2f} dB   (Min: {summary.get('min_snr')}, Max: {summary.get('max_snr')})")
        print(f"  * Airtime LoRa Promedio:    {summary.get('avg_airtime', 0):.4f} s  (T_aire en canal físico)")
        print(f"  * Delay Red y Servidor:     {summary.get('avg_delay', 0):.4f} s  (T_red: Gateway -> TTN Server)")
        if summary.get('avg_total_uplink_delay') is not None:
            print(f"  * Latencia Total Subida E2E:{summary.get('avg_total_uplink_delay', 0):.4f} s  (T_E2E = T_aire + T_red)")
    if summary.get("total_rtt_samples", 0) > 0:
        print(f"  * RTT Red/Infraestructura:  {summary.get('avg_rtt', 0):.4f} s  (Muestras: {summary.get('total_rtt_samples')})")
        if summary.get('avg_rtt_phy_complete') is not None:
            print(f"  * RTT Fisico Completo:      {summary.get('avg_rtt_phy_complete', 0):.4f} s  (rtt_phy_complete = Airtime_Up + RTT_Red + Airtime_Down)")
        if summary.get('avg_effective_dl_window_delay_au915') is not None:
            print(f"  * Espera en Ventana RX1:    {summary.get('avg_effective_dl_window_delay_au915', 0):.4f} s  (effective_dl_window = 5000ms - RTT_Red)")
        if summary.get('avg_cloud_turnaround') is not None:
            print(f"    - Server Cloud Turnaround: {summary.get('avg_cloud_turnaround', 0):.4f} s  (Cómputo interno TTN: received_at -> gs_send)")
        if summary.get('avg_tx_delay') is not None:
            print(f"    - Retardo Bajada GS->GW:   {summary.get('avg_tx_delay', 0):.4f} s  (Despacho GS -> Gateway y confirmación)")
    print("=" * 68 + "\n", flush=True)


def main():
    parser = argparse.ArgumentParser(description="TTN LoRaWAN Data Collector for Thesis Field Experiments")
    parser.add_argument("--mode", choices=["continuous", "count"], help="Override collection mode")
    parser.add_argument("--max-packets", type=int, help="Max packets to collect in count mode")
    parser.add_argument("--export", action="store_true", help="Export session data to CSV and Excel without streaming")
    parser.add_argument("--status", action="store_true", help="Display metrics summary without starting collection")
    parser.add_argument("--session", type=str, help="Specify session ID for status or export")
    parser.add_argument("--sessions", action="store_true", help="List all recorded sessions in database")
    parser.add_argument("--all-sessions", action="store_true", help="Include all sessions combined in status/export")
    parser.add_argument("--clean", action="store_true", help="Clear the SQLite database (or specified --session) before starting")
    args = parser.parse_args()

    setup_logging()

    # Override config from CLI arguments if provided
    if args.mode:
        Config.COLLECTION_MODE = args.mode
    if args.max_packets:
        Config.MAX_PACKETS = args.max_packets

    db = Database(Config.DB_PATH)
    exporter = DataExporter(db, Config.DATA_DIR)

    if args.clean:
        if args.session:
            db.clear_database(session_id=args.session)
            logger.info(f"Sesion '{args.session}' eliminada con exito.")
        else:
            db.clear_database()
            logger.info("Base de datos limpiada por completo.")

    if args.sessions:
        list_sessions(db)
        sys.exit(0)

    if args.status:
        target_sess = None if args.all_sessions else args.session
        show_status(db, session_id=target_sess)
        sys.exit(0)

    if args.export:
        target_sess = None if args.all_sessions else (args.session or db.get_latest_session_id())
        logger.info(f"Exportando datos a CSV y Excel (Sesion: {target_sess or 'Todas'})...")
        res = exporter.export_all(session_id=target_sess, prefix="manual_export")
        print("[OK] Exportacion completada:")
        for k, path in res.items():
            print(f"  - {k}: {path}")
        sys.exit(0)

    # Validate configuration before starting stream
    try:
        Config.validate(require_app=True, require_gateway=False)
    except ValueError as e:
        print(e)
        sys.exit(1)

    # Generate unique Session ID for this run
    current_session_id = f"sess_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    db.start_session(
        session_id=current_session_id,
        app_id=Config.TTN_APP_ID,
        gateway_id=Config.TTN_GATEWAY_ID,
        mode=Config.COLLECTION_MODE
    )

    print_banner(session_id=current_session_id)

    # Shared state
    packet_count = 0
    start_time = time.time()
    last_export_time = time.time()
    shutting_down = False

    def on_event(event_type: str, data: dict):
        nonlocal packet_count
        if event_type == "uplink":
            packet_count += 1
            if Config.COLLECTION_MODE == "count" and packet_count >= Config.MAX_PACKETS:
                logger.info(f"Objetivo de {Config.MAX_PACKETS} paquetes alcanzado. Finalizando recoleccion...")
                stop_and_exit()

    # Initialize workers with current session_id
    events_client = TTNEventsClient(db, session_id=current_session_id, on_event_callback=on_event)
    stats_poller = GatewayStatsPoller(db, session_id=current_session_id)

    def stop_and_exit(signum=None, frame=None):
        nonlocal shutting_down
        if shutting_down:
            return
        shutting_down = True

        print("\n\nDeteniendo recoleccion de datos...", flush=True)
        try:
            events_client.stop()
        except Exception as e:
            logger.debug(f"Error deteniendo events_client: {e}")

        try:
            stats_poller.stop()
        except Exception as e:
            logger.debug(f"Error deteniendo stats_poller: {e}")

        # Finalize session in DB
        db.end_session(current_session_id)

        print("\nCalculando metricas finales de la sesion...", flush=True)
        try:
            show_status(db, session_id=current_session_id)
        except Exception as e:
            logger.error(f"Error mostrando resumen: {e}")

        print("Generando archivos finales en CSV y Excel...", flush=True)
        try:
            res = exporter.export_all(session_id=current_session_id, prefix="final")
            print("\n[OK] Archivos generados con exito:", flush=True)
            for k, p in res.items():
                print(f"   * {k}: {p}", flush=True)
        except Exception as e:
            logger.error(f"Error generando exports: {e}")

        elapsed_m = (time.time() - start_time) / 60.0
        print(f"\nTiempo total de sesion: {elapsed_m:.1f} minutos.\n", flush=True)
        os._exit(0)

    # Register OS signals for graceful shutdown
    signal.signal(signal.SIGINT, stop_and_exit)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop_and_exit)

    # Start workers
    events_client.start()
    stats_poller.start()

    logger.info("Presiona Ctrl+C en cualquier momento para detener la recoleccion y exportar los datos a CSV/Excel.\n")

    # Main monitoring loop
    try:
        while not shutting_down:
            time.sleep(0.5)

            # Auto-export if configured
            if Config.AUTO_EXPORT_INTERVAL_S > 0:
                if time.time() - last_export_time >= Config.AUTO_EXPORT_INTERVAL_S:
                    last_export_time = time.time()
                    try:
                        exporter.export_all(session_id=current_session_id, prefix="periodic_auto")
                    except Exception as e:
                        logger.warning(f"Error en auto-exportacion periodica: {e}")

    except KeyboardInterrupt:
        stop_and_exit()


if __name__ == "__main__":
    main()
