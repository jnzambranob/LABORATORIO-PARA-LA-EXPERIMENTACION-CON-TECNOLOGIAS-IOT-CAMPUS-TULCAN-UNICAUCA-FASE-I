%% ========================================================================
%  SCRIPT: analyze_ttn_session.m
%  DESCRIPCIÓN: Análisis estadístico y caracterización experimental de la
%               sesión de transmisión LoRaWAN continua (84 horas, 13.769
%               paquetes confirmados). Genera figuras vectoriales SVG con
%               calidad de publicación académica.
%
%  AUTOR: Nicolás Zambrano & Sandy Suarez
%  FECHA: 2026
%  ========================================================================
clc; clear; close all;

fprintf('================================================================\n');
fprintf('  ANÁLISIS ESTADÍSTICO DE SESIÓN LORAWAN (84 HORAS)\n');
fprintf('  Nodo: node-1 | Gateway: ug65-fiet | Plan: AU915\n');
fprintf('================================================================\n\n');

%% ========================================================================
%  0. PARÁMETROS DE ENTORNO Y PALETA DE COLORES
%  ========================================================================
script_dir = fileparts(mfilename('fullpath'));
cd(fileparts(script_dir));  % Directorio raíz del proyecto
fprintf('Directorio de trabajo: %s\n\n', pwd);

% Archivos de entrada
SESSION_TAG = 'sess_20260816_070733';
csv_uplink = fullfile('scripts','ttn_data_collector','data', ...
    ['uplink_data_final_' SESSION_TAG '.csv']);
csv_rtt    = fullfile('scripts','ttn_data_collector','data', ...
    ['rtt_analysis_final_' SESSION_TAG '.csv']);

% Directorio de exportación gráfica
fig_dir = 'Figures';
if ~exist(fig_dir, 'dir'), mkdir(fig_dir); end
FIG_PREFIX = 'ttn_session';

% Control de exportación (false: exporta las 14 figuras; true: solo figura 1)
EXPORTAR_SOLO_UNA_IMAGEN = false;

% Paleta cromática institucional y técnica
c_azul_primario   = [0.20, 0.40, 0.70];   % Azul principal
c_verde_exito     = [0.18, 0.54, 0.34];   % Verde confirmación / entregado
c_naranja_sec     = [0.85, 0.37, 0.15];   % Naranja advertencia / secundario
c_purpura_acento  = [0.60, 0.30, 0.60];   % Púrpura acento / retardo de red
c_rojo_alerta     = [0.90, 0.30, 0.30];   % Rojo pérdida / alerta
c_ambar_calido    = [0.95, 0.65, 0.20];   % Ámbar
c_verde_claro     = [0.40, 0.75, 0.40];   % Verde claro
c_azul_suave      = [0.20, 0.60, 0.80];   % Azul suave
c_gris_neutro     = [0.50, 0.50, 0.50];   % Gris neutro

% Asignación cromática por Spreading Factor (SF7 - SF12)
colores_sf = [
    0.20, 0.60, 0.80;   % SF7  - Azul suave
    0.18, 0.54, 0.34;   % SF8  - Verde bosque
    0.40, 0.75, 0.40;   % SF9  - Verde claro
    0.95, 0.65, 0.20;   % SF10 - Ámbar
    0.85, 0.37, 0.15;   % SF11 - Naranja
    0.90, 0.30, 0.30;   % SF12 - Rojo
];
sf_labels = {'SF7','SF8','SF9','SF10','SF11','SF12'};
sf_values = [7, 8, 9, 10, 11, 12];
n_sf = length(sf_values);

% Umbrales teóricos de demodulación SNR para modulación LoRa (dB)
snr_demod_thresholds = [-7.5, -10.0, -12.5, -15.0, -17.5, -20.0];

%% ========================================================================
%  1. CARGA Y PREPROCESAMIENTO DE DATOS
%  ========================================================================
fprintf('=== PASO 1: CARGA Y PREPROCESAMIENTO DE DATOS ===\n\n');

fprintf('Cargando datos de Uplink: %s ...\n', csv_uplink);
opts_ul = detectImportOptions(csv_uplink, 'TextType', 'string');
json_col = find(opts_ul.VariableNames == "decoded_json");
if ~isempty(json_col)
    opts_ul.VariableTypes{json_col} = 'string';
end
T_ul = readtable(csv_uplink, opts_ul);
fprintf('  ✓ Uplinks cargados: %d registros\n', height(T_ul));

fprintf('Cargando datos de RTT: %s ...\n', csv_rtt);
opts_rtt = detectImportOptions(csv_rtt, 'TextType', 'string');
T_rtt = readtable(csv_rtt, opts_rtt);
fprintf('  ✓ Registros RTT cargados: %d registros\n\n', height(T_rtt));

% Conversión de marcas temporales UTC a tipo datetime
T_ul.timestamp_dt = datetime(T_ul.timestamp_utc, 'InputFormat', ...
    "uuuu-MM-dd'T'HH:mm:ss.SSSSSSSSS'Z'", 'TimeZone', 'UTC');
T_rtt.timestamp_dt = datetime(T_rtt.timestamp_utc, 'InputFormat', ...
    "uuuu-MM-dd'T'HH:mm:ss.SSSSSSSSS'Z'", 'TimeZone', 'UTC');

% Ordenamiento cronológico por contador de tramas (f_cnt)
T_ul  = sortrows(T_ul, 'f_cnt');
T_rtt = sortrows(T_rtt, 'f_cnt');

% Decodificación de variables ambientales en la carga útil JSON
fprintf('Decodificando variables ambientales del payload...\n');
n_ul = height(T_ul);
temperature = NaN(n_ul, 1);
humidity    = NaN(n_ul, 1);
pressure    = NaN(n_ul, 1);

for i = 1:n_ul
    js = T_ul.decoded_json(i);
    if ~ismissing(js) && strlength(js) > 2
        try
            s = jsondecode(char(js));
            if isfield(s, 'temperature'), temperature(i) = s.temperature; end
            if isfield(s, 'humidity'),    humidity(i) = s.humidity; end
            if isfield(s, 'pressure'),    pressure(i) = s.pressure; end
        catch
        end
    end
end
T_ul.temperature = temperature;
T_ul.humidity    = humidity;
T_ul.pressure    = pressure;

session_start = min(T_ul.timestamp_dt);
session_end   = max(T_ul.timestamp_dt);
session_hours = hours(session_end - session_start);
fprintf('  ✓ Telemetría procesada: %d muestras válidas\n', sum(~isnan(temperature)));
fprintf('  ✓ Ventana temporal: %s a %s (%.1f horas / %.2f días)\n\n', ...
    datestr(session_start), datestr(session_end), session_hours, session_hours/24);

%% ========================================================================
%  2. ANÁLISIS DIFERENCIAL DE PDR/PLR POR SPREADING FACTOR (UPLINK + DOWNLINK)
%  ========================================================================
fprintf('=== PASO 2: ANÁLISIS DIFERENCIAL DE PDR/PLR POR SF ===\n\n');

