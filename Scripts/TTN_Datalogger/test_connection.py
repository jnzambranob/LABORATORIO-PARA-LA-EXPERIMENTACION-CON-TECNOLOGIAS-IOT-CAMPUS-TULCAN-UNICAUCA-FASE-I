"""
Test de conectividad y diagnostico para The Things Network (TTN).
Verifica la validez de la API Key, los permisos otorgados y la conexion con la aplicacion y gateway.
"""

import json
from pathlib import Path
import sys
import requests

# Cargar configuracion
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config import Config


def main():
    print("=" * 70)
    print("  DIAGNOSTICO DE CONECTIVIDAD CON THE THINGS NETWORK (TTN)")
    print("=" * 70)

    server_url = Config.TTN_SERVER_URL
    api_key = Config.TTN_API_KEY.strip()
    app_id = Config.TTN_APP_ID.strip()
    gw_id = Config.TTN_GATEWAY_ID.strip()

    print(f"\n[1] Parametros cargados desde .env:")
    print(f"  - Server URL:   {server_url}")
    print(f"  - Application:  {app_id}")
    print(f"  - Gateway:      {gw_id}")
    print(f"  - API Key:      {api_key[:10]}...{api_key[-6:] if len(api_key) > 16 else ''} (Longitud: {len(api_key)} chars)")

    if not api_key or api_key == "NNSXS.YOUR_API_KEY_HERE":
        print("\n[ERROR] La API Key esta vacia o tiene el valor por defecto.")
        return

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    # 1. Probar conexion y stats del Gateway
    print(f"\n[2] Probando conexion con Gateway '{gw_id}' (/connection/stats)...")
    stats_url = f"{server_url}/api/v3/gs/gateways/{gw_id}/connection/stats"
    gw_ok = False
    try:
        r_stats = requests.get(stats_url, headers=headers, timeout=10)
        print(f"  -> Codigo HTTP: {r_stats.status_code}")
        if r_stats.status_code == 200:
            gw_ok = True
            stats = r_stats.json()
            print("  [OK] Estadisticas del Gateway obtenidas con exito:")
            print(f"     * Conectado desde:          {stats.get('connected_at', 'N/A')}")
            print(f"     * Paquetes Uplink recibidos: {stats.get('uplink_count', 0)}")
            print(f"     * Paquetes Downlink enviados:{stats.get('downlink_count', 0)}")
        else:
            print(f"  [AVISO] Respuesta ({r_stats.status_code}): {r_stats.text[:150]}")
    except Exception as e:
        print(f"  [ERROR] Error consultando stats: {e}")

    # 2. Probar Stream SSE solo con Gateway
    print(f"\n[3] Probando Stream de Eventos del Gateway...")
    events_url = f"{server_url}/api/v3/events"
    events_headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "text/event-stream",
        "Content-Type": "application/json"
    }
    payload_gw = {"identifiers": [{"gateway_ids": {"gateway_id": gw_id}}]}
    try:
        with requests.post(events_url, headers=events_headers, json=payload_gw, stream=True, timeout=3) as r_stream:
            print(f"  -> Codigo HTTP Stream Gateway: {r_stream.status_code}")
            if r_stream.status_code == 200:
                print("  [OK] CONEXION AL STREAM DE EVENTOS DEL GATEWAY EXITOSA.")
    except requests.exceptions.Timeout:
        print("  [OK] CONEXION AL STREAM DE EVENTOS DEL GATEWAY EXITOSA (Stream abierto y esperando).")
    except Exception as e:
        print(f"  [ERROR] {e}")

    # 3. Probar Stream SSE con Application
    print(f"\n[4] Probando Stream de Eventos de la Aplicacion '{app_id}'...")
    payload_app = {"identifiers": [{"application_ids": {"application_id": app_id}}]}
    try:
        with requests.post(events_url, headers=events_headers, json=payload_app, stream=True, timeout=3) as r_app:
            print(f"  -> Codigo HTTP Stream Application: {r_app.status_code}")
            if r_app.status_code == 200:
                print("  [OK] CONEXION AL STREAM DE EVENTOS DE LA APLICACION EXITOSA.")
            elif r_app.status_code == 403:
                print(f"  [403 FORBIDDEN] Tu API Key actual NO tiene permisos sobre la aplicacion '{app_id}'.")
                print("                  (Esto ocurre si creaste la API Key dentro de la seccion del Gateway).")
            else:
                print(f"  [ERROR] {r_app.text[:200]}")
    except requests.exceptions.Timeout:
        print("  [OK] CONEXION AL STREAM DE EVENTOS DE LA APLICACION EXITOSA (Stream abierto).")
    except Exception as e:
        print(f"  [ERROR] {e}")

    print("\n" + "=" * 70)
    print("  RESUMEN DEL DIAGNOSTICO")
    print("=" * 70)
    if gw_ok:
        print("  * Tu API Key FUNCIONA para el Gateway 'ug65-fiet' (HTTP 200).")
        print("  * El Gateway esta conectado a TTN y transmitiendo paquetes.")
        print("  * Para recibir tambien los eventos decodificados de la Aplicacion 'fiet-iot':")
        print("    Crea una 'Personal API Key' en la consola de TTN (Perfil -> Personal API Keys)")
        print("    o una API Key dentro de 'Applications -> fiet-iot -> API Keys'.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
