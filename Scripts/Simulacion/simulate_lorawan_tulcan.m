% Simulación de Cobertura LoRaWAN en el Campus Universitario de Tulcán
% Basado en las coordenadas proporcionadas (Latitud: 2°26'48"N, Longitud: 76°35'54"W)

%% 1. Definición de Parámetros de la Red LoRaWAN
% Frecuencia de operación para Colombia (AU915 / US915)
fq = 915e6; % 915 MHz

% Sensibilidad del receptor (Nodos finales LoRa)
% La sensibilidad típica puede rondar entre -120 y -137 dBm dependiendo del Spreading Factor (SF)
rxSensitivity = -100; % Unidades: dBm

% Potencia del Transmisor (Gateway)
% Un Gateway típico de exteriores puede tener hasta 27 dBm de potencia (500 mW)

txPower = 0.1259; % Unidades: Watts

%% 2. Definición del Gateway (Sitio Transmisor)
% Coordenadas convertidas desde GMS a Grados Decimales:
% Lat = 2 + (26/60) + (48/3600) = 2.446667
% Lon = -(76 + (35/60) + (54/3600)) = -76.598333
latGateway = 2.446734;
lonGateway = -76.598697;

tx = txsite("Name", "Gateway LoRaWAN (Tulcán)", ...
    "Latitude", latGateway, ...
    "Longitude", lonGateway, ...
    "Antenna", design(dipole, fq), ...
    "AntennaHeight", 1, ...               % Altura de la antena en metros (ej. 15 metros)
    "TransmitterFrequency", fq, ...
    "TransmitterPower", txPower);

%% 3. Definición de Nodos de Prueba (Sitios Receptores)
% Aquí se definen algunos puntos de prueba alrededor del campus.

rxNames = [
    "Punto Prueba 1 (Residencias)", 
    "Punto Prueba 2 (Contables)", 
    "Punto Prueba 3 (Parqueadero Motos Tulcan)", 
    "Punto Prueba 4 (CDU Sur)",
    "Punto Prueba 5 (CDU Norte)",
    "Punto Prueba 6 (Facultad Educacion (Esquina Norte))"
];

% Coordenadas
rxLocations = [
    2.44502   -76.59816; ... % Residencias
    2.44630   -76.59752; ... % Contables
    2.44574   -76.59936; ... % Parqueadero Motos Tulcan
    2.44748   -76.60029; ... % CDU Sur
    2.44817   -76.59802; ... % CDU Norte
    2.44558   -76.60132  ... % Facultad Educacion (Esquina Norte)
];

rxs = rxsite("Name", rxNames, ...
    "Latitude", rxLocations(:,1), ...
    "Longitude", rxLocations(:,2), ...
    "Antenna", design(dipole, fq), ...
    "ReceiverSensitivity", rxSensitivity);

%% 4. Visualización Inicial (Con Topografía y Edificios 3D)
% Se añaden los datos de elevación descargados (formato DTED: .dt2) y edificios locales
% IMPORTANTE: Solo correr addCustomTerrain si no se ha añadido previamente
% addCustomTerrain("Popayan_DTED", "n02.dt2");
viewer = siteviewer("Basemap", "openstreetmap", "Terrain", "Popayan_DTED", "Buildings", "tulcan_campus.osm");
show(tx)
show(rxs)

%% 5. Despliegue del Mapa de Cobertura
% Calcula el mapa de cobertura 
disp("Generando el mapa de cobertura con Ray Tracing (Paciencia, puede tardar)...");
% Definir niveles de intensidad para visualizar la atenuación como un mapa de calor (heatmap)
sigStrengths = -120:5:0; % Desde sensibilidad (-120 dBm) hasta señal fuerte (0 dBm) en pasos de 5 dBm
% Nota: El modelo "raytracing" utiliza los edificios 3D para calcular reflejos y bloqueos físicos
coverage(tx, "longley-rice", "SignalStrengths", sigStrengths, "MaxRange", 2000);

%% 6. Análisis de Enlaces de Comunicación (Communication Links)
% Trazamos las líneas para ver visualmente cuáles puntos están en cobertura (Verde) y cuáles no (Rojo)
disp("Calculando enlaces...");
sc = [0 0.8 0]; % Color verde para conexión exitosa
link(rxs, tx, "longley-rice", "SuccessColor", sc);

%% 7. Cálculo de Intensidad de Señal Recibida en Cada Nodo
% Usamos sigstrength para obtener la potencia recibida (dBm) en cada punto receptor
disp(" ");
disp("==========================================================");
disp("  INTENSIDAD DE SEÑAL RECIBIDA EN CADA NODO RECEPTOR");
disp("==========================================================");

ss = sigstrength(rxs, tx, "longley-rice");

% Calcular la distancia desde el Gateway a cada nodo (en metros)
distancias = distance(latGateway, lonGateway, rxLocations(:,1), rxLocations(:,2), wgs84Ellipsoid("m"));

% Imprimir tabla formateada en consola
fprintf("\n%-50s | %10s | %10s | %15s | %12s\n", ...
    "Nombre del Nodo", "Lat", "Lon", "Distancia (m)", "RSSI (dBm)");
fprintf("%s\n", repmat('-', 1, 105));

for i = 1:length(rxs)
    % Determinar el estado del enlace
    if ss(i) >= rxSensitivity
        estado = "✓ CONECTADO";
    else
        estado = "✗ FUERA DE RANGO";
    end
    
    fprintf("%-50s | %10.5f | %10.5f | %13.1f m | %10.2f  [%s]\n", ...
        rxNames(i), rxLocations(i,1), rxLocations(i,2), ...
        distancias(i), ss(i), estado);
end

fprintf("%s\n", repmat('-', 1, 105));
fprintf("Sensibilidad del receptor configurada: %d dBm\n", rxSensitivity);
fprintf("Potencia del transmisor: %.1f W (%.1f dBm)\n"%% 8. Análisis de Link Budget (Justificación de Sensibilidad Efectiva)
% Se ejecuta desde un archivo separado para mantener el script principal limpio
link_budget_analysis;

disp(" ");
disp("Simulación completada.");
��─────────────────────────────────┼──────────┤\n");
fprintf("  │ DEGRADACIÓN TOTAL                               │ %+5.1f dB │\n", degradacion_total);
fprintf("  └─────────────────────────────────────────────────┴──────────┘\n");

fprintf("\n--- Paso 3: Sensibilidad Efectiva (SF12) ---\n");
fprintf("  S_efectiva = S_teórica + Degradación_total\n");
fprintf("  S_efectiva = %.2f + %.1f\n", S_teorica, degradacion_total);
fprintf("  S_efectiva = %.2f dBm\n", S_efectiva);
fprintf("\n  ➤ Valor configurado en simulación: %d dBm\n", rxSensitivity);
fprintf("  ➤ Diferencia con el cálculo:       %.2f dB\n", abs(rxSensitivity - S_efectiva));

disp(" ");
disp("Simulación completada.");