% Tasa de entrega en subida (Uplink PDR) evaluando discontinuidades en f_cnt
ul_recv    = zeros(n_sf, 1);
ul_lost    = zeros(n_sf, 1);

for i = 1:height(T_ul)
    sf_i = T_ul.sf(i);
    k = find(sf_values == sf_i);
    if ~isempty(k)
        ul_recv(k) = ul_recv(k) + 1;
    end
    if i > 1
        gap = T_ul.f_cnt(i) - T_ul.f_cnt(i-1) - 1;
        if gap > 0
            sf_prev = T_ul.sf(i-1);
            k_prev = find(sf_values == sf_prev);
            if ~isempty(k_prev)
                ul_lost(k_prev) = ul_lost(k_prev) + gap;
            end
        end
    end
end
ul_expect  = ul_recv + ul_lost;
ul_pdr     = ul_recv ./ max(ul_expect, 1) * 100;
ul_plr     = ul_lost ./ max(ul_expect, 1) * 100;

% Tasa de entrega en bajada (Downlink PDR) basada en recepción de confirmación ACK
dl_pdr     = zeros(n_sf, 1);
dl_plr     = zeros(n_sf, 1);
dl_acked   = zeros(n_sf, 1);
dl_noack   = zeros(n_sf, 1);
dl_total   = zeros(n_sf, 1);

for k = 1:n_sf
    sf_k = sf_values(k);
    idx = T_rtt.sf == sf_k;
    rtt_k = T_rtt.rtt_s(idx);
    
    n_total = sum(idx);
    n_acked = sum(~isnan(rtt_k));
    n_noack = n_total - n_acked;
    
    dl_total(k) = n_total;
    dl_acked(k) = n_acked;
    dl_noack(k) = n_noack;
    dl_pdr(k)   = n_acked / max(n_total, 1) * 100;
    dl_plr(k)   = n_noack / max(n_total, 1) * 100;
end

total_ul_recv   = sum(ul_recv);
total_ul_lost   = sum(ul_lost);
total_ul_expect = sum(ul_expect);
total_ul_pdr    = total_ul_recv / max(total_ul_expect, 1) * 100;

total_dl_total  = sum(dl_total);
total_dl_acked  = sum(dl_acked);
total_dl_noack  = sum(dl_noack);
total_dl_pdr    = total_dl_acked / max(total_dl_total, 1) * 100;

fprintf('  %-6s | %10s %10s %10s | %10s %10s %10s\n', ...
    'SF', 'UL Recv', 'UL Perd', 'UL PDR', 'DL Conf', 'DL SinACK', 'DL PDR');
fprintf('  %s\n', repmat('-', 1, 75));
for k = 1:n_sf
    fprintf('  %-6s | %10d %10d %9.2f%% | %10d %10d %9.2f%%\n', ...
        sf_labels{k}, ul_recv(k), ul_lost(k), ul_pdr(k), ...
        dl_total(k), dl_noack(k), dl_pdr(k));
end
fprintf('  %s\n', repmat('-', 1, 75));
fprintf('  %-6s | %10d %10d %9.2f%% | %10d %10d %9.2f%%\n\n', ...
    'TOTAL', total_ul_recv, total_ul_lost, total_ul_pdr, ...
    total_dl_total, total_dl_noack, total_dl_pdr);

% -------------------------------------------------------------------------
% GRÁFICA 1: PDR Uplink y Downlink por Spreading Factor
% -------------------------------------------------------------------------
fig1 = figure('Name', 'LoRaWAN - PDR Uplink y Downlink por SF', ...
              'NumberTitle', 'off', 'Position', [100 100 820 480]);
set(fig1, 'Color', 'w');

offset_bar = 0.18; % Desplazamiento lateral entre barras emparejadas
ancho_bar  = 0.28; % Ancho individual de cada barra

b1_ul = bar((1:n_sf) - offset_bar, ul_pdr, ancho_bar, 'FaceColor', c_azul_primario, 'EdgeColor', 'w');
hold on;
b1_dl = bar((1:n_sf) + offset_bar, dl_pdr, ancho_bar, 'FaceColor', c_verde_exito, 'EdgeColor', 'w');
hold off;

ax1 = gca;
set(ax1, 'Color', 'w', 'FontSize', 11);
ax1.XColor = [0.15 0.15 0.15];
ax1.YColor = [0.15 0.15 0.15];
ax1.GridColor = [0.8 0.8 0.8];
ax1.GridAlpha = 0.6;
set(ax1, 'XTick', 1:n_sf, 'XTickLabel', sf_labels);
xlim([0.4, n_sf + 0.6]);

xlabel('Spreading Factor (SF)', 'FontSize', 12, 'FontWeight', 'bold', 'Color', 'k');
ylabel('Tasa de Entrega de Paquetes - PDR (%)', 'FontSize', 12, 'FontWeight', 'bold', 'Color', 'k');
t1 = title('PDR en Enlace Ascendente (Uplink) y Descendente (Downlink) por SF', 'FontSize', 14, 'FontWeight', 'bold');
set(t1, 'Color', 'k');

lg1 = legend([b1_ul, b1_dl], {'PDR Uplink (Gateway RX)', 'PDR Downlink (ACK Confirmado)'}, ...
    'Location', 'southwest', 'FontSize', 10);
set(lg1, 'Color', 'w', 'TextColor', 'k', 'EdgeColor', [0.8 0.8 0.8]);

ylim([0, 118]);
grid on;

for i = 1:n_sf
    text(i - offset_bar, ul_pdr(i) + 2.5, sprintf('%.1f%%', ul_pdr(i)), ...
        'HorizontalAlignment', 'center', 'FontSize', 8.5, 'FontWeight', 'bold', 'Color', c_azul_primario);
    text(i + offset_bar, dl_pdr(i) + 2.5, sprintf('%.1f%%', dl_pdr(i)), ...
        'HorizontalAlignment', 'center', 'FontSize', 8.5, 'FontWeight', 'bold', 'Color', c_verde_exito);
end
export_figure(fig1, fig_dir, [FIG_PREFIX '_pdr_por_sf']);

