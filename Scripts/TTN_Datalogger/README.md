# Programa de Recolección de Datos LoRaWAN desde The Things Network (TTN)

Este programa automatiza la recolección de datos de campo y métricas de red desde **The Things Network (TTN)** para la etapa de verificación de la tesis.

El programa utiliza el **stream de eventos SSE (equivalente funcional a gRPC `Events.Stream`)** para capturar en tiempo real tanto el enlace **Uplink** de los sensores como el ciclo de vida del **Downlink ACK** (para paquetes confirmados), persistiendo inmediatamente cada registro en una base de datos local SQLite y exportando los resultados a **CSV** y **Excel** (.xlsx).

---

## 📌 Características Principales

1. **Captura de Métricas LoRa**:
   - **Calidad de Señal**: RSSI (dBm) y SNR (dB).
   - **Configuración RF**: Spreading Factor (SF), Ancho de Banda (BW), Coding Rate, Frecuencia, Contador de Tramas (`f_cnt`) y Canal.
   - **Airtime LoRa**: `consumed_airtime` exacto calculado por el Network Server.

2. **Cálculo de Delays y Latencias**:
   - **Delay de Red (Gateway → Application Server)**: $\Delta t = \text{received\_at} - \text{gateway\_time}$.
   - **Estimación de Procesamiento de Servidor**: $\Delta t_{\text{proc}} = \text{Delay de Red} - \text{Airtime}$.
   - **Round Trip Time (RTT)** para paquetes confirmados: Tiempo desde la llegada del Uplink al Gateway hasta la transmisión del paquete Downlink ACK en la ventana RX1/RX2.
   - **Latencia de Scheduling**: Tiempo que toma el Network Server en programar el ACK.

3. **Monitoreo de Gateway**:
   - Sondeo periódico de contadores de paquetes `rx_ok` (uplink) y `tx_in` (downlink), estado de conexión y último timestamp.

4. **Diseñado para Sesiones Largas (hasta 5 días)**:
   - **Persistencia Inmediata**: Almacenamiento en SQLite (`ttn_data.db`) sin riesgo de pérdida de datos por corte eléctrico o desconexión.
   - **Reconexión Automática**: Manejo de reconexiones con backoff exponencial.
   - **Logs Rotativos**: Historial de eventos con rotación automática (máximo 10 MB).

5. **Salida Lista para MATLAB y Análisis**:
   - Exportación directa a CSV y libro Excel con formato y tablas resumen.

---

## 🚀 Requisitos e Instalación