if ~EXPORTAR_SOLO_UNA_IMAGEN
    % -------------------------------------------------------------------------
    % GRÁFICA 2: Paquetes Entregados vs. Perdidos en Uplink y Downlink
    % -------------------------------------------------------------------------
    fig2 = figure('Name', 'LoRaWAN - Paquetes Entregados vs Perdidos', ...
                  'NumberTitle', 'off', 'Position', [100 550 900 480]);
    set(fig2, 'Color', 'w');

    subplot(1,2,1);
    b2a = bar([ul_recv, ul_lost], 'stacked');
    b2a(1).FaceColor = c_verde_exito;   % Entregados
    b2a(2).FaceColor = c_rojo_alerta;   % Perdidos
    ax2a = gca;
    set(ax2a, 'Color', 'w', 'FontSize', 11);
    ax2a.XColor = [0.15 0.15 0.15]; ax2a.YColor = [0.15 0.15 0.15];
    ax2a.GridColor = [0.8 0.8 0.8]; ax2a.GridAlpha = 0.5;
    set(ax2a, 'XTickLabel', sf_labels);
    xlabel('Spreading Factor', 'FontSize', 12, 'FontWeight', 'bold', 'Color', 'k');
    ylabel('Número de Paquetes Uplink', 'FontSize', 12, 'FontWeight', 'bold', 'Color', 'k');
    t2a = title('Uplink: Entregados vs. Perdidos', 'FontSize', 13, 'FontWeight', 'bold');
    set(t2a, 'Color', 'k');
    lg2a = legend({'Entregados', 'Perdidos'}, 'Location', 'northeast', 'FontSize', 10);
    set(lg2a, 'Color', 'w', 'TextColor', 'k', 'EdgeColor', [0.8 0.8 0.8]);
    grid on;
    ylim([0, max(ul_expect)*1.18]);
    for i = 1:n_sf
        text(i, ul_expect(i) + max(ul_expect)*0.03, sprintf('%d', ul_recv(i)), ...
            'HorizontalAlignment', 'center', 'FontSize', 9, 'FontWeight', 'bold', 'Color', 'k');
    end

    subplot(1,2,2);
    b2b = bar([dl_acked, dl_noack], 'stacked');
    b2b(1).FaceColor = c_azul_primario; % Confirmados
    b2b(2).FaceColor = c_naranja_sec;   % Sin ACK
    ax2b = gca;
    set(ax2b, 'Color', 'w', 'FontSize', 11);
    ax2b.XColor = [0.15 0.15 0.15]; ax2b.YColor = [0.15 0.15 0.15];
    ax2b.GridColor = [0.8 0.8 0.8]; ax2b.GridAlpha = 0.5;
    set(ax2b, 'XTickLabel', sf_labels);
    xlabel('Spreading Factor', 'FontSize', 12, 'FontWeight', 'bold', 'Color', 'k');
    ylabel('Número de Paquetes Downlink', 'FontSize', 12, 'FontWeight', 'bold', 'Color', 'k');
    t2b = title('Downlink: ACKs Confirmados vs. Faltantes', 'FontSize', 13, 'FontWeight', 'bold');
    set(t2b, 'Color', 'k');
    lg2b = legend({'ACK Confirmado', 'Sin ACK'}, 'Location', 'northeast', 'FontSize', 10);
    set(lg2b, 'Color', 'w', 'TextColor', 'k', 'EdgeColor', [0.8 0.8 0.8]);
    grid on;
    ylim([0, max(dl_total)*1.18]);
    for i = 1:n_sf
        if dl_total(i) > 0
            text(i, dl_total(i) + max(dl_total)*0.03, sprintf('%d', dl_acked(i)), ...
                'HorizontalAlignment', 'center', 'FontSize', 9, 'FontWeight', 'bold', 'Color', 'k');
        end
    end
    export_figure(fig2, fig_dir, [FIG_PREFIX '_paquetes_por_sf']);

    %% ========================================================================
    %  3. CALIDAD DE SEÑAL RF (RSSI Y SNR) POR SPREADING FACTOR
    %  ========================================================================
    fprintf('=== PASO 3: CALIDAD DE SEÑAL RF POR SF ===\n\n');

    % -------------------------------------------------------------------------
    % GRÁFICA 3: Diagrama de Cajas (Boxplot) de RSSI por SF
    % -------------------------------------------------------------------------
    fig3 = figure('Name', 'LoRaWAN - Boxplot RSSI por SF', ...
                  'NumberTitle', 'off', 'Position', [150 100 750 450]);
    set(fig3, 'Color', 'w');
    boxplot(T_ul.rssi_dbm, T_ul.sf, 'Labels', sf_labels, 'Colors', [0.2 0.2 0.2], ...
        'Symbol', '.r', 'OutlierSize', 3);
    hold on;
    yline(-137, '--r', 'Sensibilidad Teórica SF12 (-137 dBm)', ...
        'LineWidth', 1.2, 'LabelHorizontalAlignment', 'left', 'FontSize', 10);
    hold off;
    ax3 = gca;
    set(ax3, 'Color', 'w', 'FontSize', 11);
    ax3.XColor = [0.15 0.15 0.15]; ax3.YColor = [0.15 0.15 0.15];
    ax3.GridColor = [0.8 0.8 0.8]; ax3.GridAlpha = 0.5;
    xlabel('Spreading Factor', 'FontSize', 12, 'FontWeight', 'bold', 'Color', 'k');
    ylabel('Potencia de Señal Recibida - RSSI (dBm)', 'FontSize', 12, 'FontWeight', 'bold', 'Color', 'k');
    t3 = title('Distribución de RSSI por Spreading Factor', 'FontSize', 14, 'FontWeight', 'bold');
    set(t3, 'Color', 'k');
    grid on;
    export_figure(fig3, fig_dir, [FIG_PREFIX '_boxplot_rssi']);

    % -------------------------------------------------------------------------
    % GRÁFICA 4: Boxplot de SNR por SF con Umbrales de Demodulación
    % -------------------------------------------------------------------------
    fig4 = figure('Name', 'LoRaWAN - Boxplot SNR por SF', ...
                  'NumberTitle', 'off', 'Position', [150 550 780 470]);
    set(fig4, 'Color', 'w');
    boxplot(T_ul.snr_db, T_ul.sf, 'Labels', sf_labels, 'Colors', [0.2 0.2 0.2], ...
        'Symbol', '.r', 'OutlierSize', 3);
    hold on;
    h_thresh = gobjects(n_sf, 1);
    for k = 1:n_sf
        h_thresh(k) = plot(k, snr_demod_thresholds(k), 'v', 'MarkerSize', 8, ...
            'MarkerFaceColor', colores_sf(k,:), 'MarkerEdgeColor', 'k', 'LineWidth', 1);
    end
    hold off;
    ax4 = gca;
    set(ax4, 'Color', 'w', 'FontSize', 11);
    ax4.XColor = [0.15 0.15 0.15]; ax4.YColor = [0.15 0.15 0.15];
    ax4.GridColor = [0.8 0.8 0.8]; ax4.GridAlpha = 0.5;
    xlabel('Spreading Factor (SF)', 'FontSize', 12, 'FontWeight', 'bold', 'Color', 'k');
    ylabel('Relación Señal a Ruido - SNR (dB)', 'FontSize', 12, 'FontWeight', 'bold', 'Color', 'k');
    t4 = title('Distribución de SNR por SF y Umbrales Teóricos de Demodulación', 'FontSize', 13, 'FontWeight', 'bold');
    set(t4, 'Color', 'k');
    ylim([-24, 15]);
    grid on;

    legend_labels = arrayfun(@(k) sprintf('%s: %.1f dB', sf_labels{k}, snr_demod_thresholds(k)), 1:n_sf, 'UniformOutput', false);
    lg4 = legend(h_thresh, legend_labels, 'Location', 'southwest', 'FontSize', 9, 'NumColumns', 2);
    title(lg4, 'Umbral de Demodulación');
    set(lg4, 'Color', 'w', 'TextColor', 'k', 'EdgeColor', [0.8 0.8 0.8]);

    export_figure(fig4, fig_dir, [FIG_PREFIX '_boxplot_snr']);

    % -------------------------------------------------------------------------
    % GRÁFICA 5: Histograma y FDP del RSSI Global
    % -------------------------------------------------------------------------
    fig5 = figure('Name', 'LoRaWAN - Histograma y FDP de RSSI Global', ...
                  'NumberTitle', 'off', 'Position', [200 100 720 450]);
    set(fig5, 'Color', 'w');
    rssi_v = T_ul.rssi_dbm(~isnan(T_ul.rssi_dbm));
    histogram(rssi_v, 40, 'Normalization', 'pdf', ...
        'FaceColor', c_azul_suave, 'FaceAlpha', 0.65, 'EdgeColor', 'w');
    hold on;
    pd_rssi = fitdist(rssi_v, 'Normal');
    x_r = linspace(min(rssi_v), max(rssi_v), 200);
    plot(x_r, pdf(pd_rssi, x_r), '-', 'Color', c_rojo_alerta, 'LineWidth', 2);
    hold off;
    ax5 = gca;
    set(ax5, 'Color', 'w', 'FontSize', 11);
    ax5.XColor = [0.15 0.15 0.15]; ax5.YColor = [0.15 0.15 0.15];
    ax5.GridColor = [0.8 0.8 0.8]; ax5.GridAlpha = 0.5;
    xlabel('RSSI (dBm)', 'FontSize', 12, 'FontWeight', 'bold', 'Color', 'k');
    ylabel('Densidad de Probabilidad (FDP)', 'FontSize', 12, 'FontWeight', 'bold', 'Color', 'k');
    t5 = title('Histograma y Función de Densidad de Probabilidad (FDP) de RSSI', 'FontSize', 14, 'FontWeight', 'bold');
    set(t5, 'Color', 'k');
    lg5 = legend({sprintf('Histograma Empírico (n=%d)', length(rssi_v)), ...
        sprintf('Ajuste Normal: \\mu=%.2f dBm, \\sigma=%.2f dB', pd_rssi.mu, pd_rssi.sigma)}, ...
        'Location', 'northeast', 'FontSize', 10);
    set(lg5, 'Color', 'w', 'TextColor', 'k', 'EdgeColor', [0.8 0.8 0.8]);
    grid on;
    export_figure(fig5, fig_dir, [FIG_PREFIX '_hist_rssi']);

    % -------------------------------------------------------------------------
    % GRÁFICA 6: Histograma y FDP del SNR Global
    % -------------------------------------------------------------------------
    fig6 = figure('Name', 'LoRaWAN - Histograma y FDP de SNR Global', ...
                  'NumberTitle', 'off', 'Position', [200 550 720 450]);
    set(fig6, 'Color', 'w');
    snr_v = T_ul.snr_db(~isnan(T_ul.snr_db));
    histogram(snr_v, 50, 'Normalization', 'pdf', ...
        'FaceColor', c_verde_exito, 'FaceAlpha', 0.65, 'EdgeColor', 'w');
    hold on;
    pd_snr = fitdist(snr_v, 'Normal');
    x_s = linspace(min(snr_v), max(snr_v), 200);
    plot(x_s, pdf(pd_snr, x_s), '-', 'Color', c_rojo_alerta, 'LineWidth', 2);
    hold off;
    ax6 = gca;
    set(ax6, 'Color', 'w', 'FontSize', 11);
    ax6.XColor = [0.15 0.15 0.15]; ax6.YColor = [0.15 0.15 0.15];
    ax6.GridColor = [0.8 0.8 0.8]; ax6.GridAlpha = 0.5;
    xlabel('SNR (dB)', 'FontSize', 12, 'FontWeight', 'bold', 'Color', 'k');
    ylabel('Densidad de Probabilidad (FDP)', 'FontSize', 12, 'FontWeight', 'bold', 'Color', 'k');
    t6 = title('Histograma y Función de Densidad de Probabilidad (FDP) de SNR', 'FontSize', 14, 'FontWeight', 'bold');
    set(t6, 'Color', 'k');
    lg6 = legend({sprintf('Histograma Empírico (n=%d)', length(snr_v)), ...
        sprintf('Ajuste Normal: \\mu=%.2f dB, \\sigma=%.2f dB', pd_snr.mu, pd_snr.sigma)}, ...
        'Location', 'northeast', 'FontSize', 10);
    set(lg6, 'Color', 'w', 'TextColor', 'k', 'EdgeColor', [0.8 0.8 0.8]);
    grid on;
    export_figure(fig6, fig_dir, [FIG_PREFIX '_hist_snr']);

    %% ========================================================================
    %  4. ANÁLISIS DE LATENCIA, TEMPORIZACIÓN Y RTT (FÍSICO COMPLETO)
    %  ========================================================================
    fprintf('=== PASO 4: ANÁLISIS DE LATENCIA Y RTT FÍSICO (CON AIRTIMES) ===\n\n');

    % -------------------------------------------------------------------------
    % GRÁFICA 7: Descomposición del RTT Físico Completo por SF (5 Componentes)
    % -------------------------------------------------------------------------
    fig7 = figure('Name', 'LoRaWAN - Descomposición de RTT Físico por SF', ...
                  'NumberTitle', 'off', 'Position', [250 100 850 500]);
    set(fig7, 'Color', 'w');

    rtt_decomp = zeros(n_sf, 5);
    for k = 1:n_sf
        sf_k = sf_values(k);
        idx = T_rtt.sf == sf_k & ~isnan(T_rtt.rtt_s);
        rtt_decomp(k,1) = mean(T_rtt.airtime_s(idx), 'omitnan');            % 1. Airtime Subida (Nodo -> Gateway)
        rtt_decomp(k,2) = mean(T_rtt.network_delay_s(idx), 'omitnan');       % 2. Tránsito IP Subida (Gateway -> Cloud TTN)
        rtt_decomp(k,3) = mean(T_rtt.cloud_turnaround_s(idx), 'omitnan');   % 3. Procesamiento Cloud TTN
        rtt_decomp(k,4) = mean(T_rtt.tx_delay_s(idx), 'omitnan');           % 4. Despacho IP Bajada (Cloud TTN -> Gateway)
        rtt_decomp(k,5) = mean(T_rtt.airtime_downlink_s(idx), 'omitnan');   % 5. Airtime Bajada ACK (Gateway -> Nodo)
    end

    b7 = bar(rtt_decomp, 'stacked');
    b7(1).FaceColor = [0.20, 0.60, 0.80];   % T_aire_ul (Azul suave)
    b7(2).FaceColor = c_purpura_acento;    % T_red (Púrpura acento)
    b7(3).FaceColor = c_azul_primario;     % T_nube (Azul institucional)
    b7(4).FaceColor = c_naranja_sec;       % T_bajada (Naranja secundario)
    b7(5).FaceColor = c_verde_exito;       % T_aire_dl (Verde éxito)

    ax7 = gca;
    set(ax7, 'Color', 'w', 'FontSize', 11);
    ax7.XColor = [0.15 0.15 0.15]; ax7.YColor = [0.15 0.15 0.15];
    ax7.GridColor = [0.8 0.8 0.8]; ax7.GridAlpha = 0.5;
    set(ax7, 'XTickLabel', sf_labels);
    xlabel('Spreading Factor (SF)', 'FontSize', 12, 'FontWeight', 'bold', 'Color', 'k');
    ylabel('Tiempo Promedio (segundos)', 'FontSize', 12, 'FontWeight', 'bold', 'Color', 'k');
    t7 = title('Descomposición Temporal del Round Trip Time Físico Completo (RTT_{PHY})', 'FontSize', 14, 'FontWeight', 'bold');
    set(t7, 'Color', 'k');
    lg7 = legend({ ...
        'T_{aire, UL} (Airtime Subida: Nodo \rightarrow Gateway)', ...
        'T_{red} (Tránsito IP: Gateway \rightarrow Cloud TTN)', ...
        'T_{nube} (Procesamiento Cloud TTN)', ...
        'T_{bajada} (Despacho IP: Cloud TTN \rightarrow Gateway)', ...
        'T_{aire, DL} (Airtime Bajada ACK: Gateway \rightarrow Nodo)'}, ...
        'Location', 'northwest', 'FontSize', 9);
    set(lg7, 'Color', 'w', 'TextColor', 'k', 'EdgeColor', [0.8 0.8 0.8]);
    grid on;

    rtt_totales = sum(rtt_decomp, 2);
    ylim([0, max(rtt_totales)*1.18]);
    for i = 1:n_sf
        text(i, rtt_totales(i) + max(rtt_totales)*0.025, sprintf('%.3f s', rtt_totales(i)), ...
            'HorizontalAlignment', 'center', 'FontSize', 9, 'FontWeight', 'bold', 'Color', 'k');
    end
    export_figure(fig7, fig_dir, [FIG_PREFIX '_rtt_decomp']);

    % -------------------------------------------------------------------------
    % GRÁFICA 8: Boxplot de Latencia Extremo a Extremo (Uplink) por SF
    % -------------------------------------------------------------------------
    fig8 = figure('Name', 'LoRaWAN - Latencia E2E Uplink por SF', ...
                  'NumberTitle', 'off', 'Position', [250 550 750 450]);
    set(fig8, 'Color', 'w');
    boxplot(T_ul.total_uplink_delay_s, T_ul.sf, 'Labels', sf_labels, ...
        'Colors', [0.2 0.2 0.2], 'Symbol', '.r', 'OutlierSize', 3);
    ax8 = gca;
    set(ax8, 'Color', 'w', 'FontSize', 11);
    ax8.XColor = [0.15 0.15 0.15]; ax8.YColor = [0.15 0.15 0.15];
    ax8.GridColor = [0.8 0.8 0.8]; ax8.GridAlpha = 0.5;
    xlabel('Spreading Factor', 'FontSize', 12, 'FontWeight', 'bold', 'Color', 'k');
    ylabel('Latencia Total E2E Uplink (s)', 'FontSize', 12, 'FontWeight', 'bold', 'Color', 'k');
    t8 = title('Latencia Total de Subida Extremo a Extremo (Airtime + Red) por SF', 'FontSize', 14, 'FontWeight', 'bold');
    set(t8, 'Color', 'k');
    grid on;
    export_figure(fig8, fig_dir, [FIG_PREFIX '_boxplot_latencia']);

    % -------------------------------------------------------------------------
    % GRÁFICA 9: Histograma y FDP del RTT: Infraestructura vs. Físico Completo
    % -------------------------------------------------------------------------
    fig9 = figure('Name', 'LoRaWAN - Comparativa Histograma y FDP del RTT', ...
                  'NumberTitle', 'off', 'Position', [150 100 1050 460]);
    set(fig9, 'Color', 'w');

    rtt_infra_valid = T_rtt.rtt_s(~isnan(T_rtt.rtt_s));
    rtt_phy_valid   = T_rtt.rtt_phy_complete(~isnan(T_rtt.rtt_phy_complete));

    % Subplot 1: RTT de Infraestructura (Sin Airtimes)
    subplot(1,2,1);
    histogram(rtt_infra_valid, 50, 'Normalization', 'pdf', ...
        'FaceColor', c_purpura_acento, 'FaceAlpha', 0.65, 'EdgeColor', 'w');
    hold on;
    pd_rtt_infra = fitdist(rtt_infra_valid, 'Normal');
    x_rtt_inf = linspace(min(rtt_infra_valid), max(rtt_infra_valid), 250);
    plot(x_rtt_inf, pdf(pd_rtt_infra, x_rtt_inf), '-', 'Color', c_rojo_alerta, 'LineWidth', 2);
    hold off;
    ax9a = gca;
    set(ax9a, 'Color', 'w', 'FontSize', 10);
    ax9a.XColor = [0.15 0.15 0.15]; ax9a.YColor = [0.15 0.15 0.15];
    ax9a.GridColor = [0.8 0.8 0.8]; ax9a.GridAlpha = 0.5;
    xlabel('RTT de Infraestructura (s)', 'FontSize', 11, 'FontWeight', 'bold', 'Color', 'k');
    ylabel('Densidad de Probabilidad (FDP)', 'FontSize', 11, 'FontWeight', 'bold', 'Color', 'k');
    t9a = title('(a) RTT de Infraestructura (Sin Airtimes)', 'FontSize', 12, 'FontWeight', 'bold');
    set(t9a, 'Color', 'k');
    lg9a = legend({sprintf('Muestras (n=%d)', length(rtt_infra_valid)), ...
        sprintf('Ajuste: \\mu=%.4f s, \\sigma=%.4f s', pd_rtt_infra.mu, pd_rtt_infra.sigma)}, ...
        'Location', 'northeast', 'FontSize', 9);
    set(lg9a, 'Color', 'w', 'TextColor', 'k', 'EdgeColor', [0.8 0.8 0.8]);
    grid on;

    % Subplot 2: RTT Físico Completo (Con Airtimes UL y DL)
    subplot(1,2,2);
    histogram(rtt_phy_valid, 60, 'Normalization', 'pdf', ...
        'FaceColor', [0.20, 0.60, 0.80], 'FaceAlpha', 0.65, 'EdgeColor', 'w');
    hold on;
    pd_rtt_phy = fitdist(rtt_phy_valid, 'Normal');
    x_rtt_phy = linspace(min(rtt_phy_valid), max(rtt_phy_valid), 250);
    plot(x_rtt_phy, pdf(pd_rtt_phy, x_rtt_phy), '-', 'Color', c_rojo_alerta, 'LineWidth', 2);
    hold off;
    ax9b = gca;
    set(ax9b, 'Color', 'w', 'FontSize', 10);
    ax9b.XColor = [0.15 0.15 0.15]; ax9b.YColor = [0.15 0.15 0.15];
    ax9b.GridColor = [0.8 0.8 0.8]; ax9b.GridAlpha = 0.5;
    xlabel('RTT Físico Completo - RTT_{PHY} (s)', 'FontSize', 11, 'FontWeight', 'bold', 'Color', 'k');
    ylabel('Densidad de Probabilidad (FDP)', 'FontSize', 11, 'FontWeight', 'bold', 'Color', 'k');
    t9b = title('(b) RTT Físico Completo (Con Airtimes UL y DL)', 'FontSize', 12, 'FontWeight', 'bold');
    set(t9b, 'Color', 'k');
    lg9b = legend({sprintf('Muestras (n=%d)', length(rtt_phy_valid)), ...
        sprintf('Ajuste: \\mu=%.4f s, \\sigma=%.4f s', pd_rtt_phy.mu, pd_rtt_phy.sigma)}, ...
        'Location', 'northeast', 'FontSize', 9);
    set(lg9b, 'Color', 'w', 'TextColor', 'k', 'EdgeColor', [0.8 0.8 0.8]);
    grid on;

    export_figure(fig9, fig_dir, [FIG_PREFIX '_hist_rtt']);

    % -------------------------------------------------------------------------
    % GRÁFICA 10: CDF del RTT: Infraestructura vs. Físico Completo
    % -------------------------------------------------------------------------
    fig10 = figure('Name', 'LoRaWAN - Comparativa CDF del RTT', ...
                   'NumberTitle', 'off', 'Position', [150 550 1050 460]);
    set(fig10, 'Color', 'w');

    % Subplot 1: CDF RTT de Infraestructura (Sin Airtimes)
    subplot(1,2,1);
    [f_cdf_inf, x_cdf_inf] = ecdf(rtt_infra_valid);
    plot(x_cdf_inf, f_cdf_inf * 100, '-', 'Color', c_purpura_acento, 'LineWidth', 2.2);
    hold on;
    p50_inf = prctile(rtt_infra_valid, 50);
    p95_inf = prctile(rtt_infra_valid, 95);
    p99_inf = prctile(rtt_infra_valid, 99);
    xline(p50_inf, '--', sprintf('P50 = %.3f s', p50_inf), 'Color', c_verde_exito, 'LineWidth', 1.3, 'FontSize', 9);
    xline(p95_inf, '--', sprintf('P95 = %.3f s', p95_inf), 'Color', c_naranja_sec, 'LineWidth', 1.3, 'FontSize', 9);
    xline(p99_inf, '--', sprintf('P99 = %.3f s', p99_inf), 'Color', c_rojo_alerta, 'LineWidth', 1.3, 'FontSize', 9);
    hold off;
    ax10a = gca;
    set(ax10a, 'Color', 'w', 'FontSize', 10);
    ax10a.XColor = [0.15 0.15 0.15]; ax10a.YColor = [0.15 0.15 0.15];
    ax10a.GridColor = [0.8 0.8 0.8]; ax10a.GridAlpha = 0.5;
    xlabel('RTT de Infraestructura (s)', 'FontSize', 11, 'FontWeight', 'bold', 'Color', 'k');
    ylabel('Probabilidad Acumulada (%)', 'FontSize', 11, 'FontWeight', 'bold', 'Color', 'k');
    t10a = title('(a) CDF - RTT Infraestructura (Sin Airtimes)', 'FontSize', 12, 'FontWeight', 'bold');
    set(t10a, 'Color', 'k');
    grid on;

    % Subplot 2: CDF RTT Físico Completo (Con Airtimes UL y DL)
    subplot(1,2,2);
    [f_cdf_phy, x_cdf_phy] = ecdf(rtt_phy_valid);
    plot(x_cdf_phy, f_cdf_phy * 100, '-', 'Color', c_azul_primario, 'LineWidth', 2.2);
    hold on;
    p50_phy = prctile(rtt_phy_valid, 50);
    p95_phy = prctile(rtt_phy_valid, 95);
    p99_phy = prctile(rtt_phy_valid, 99);
    xline(p50_phy, '--', sprintf('P50 = %.3f s', p50_phy), 'Color', c_verde_exito, 'LineWidth', 1.3, 'FontSize', 9);
    xline(p95_phy, '--', sprintf('P95 = %.3f s', p95_phy), 'Color', c_naranja_sec, 'LineWidth', 1.3, 'FontSize', 9);
    xline(p99_phy, '--', sprintf('P99 = %.3f s', p99_phy), 'Color', c_rojo_alerta, 'LineWidth', 1.3, 'FontSize', 9);
    hold off;
    ax10b = gca;
    set(ax10b, 'Color', 'w', 'FontSize', 10);
    ax10b.XColor = [0.15 0.15 0.15]; ax10b.YColor = [0.15 0.15 0.15];
    ax10b.GridColor = [0.8 0.8 0.8]; ax10b.GridAlpha = 0.5;
    xlabel('RTT Físico Completo - RTT_{PHY} (s)', 'FontSize', 11, 'FontWeight', 'bold', 'Color', 'k');
    ylabel('Probabilidad Acumulada (%)', 'FontSize', 11, 'FontWeight', 'bold', 'Color', 'k');
    t10b = title('(b) CDF - RTT Físico Completo (Con Airtimes UL y DL)', 'FontSize', 12, 'FontWeight', 'bold');
    set(t10b, 'Color', 'k');
    grid on;

    export_figure(fig10, fig_dir, [FIG_PREFIX '_cdf_rtt']);

    %% ========================================================================
    %  5. EVOLUCIÓN TEMPORAL DEL ENLACE Y DECISIONES ADR
    %  ========================================================================
    fprintf('=== PASO 5: EVOLUCIÓN TEMPORAL Y DINÁMICA ADR ===\n\n');

    t_horas = hours(T_ul.timestamp_dt - session_start);

    % -------------------------------------------------------------------------
    % GRÁFICA 11: Serie Temporal de RSSI y SNR (84 horas)
    % -------------------------------------------------------------------------
    fig11 = figure('Name', 'LoRaWAN - Evolución Temporal RSSI y SNR (84h)', ...
                   'NumberTitle', 'off', 'Position', [350 100 1000 550]);
    set(fig11, 'Color', 'w');

    subplot(2,1,1);
    hold on;
    for k = 1:n_sf
        sf_k = sf_values(k);
        idx = T_ul.sf == sf_k;
        plot(t_horas(idx), T_ul.rssi_dbm(idx), '.', 'Color', colores_sf(k,:), 'MarkerSize', 6);
    end
    hold off;
    ax11a = gca;
    set(ax11a, 'Color', 'w', 'FontSize', 10);
    ax11a.XColor = [0.15 0.15 0.15]; ax11a.YColor = [0.15 0.15 0.15];
    ax11a.GridColor = [0.8 0.8 0.8]; ax11a.GridAlpha = 0.5;
    ylabel('RSSI (dBm)', 'FontSize', 11, 'FontWeight', 'bold', 'Color', 'k');
    t11a = title('Evolución Temporal del RSSI durante 84 Horas de Transmisión Continua', 'FontSize', 13, 'FontWeight', 'bold');
    set(t11a, 'Color', 'k');
    lg11a = legend(sf_labels, 'Location', 'eastoutside', 'FontSize', 9);
    set(lg11a, 'Color', 'w', 'TextColor', 'k', 'EdgeColor', [0.8 0.8 0.8]);
    xlim([0, session_hours]);
    grid on;

    subplot(2,1,2);
    hold on;
    for k = 1:n_sf
        sf_k = sf_values(k);
        idx = T_ul.sf == sf_k;
        plot(t_horas(idx), T_ul.snr_db(idx), '.', 'Color', colores_sf(k,:), 'MarkerSize', 6);
    end
    hold off;
    ax11b = gca;
    set(ax11b, 'Color', 'w', 'FontSize', 10);
    ax11b.XColor = [0.15 0.15 0.15]; ax11b.YColor = [0.15 0.15 0.15];
    ax11b.GridColor = [0.8 0.8 0.8]; ax11b.GridAlpha = 0.5;
    xlabel('Tiempo Transcurrido (Horas)', 'FontSize', 12, 'FontWeight', 'bold', 'Color', 'k');
    ylabel('SNR (dB)', 'FontSize', 11, 'FontWeight', 'bold', 'Color', 'k');
    t11b = title('Evolución Temporal del SNR durante 84 Horas de Transmisión Continua', 'FontSize', 13, 'FontWeight', 'bold');
    set(t11b, 'Color', 'k');
    xlim([0, session_hours]);
    grid on;
    export_figure(fig11, fig_dir, [FIG_PREFIX '_evolucion_temporal']);

    % -------------------------------------------------------------------------
    % GRÁFICA 12: Mapa de Calor (Heatmap) de Ocurrencia de SF por Hora (ADR)
    % -------------------------------------------------------------------------
    fig12 = figure('Name', 'LoRaWAN - Mapa de Calor ADR', ...
                   'NumberTitle', 'off', 'Position', [350 550 900 400]);
    set(fig12, 'Color', 'w');

    n_bins_h = ceil(session_hours);
    matriz_calor = zeros(n_sf, n_bins_h);
    for k = 1:n_sf
        sf_k = sf_values(k);
        idx = T_ul.sf == sf_k;
        h_k = t_horas(idx);
        for b = 1:n_bins_h
            matriz_calor(k, b) = sum(h_k >= (b-1) & h_k < b);
        end
    end

    imagesc(matriz_calor);
    colormap(flipud(hot));
    cb = colorbar;
    cb.Label.String = 'Paquetes / Hora';
    cb.Label.FontSize = 11;
    cb.Label.FontWeight = 'bold';
    cb.Color = 'k';

    ax12 = gca;
    set(ax12, 'YTick', 1:n_sf, 'YTickLabel', sf_labels, 'FontSize', 11);
    ax12.XColor = [0.15 0.15 0.15]; ax12.YColor = [0.15 0.15 0.15];
    xlabel('Tiempo de Sesión (Horas)', 'FontSize', 12, 'FontWeight', 'bold', 'Color', 'k');
    ylabel('Spreading Factor', 'FontSize', 12, 'FontWeight', 'bold', 'Color', 'k');
    t12 = title('Mapa de Calor: Ocurrencia de Spreading Factor por Hora (Mecanismo ADR)', 'FontSize', 14, 'FontWeight', 'bold');
    set(t12, 'Color', 'k');

    marcas_x = 1:12:n_bins_h;
    set(ax12, 'XTick', marcas_x, 'XTickLabel', arrayfun(@(x) sprintf('%dh', x-1), marcas_x, 'UniformOutput', false));
    export_figure(fig12, fig_dir, [FIG_PREFIX '_heatmap_adr']);

    %% ========================================================================
    %  6. DISTRIBUCIÓN DE CANALES DE FRECUENCIA AU915
    %  ========================================================================
    fprintf('=== PASO 6: DISTRIBUCIÓN DE CANALES AU915 ===\n\n');

    % -------------------------------------------------------------------------
    % GRÁFICA 13: Distribución de Paquetes por Canal de Frecuencia
    % -------------------------------------------------------------------------
    fig13 = figure('Name', 'LoRaWAN - Distribución de Canales AU915', ...
                   'NumberTitle', 'off', 'Position', [400 100 750 450]);
    set(fig13, 'Color', 'w');

    frecuencias_mhz = T_ul.frequency_hz / 1e6;
    [frec_unicas, ~, idx_frec] = unique(frecuencias_mhz);
    conteos_frec = accumarray(idx_frec, 1);

    b13 = bar(conteos_frec, 'FaceColor', c_azul_primario, 'EdgeColor', 'w');
    ax13 = gca;
    set(ax13, 'Color', 'w', 'FontSize', 10);
    ax13.XColor = [0.15 0.15 0.15]; ax13.YColor = [0.15 0.15 0.15];
    ax13.GridColor = [0.8 0.8 0.8]; ax13.GridAlpha = 0.5;
    set(ax13, 'XTickLabel', arrayfun(@(f) sprintf('%.1f MHz', f), frec_unicas, 'UniformOutput', false));
    xtickangle(30);
    xlabel('Canal de Frecuencia (AU915 Sub-banda 2)', 'FontSize', 12, 'FontWeight', 'bold', 'Color', 'k');
    ylabel('Número de Paquetes Recibidos', 'FontSize', 12, 'FontWeight', 'bold', 'Color', 'k');
    t13 = title('Distribución de Carga por Canal de Frecuencia en el Gateway', 'FontSize', 14, 'FontWeight', 'bold');
    set(t13, 'Color', 'k');
    grid on;
    ylim([0, max(conteos_frec)*1.18]);

    for i = 1:length(frec_unicas)
        text(i, conteos_frec(i) + max(conteos_frec)*0.025, sprintf('%d', conteos_frec(i)), ...
            'HorizontalAlignment', 'center', 'FontSize', 10, 'FontWeight', 'bold', 'Color', 'k');
    end
    export_figure(fig13, fig_dir, [FIG_PREFIX '_canales_au915']);

    %% ========================================================================
    %  7. REGISTRO AMBIENTAL (TELEMETRÍA: T, H, PRESIÓN ATMOSFÉRICA)
    %  ========================================================================
    fprintf('=== PASO 7: REGISTRO AMBIENTAL Y TELEMETRÍA ===\n\n');

    % -------------------------------------------------------------------------
    % GRÁFICA 14: Serie Temporal de Temperatura, Humedad y Presión Atmosférica
    % -------------------------------------------------------------------------
    fig14 = figure('Name', 'LoRaWAN - Telemetría del Sensor', ...
                   'NumberTitle', 'off', 'Position', [400 550 1000 580]);
    set(fig14, 'Color', 'w');

    t_val = ~isnan(temperature) & temperature > 0 & pressure > 500;
    t_h_val = t_horas(t_val);
    temp_v = temperature(t_val);
    hum_v  = humidity(t_val);
    pres_v = pressure(t_val);

    % Subplot 1: Temperatura y Humedad Relativa
    subplot(2,1,1);
    yyaxis left
    plot(t_h_val, temp_v, '-', 'Color', c_rojo_alerta, 'LineWidth', 1.2);
    ylabel('Temperatura (°C)', 'FontSize', 11, 'FontWeight', 'bold');
    ax14a = gca;
    set(ax14a, 'Color', 'w', 'FontSize', 10);
    ax14a.YColor = c_rojo_alerta;

    yyaxis right
    plot(t_h_val, hum_v, '-', 'Color', c_azul_primario, 'LineWidth', 1.2);
    ylabel('Humedad Relativa (%)', 'FontSize', 11, 'FontWeight', 'bold');
    ax14a.YColor = c_azul_primario;

    ax14a.XColor = [0.15 0.15 0.15];
    ax14a.GridColor = [0.8 0.8 0.8]; ax14a.GridAlpha = 0.5;
    xlim([0, session_hours]);
    grid on;
    lg14a = legend({'Temperatura (°C)', 'Humedad Relativa (%)'}, 'Location', 'northeast', 'FontSize', 9);
    set(lg14a, 'Color', 'w', 'TextColor', 'k', 'EdgeColor', [0.8 0.8 0.8]);

    % Subplot 2: Presión Atmosférica
    subplot(2,1,2);
    plot(t_h_val, pres_v, '-', 'Color', c_verde_exito, 'LineWidth', 1.2);
    ax14b = gca;
    set(ax14b, 'Color', 'w', 'FontSize', 10);
    ax14b.XColor = [0.15 0.15 0.15]; ax14b.YColor = [0.15 0.15 0.15];
    ax14b.GridColor = [0.8 0.8 0.8]; ax14b.GridAlpha = 0.5;
    xlabel('Tiempo Transcurrido (Horas)', 'FontSize', 11, 'FontWeight', 'bold', 'Color', 'k');
    ylabel('Presión Atmosférica (hPa)', 'FontSize', 11, 'FontWeight', 'bold', 'Color', 'k');
    xlim([0, session_hours]);
    grid on;
    lg14b = legend({'Presión Atmosférica (hPa)'}, 'Location', 'northeast', 'FontSize', 9);
    set(lg14b, 'Color', 'w', 'TextColor', 'k', 'EdgeColor', [0.8 0.8 0.8]);

    % Título único para la figura completa
    sg14 = sgtitle('Registro Ambiental Continuo: Temperatura, Humedad y Presión Atmosférica (84 Horas)', ...
        'FontSize', 13, 'FontWeight', 'bold', 'Color', 'k');

    export_figure(fig14, fig_dir, [FIG_PREFIX '_telemetria']);
else
    fprintf('\n  [AVISO]: Modo de prueba activo (EXPORTAR_SOLO_UNA_IMAGEN = true).\n');
    fprintf('           Se ha exportado únicamente: %s.svg\n', [FIG_PREFIX '_pdr_por_sf']);
    fprintf('           Las demás figuras se omitieron para permitir la validación visual previa.\n');
end

%% ========================================================================
%  8. RESUMEN FINAL EN CONSOLA
%  ========================================================================
fprintf('\n================================================================\n');
fprintf('  RESUMEN EJECUTIVO DE LA SESIÓN DE CAPTURA\n');
fprintf('================================================================\n\n');
fprintf('  Duración total:        %.1f horas (%.2f días)\n', session_hours, session_hours/24);
fprintf('  Total paquetes uplink: %d confirmados\n', n_ul);
fprintf('  PDR Uplink Global:     %.2f%% (%d esperados, %d perdidos)\n', total_ul_pdr, total_ul_expect, total_ul_lost);
fprintf('  PDR Downlink Global:   %.2f%% (%d ACKs confirmados, %d sin ACK)\n', total_dl_pdr, total_dl_acked, total_dl_noack);
rtt_valid = T_rtt.rtt_s(~isnan(T_rtt.rtt_s));
p50 = prctile(rtt_valid, 50); p95 = prctile(rtt_valid, 95); p99 = prctile(rtt_valid, 99);
fprintf('  RTT Infraestructura:   %.4f s (P50 = %.3f s, P95 = %.3f s, P99 = %.3f s)\n', mean(rtt_valid), p50, p95, p99);