### 1. Requisitos Previos
- Python 3.9 o superior.
- Cuenta en [The Things Network Console](https://console.cloud.thethings.network/).
- Un Gateway y uno o más dispositivos registrados en TTN.

### 2. Instalación de Dependencias

Abre una terminal en este directorio (`scripts/ttn_data_collector`):

```bash
pip install -r requirements.txt
```

---

## ⚙️ Configuración

1. Copia el archivo de plantilla `.env.example` y nómbralo `.env`:

```bash
cp .env.example .env
```

2. Edita el archivo `.env` con tus credenciales de TTN:

```ini
# URL del cluster de TTN (nam1 para Colombia / América Latina)
TTN_SERVER_URL=https://nam1.cloud.thethings.network

# API Key de TTN con permisos de lectura de tráfico de aplicación y gateway
TTN_API_KEY=NNSXS.XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

# Identificador de la aplicación en TTN (Console -> Applications)
TTN_APP_ID=iot-lab-tulcan

# Identificador del Gateway en TTN (Console -> Gateways)
TTN_GATEWAY_ID=eui-58a0cbfffe80xxxx

# Modo de recolección: 'continuous' (para sesiones largas) o 'count' (número fijo)
COLLECTION_MODE=continuous
MAX_PACKETS=1000

# Intervalo de consulta de estadísticas del Gateway en segundos
GW_STATS_INTERVAL_S=60

# Intervalo de auto-exportación periódica a Excel/CSV (ej. 3600 = cada 1 hora)
AUTO_EXPORT_INTERVAL_S=3600
```

> ⚠️ **Nota de Seguridad**: El archivo `.env` contiene tu API Key privada y está configurado en `.gitignore` para evitar que se suba a repositorios públicos.

---

## 💻 Modos de Uso

### Modo 1: Recolección Continua (Recomendado para pruebas de campo)
Inicia una nueva sesión de recolección en tiempo real. Cada ejecución genera un **`session_id` único** que calcula el PDR y métricas de forma 100% aislada. Para finalizar, presiona `Ctrl+C` y el programa generará automáticamente los archivos CSV y Excel de la sesión:

```bash
python main.py
```

### Modo 2: Recolección por Límite de Paquetes
Recolecta un número fijo de paquetes en la sesión actual y finaliza automáticamente:

```bash
python main.py --mode count --max-packets 500
```

### Modo 3: Ver Estado y PDR de la Última Sesión
Muestra en consola las métricas y el PDR calculado exclusivamente para la última sesión ejecutada:

```bash
python main.py --status
```

### Modo 4: Listar Historial de Todas las Sesiones
Muestra una tabla con todas las sesiones realizadas, su fecha/hora, número de paquetes y PDR obtenido:

```bash
python main.py --sessions
```

### Modo 5: Exportar Datos de una Sesión a CSV y Excel
Exporta los datos de la última sesión (o de una específica usando `--session <id>`):

```bash
python main.py --export
python main.py --export --session sess_20260815_173000
```

### Modo 6: Limpiar Base de Datos
Borra todos los registros (o solo una sesión con `--session <id>`) para iniciar una nueva campaña limpia:

```bash
python main.py --clean
python main.py --clean --session sess_20260815_173000
```

---

## 📁 Estructura de Archivos Generados

Los datos se guardan en el subdirectorio `data/`:

| Archivo | Descripción |
|---|---|
| `data/ttn_data.db` | Base de datos SQLite con todas las tablas y vistas. |
| `data/uplink_data_YYYYMMDD_HHMMSS.csv` | Registros crudos de cada uplink recibido. |
| `data/downlink_data_YYYYMMDD_HHMMSS.csv` | Registros del ciclo de vida de los paquetes ACK downlink. |
| `data/rtt_analysis_YYYYMMDD_HHMMSS.csv` | Vista cruzada Uplink-Downlink con el cálculo de RTT y latencias. |
| `data/gateway_stats_YYYYMMDD_HHMMSS.csv` | Historial de contadores del Gateway. |
| `data/lorawan_data_YYYYMMDD_HHMMSS.xlsx` | Libro Excel completo con pestañas separadas y hoja resumen. |
| `data/collector.log` | Archivo de registro con rotación automática. |

---

## 📊 Importación Directa en MATLAB

Para cargar los datos en MATLAB y graficar RSSI, SNR, Delay y Airtime:

```matlab
% Cargar archivo CSV generado por el recolector
filename = 'scripts/ttn_data_collector/data/rtt_analysis_final_YYYYMMDD_HHMMSS.csv';
data = readtable(filename);

% Extraer vectores
rssi = data.rssi_dbm;
snr = data.snr_db;
airtime = data.airtime_s * 1000; % Convertir a ms
delay = data.network_delay_s * 1000; % Convertir a ms

% Graficar RSSI y SNR
figure('Name', 'Calidad de Enlace LoRa');
subplot(2,1,1);
plot(rssi, 'b-o', 'LineWidth', 1.5);
grid on;
title('RSSI Recibido en Gateway');
xlabel('Muestra');
ylabel('RSSI (dBm)');

subplot(2,1,2);
plot(snr, 'r-s', 'LineWidth', 1.5);
grid on;
title('SNR Recibido en Gateway');
xlabel('Muestra');
ylabel('SNR (dB)');

% Graficar Latencia y Airtime
figure('Name', 'Análisis Temporal y Latencia');
subplot(2,1,1);
plot(airtime, 'm-^', 'LineWidth', 1.5);
grid on;
title('Airtime LoRa (Tiempo de Transmisión)');
ylabel('Airtime (ms)');

subplot(2,1,2);
plot(delay, 'k-d', 'LineWidth', 1.5);
grid on;
title('Delay de Red (Gateway -> Application Server)');
xlabel('Muestra');
ylabel('Delay (ms)');
```