rtt_phy_valid = T_rtt.rtt_phy_complete(~isnan(T_rtt.rtt_phy_complete));
p50_phy = prctile(rtt_phy_valid, 50); p95_phy = prctile(rtt_phy_valid, 95); p99_phy = prctile(rtt_phy_valid, 99);
fprintf('  RTT Físico Completo:   %.4f s (P50 = %.3f s, P95 = %.3f s, P99 = %.3f s)\n', mean(rtt_phy_valid), p50_phy, p95_phy, p99_phy);

fprintf('  RSSI Promedio:         %.2f dBm\n', mean(T_ul.rssi_dbm, 'omitnan'));
fprintf('  SNR Promedio:          %.2f dB\n', mean(T_ul.snr_db, 'omitnan'));
fprintf('\n================================================================\n');
if EXPORTAR_SOLO_UNA_IMAGEN
    fprintf('  Modo prueba: 1 figura generada en Figures/%s.svg\n', [FIG_PREFIX '_pdr_por_sf']);
else
    fprintf('  Se generaron 14 figuras SVG en la carpeta Figures/\n');
end
fprintf('================================================================\n');

%% ========================================================================
%  FUNCIONES AUXILIARES
%  ========================================================================

function export_figure(fig, fig_dir, name)
    % Exporta la figura a formato SVG vectorial con fondo blanco
    svg_path = fullfile(fig_dir, [name '.svg']);
    exportgraphics(fig, svg_path, 'BackgroundColor', 'white');
    fprintf('  ✓ Guardada: %s.svg\n', name);
end
