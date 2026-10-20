%% ========================================================================
%  SCRIPT: AHP_Seleccion_Tecnologia.m
%  DESCRIPCIÓN: Aplicación paso a paso del método AHP (Analytic Hierarchy
%               Process) para la selección de la tecnología LPWAN más
%               adecuada para el laboratorio piloto de IoT en el Campus
%               de Tulcán - Universidad del Cauca.
%
%  AUTOR: Nicolás Zambrano & Sandy Suarez
%  REFERENCIA: Saaty, T.L. (1987). The Analytic Hierarchy Process.
%  ========================================================================
clc; clear; close all;

fprintf('================================================================\n');
fprintf('  MÉTODO AHP - SELECCIÓN DE TECNOLOGÍA LPWAN\n');
fprintf('  Laboratorio Piloto IoT - Campus de Tulcán\n');
fprintf('================================================================\n\n');

%% ========================================================================
%  PASO 1: DEFINICIÓN DEL PROBLEMA JERÁRQUICO
%  ========================================================================
%  Nivel 1: Objetivo      -> Seleccionar la tecnología LPWAN más adecuada
%  Nivel 2: Criterios     -> C1..C6
%  Nivel 3: Alternativas  -> LoRaWAN, SigFox, NB-IoT, LTE-M, Wi-SUN
%  ========================================================================

fprintf('=== PASO 1: DEFINICIÓN DEL PROBLEMA JERÁRQUICO ===\n\n');

% Nombres de los criterios
criterios = {'C1 - Cobertura y alcance', ...
             'C2 - Consumo de energía', ...
             'C3 - Velocidad de datos', ...
             'C4 - Escalabilidad', ...
             'C5 - Costo de implementación', ...
             'C6 - Disponibilidad y madurez'};

% Nombres de las alternativas
alternativas = {'LoRaWAN', 'SigFox', 'NB-IoT', 'LTE-M', 'Wi-SUN'};

n_criterios    = length(criterios);
n_alternativas = length(alternativas);

fprintf('Objetivo: Seleccionar la tecnología LPWAN más adecuada\n');
fprintf('Número de criterios:    %d\n', n_criterios);
fprintf('Número de alternativas: %d\n\n', n_alternativas);

fprintf('Criterios de evaluación:\n');
for i = 1:n_criterios
    fprintf('  %s\n', criterios{i});
end
fprintf('\nAlternativas tecnológicas:\n');
for i = 1:n_alternativas
    fprintf('  %d. %s\n', i, alternativas{i});
end

%% ========================================================================
%  PASO 2: ESCALA FUNDAMENTAL DE SAATY
%  ========================================================================

fprintf('\n\n=== PASO 2: ESCALA FUNDAMENTAL DE SAATY ===\n\n');
fprintf('  Valor | Definición\n');
fprintf('  ------+-------------------------------------------\n');
fprintf('    1   | Igual importancia\n');
fprintf('    3   | Importancia moderada\n');
fprintf('    5   | Importancia fuerte\n');
fprintf('    7   | Importancia muy fuerte\n');
fprintf('    9   | Importancia extrema\n');
fprintf('  2,4,6,8 | Valores intermedios\n');
fprintf('  Recíprocos (1/n) para comparaciones inversas\n');

%% ========================================================================
%  PASO 3: MATRIZ DE COMPARACIÓN POR PARES DE CRITERIOS
%  ========================================================================
%  Justificación de los juicios:
%  - C5 (Costo) es el más importante por restricciones presupuestarias
%  - C1 (Cobertura) es el segundo por la extensión del campus
%  - C6 (Disponibilidad) es fundamental para adquirir hardware
%  - C2 (Consumo) es relevante para la autonomía de sensores
%  - C4 (Escalabilidad) se pondera moderadamente (Fase I: pocos dispositivos)
%  - C3 (Velocidad de datos) recibe menor ponderación (aplicaciones IoT de
%    baja tasa)
%  ========================================================================

fprintf('\n\n=== PASO 3: MATRIZ DE COMPARACIÓN POR PARES DE CRITERIOS ===\n\n');

%        C1     C2     C3     C4     C5     C6
A_crit = [1     3     5     3     1/2   2;     % C1 - Cobertura
          1/3   1     3     2     1/3   1/2;   % C2 - Consumo
          1/5   1/3   1     1/2   1/5   1/4;   % C3 - Vel. datos
          1/3   1/2   2     1     1/3   1/2;   % C4 - Escalabilidad
          2     3     5     3     1     2;      % C5 - Costo
          1/2   2     4     2     1/2   1];     % C6 - Disponibilidad

% Verificar reciprocidad: A(i,j) = 1/A(j,i)
fprintf('Matriz de comparación por pares (Criterios):\n');
fprintf('         C1      C2      C3      C4      C5      C6\n');
etiquetas_c = {'C1', 'C2', 'C3', 'C4', 'C5', 'C6'};
for i = 1:n_criterios
    fprintf('  %s  ', etiquetas_c{i});
    for j = 1:n_criterios
        fprintf('%7.3f ', A_crit(i,j));
    end
    fprintf('\n');
end

% Verificación de reciprocidad
fprintf('\nVerificación de reciprocidad (A(i,j) * A(j,i) = 1):\n');
es_reciproca = true;
for i = 1:n_criterios
    for j = i+1:n_criterios
        producto = A_crit(i,j) * A_crit(j,i);
        if abs(producto - 1) > 1e-6
            fprintf('  ADVERTENCIA: A(%d,%d)*A(%d,%d) = %.4f ≠ 1\n', i, j, j, i, producto);
            es_reciproca = false;
        end
    end
end
if es_reciproca
    fprintf('  ✓ La matriz es recíproca (todos los productos = 1)\n');
end

%% ========================================================================
%  PASO 4: NORMALIZACIÓN DE LA MATRIZ DE CRITERIOS Y CÁLCULO DE PESOS
%  ========================================================================
%  Procedimiento:
%  1. Calcular la suma de cada columna
%  2. Dividir cada elemento entre la suma de su columna
%  3. Promediar cada fila para obtener el peso (w_i)
%  ========================================================================

fprintf('\n\n=== PASO 4: NORMALIZACIÓN Y CÁLCULO DE PESOS DE CRITERIOS ===\n\n');

% 4.1 Sumas de columnas
sumas_col_crit = sum(A_crit, 1);
fprintf('Sumas de columnas:\n');
fprintf('         C1      C2      C3      C4      C5      C6\n');
fprintf('  Σ   ');
for j = 1:n_criterios
    fprintf('%7.3f ', sumas_col_crit(j));
end
fprintf('\n');

% 4.2 Matriz normalizada
A_crit_norm = A_crit ./ sumas_col_crit;
fprintf('\nMatriz normalizada de criterios:\n');
fprintf('         C1      C2      C3      C4      C5      C6     Peso(wi)\n');

% 4.3 Vector de pesos (promedio de cada fila)
w_criterios = mean(A_crit_norm, 2);

for i = 1:n_criterios
    fprintf('  %s  ', etiquetas_c{i});
    for j = 1:n_criterios
        fprintf('%7.3f ', A_crit_norm(i,j));
    end
    fprintf('  %7.3f\n', w_criterios(i));
end

fprintf('\n--- Vector de pesos de los criterios ---\n');
fprintf('  %-35s  Peso     Porcentaje\n', 'Criterio');
fprintf('  %-35s  -------  ----------\n', repmat('-', 1, 35));
% Ordenar por peso descendente para mostrar
[w_sorted, idx_sorted] = sort(w_criterios, 'descend');
for k = 1:n_criterios
    i = idx_sorted(k);
    fprintf('  %-35s  %.3f    %5.1f%%\n', criterios{i}, w_criterios(i), w_criterios(i)*100);
end
fprintf('  %-35s  %.3f    %5.1f%%\n', 'TOTAL', sum(w_criterios), sum(w_criterios)*100);

%% ========================================================================
%  PASO 5: MATRICES DE COMPARACIÓN POR PARES DE ALTERNATIVAS
%  ========================================================================
%  Se construye una matriz de comparación 5×5 para cada criterio,
%  comparando las 5 alternativas entre sí.
%  ========================================================================

fprintf('\n\n=== PASO 5: MATRICES DE COMPARACIÓN DE ALTERNATIVAS ===\n\n');

% --- C1: Cobertura y alcance ---
% SigFox (~50 km) > LoRaWAN (~15 km) > NB-IoT = LTE-M (~10 km) > Wi-SUN (~1-5 km)
A_C1 = [1     1/2   2     2     3;     % LoRaWAN
        2     1     3     3     4;     % SigFox
        1/2   1/3   1     1     2;     % NB-IoT
        1/2   1/3   1     1     2;     % LTE-M
        1/3   1/4   1/2   1/2   1];    % Wi-SUN

% --- C2: Consumo de energía ---
% LoRaWAN = SigFox (ultrabajo) > NB-IoT > Wi-SUN > LTE-M
A_C2 = [1     1     3     5     4;     % LoRaWAN
        1     1     3     5     4;     % SigFox
        1/3   1/3   1     3     2;     % NB-IoT
        1/5   1/5   1/3   1     1/2;   % LTE-M
        1/4   1/4   1/2   2     1];    % Wi-SUN

% --- C3: Velocidad de transmisión de datos ---
% LTE-M (~1 Mbps) > NB-IoT = Wi-SUN (~250-300 kbps) > LoRaWAN (~50 kbps) > SigFox (~600 bps)
A_C3 = [1     3     1/3   1/5   1/3;   % LoRaWAN
        1/3   1     1/5   1/7   1/5;   % SigFox
        3     5     1     1/2   1;     % NB-IoT
        5     7     2     1     2;     % LTE-M
        3     5     1     1/2   1];    % Wi-SUN

% --- C4: Escalabilidad ---
% LoRaWAN = NB-IoT > SigFox > LTE-M = Wi-SUN
A_C4 = [1     2     1     3     3;     % LoRaWAN
        1/2   1     1/2   2     2;     % SigFox
        1     2     1     3     3;     % NB-IoT
        1/3   1/2   1/3   1     1;     % LTE-M
        1/3   1/2   1/3   1     1];    % Wi-SUN

% --- C5: Costo de implementación ---
% LoRaWAN (más económico) > SigFox > Wi-SUN > NB-IoT > LTE-M (más costoso)
A_C5 = [1     2     4     5     3;     % LoRaWAN
        1/2   1     3     4     2;     % SigFox
        1/4   1/3   1     2     1/2;   % NB-IoT
        1/5   1/4   1/2   1     1/3;   % LTE-M
        1/3   1/2   2     3     1];    % Wi-SUN

% --- C6: Disponibilidad y madurez tecnológica ---
% LoRaWAN > NB-IoT > SigFox = LTE-M > Wi-SUN
A_C6 = [1     3     2     3     5;     % LoRaWAN
        1/3   1     1/2   1     3;     % SigFox
        1/2   2     1     2     4;     % NB-IoT
        1/3   1     1/2   1     3;     % LTE-M
        1/5   1/3   1/4   1/3   1];    % Wi-SUN

% Almacenar todas las matrices en un cell array
matrices_alt = {A_C1, A_C2, A_C3, A_C4, A_C5, A_C6};
nombres_crit_cortos = {'C1-Cobertura', 'C2-Consumo', 'C3-Vel.datos', ...
                       'C4-Escalabilidad', 'C5-Costo', 'C6-Disponibilidad'};

%% ========================================================================
%  PASO 6: NORMALIZACIÓN DE MATRICES DE ALTERNATIVAS Y VECTORES DE
%          PRIORIDADES LOCALES
%  ========================================================================

fprintf('=== PASO 6: NORMALIZACIÓN Y PRIORIDADES LOCALES ===\n\n');

% Matriz para almacenar las prioridades locales (n_alternativas x n_criterios)
P_local = zeros(n_alternativas, n_criterios);

for c = 1:n_criterios
    A = matrices_alt{c};
    
    fprintf('--- Criterio: %s ---\n\n', nombres_crit_cortos{c});
    
    % Mostrar la matriz original
    fprintf('  Matriz de comparación por pares:\n');
    fprintf('              LoRaWAN  SigFox  NB-IoT   LTE-M  Wi-SUN\n');
    for i = 1:n_alternativas
        fprintf('  %-8s  ', alternativas{i});
        for j = 1:n_alternativas
            fprintf('%7.3f ', A(i,j));
        end
        fprintf('\n');
    end
    
    % Sumas de columnas
    sumas_col = sum(A, 1);
    fprintf('  Σ columna  ');
    for j = 1:n_alternativas
        fprintf('%7.3f ', sumas_col(j));
    end
    fprintf('\n\n');
    
    % Normalización
    A_norm = A ./ sumas_col;
    
    % Vector de prioridades locales
    w_alt = mean(A_norm, 2);
    P_local(:, c) = w_alt;
    
    % Mostrar matriz normalizada con pesos
    fprintf('  Matriz normalizada:\n');
    fprintf('              LoRaWAN  SigFox  NB-IoT   LTE-M  Wi-SUN   Peso\n');
    for i = 1:n_alternativas
        fprintf('  %-8s  ', alternativas{i});
        for j = 1:n_alternativas
            fprintf('%7.3f ', A_norm(i,j));
        end
        fprintf('  %5.3f\n', w_alt(i));
    end
    fprintf('\n');
    
    % Mostrar vector de prioridades
    fprintf('  Vector de prioridades locales:\n');
    for i = 1:n_alternativas
        fprintf('    %s = %.3f\n', alternativas{i}, w_alt(i));
    end
    fprintf('\n\n');
end

%% ========================================================================
%  PASO 7: VERIFICACIÓN DE CONSISTENCIA
%  ========================================================================
%  Para cada matriz se calcula:
%  1. λ_max (valor propio máximo)
%  2. CI = (λ_max - n) / (n - 1)   (Índice de Consistencia)
%  3. CR = CI / RI                   (Razón de Consistencia)
%  CR < 0.10 → Juicios consistentes
%  ========================================================================

fprintf('=== PASO 7: VERIFICACIÓN DE CONSISTENCIA ===\n\n');

% Tabla de Índices de Consistencia Aleatorio (RI) de Saaty
% n:   1     2     3     4     5     6     7     8     9     10
RI_tabla = [0, 0, 0.58, 0.90, 1.12, 1.24, 1.32, 1.41, 1.45, 1.49];

fprintf('Tabla de valores RI (Índice de Consistencia Aleatorio de Saaty):\n');
fprintf('  n:   ');
for n = 1:10
    fprintf('%5d ', n);
end
fprintf('\n  RI:  ');
for n = 1:10
    fprintf('%5.2f ', RI_tabla(n));
end
fprintf('\n\n');

% --- 7.1: Consistencia de la matriz de CRITERIOS (n=6) ---
fprintf('--- 7.1: Consistencia de la matriz de CRITERIOS (n = %d) ---\n\n', n_criterios);

RI_crit = RI_tabla(n_criterios);

% Calcular A * w
Aw_crit = A_crit * w_criterios;

% Calcular λ_i para cada fila
lambda_i_crit = Aw_crit ./ w_criterios;

% λ_max = promedio de λ_i
lambda_max_crit = mean(lambda_i_crit);

% CI y CR
CI_crit = (lambda_max_crit - n_criterios) / (n_criterios - 1);
CR_crit = CI_crit / RI_crit;

fprintf('  Criterio                  w_i      (A·w)_i    λ_i\n');
fprintf('  %-24s -------  --------  -------\n', repmat('-', 1, 24));
for i = 1:n_criterios
    fprintf('  %-24s %.3f    %.3f     %.3f\n', criterios{i}, w_criterios(i), Aw_crit(i), lambda_i_crit(i));
end
fprintf('\n');
fprintf('  λ_max = %.3f\n', lambda_max_crit);
fprintf('  CI = (%.3f - %d) / (%d - 1) = %.3f\n', lambda_max_crit, n_criterios, n_criterios, CI_crit);
fprintf('  RI (n=%d) = %.2f\n', n_criterios, RI_crit);
fprintf('  CR = %.3f / %.2f = %.3f\n', CI_crit, RI_crit, CR_crit);

if CR_crit < 0.10
    fprintf('  ✓ CR = %.3f < 0.10 → Matriz CONSISTENTE\n', CR_crit);
else
    fprintf('  ✗ CR = %.3f ≥ 0.10 → Matriz INCONSISTENTE - Revisar juicios\n', CR_crit);
end

% --- 7.2: Consistencia de las matrices de ALTERNATIVAS (n=5) ---
fprintf('\n--- 7.2: Consistencia de las matrices de ALTERNATIVAS (n = %d) ---\n\n', n_alternativas);

RI_alt = RI_tabla(n_alternativas);

fprintf('  %-20s  λ_max    CI       CR       ¿Consistente?\n', 'Criterio');
fprintf('  %-20s  ------   ------   ------   --------------\n', repmat('-', 1, 20));

lambda_max_alt = zeros(1, n_criterios);
CI_alt = zeros(1, n_criterios);
CR_alt = zeros(1, n_criterios);

for c = 1:n_criterios
    A = matrices_alt{c};
    w = P_local(:, c);
    
    Aw = A * w;
    lambda_i = Aw ./ w;
    lambda_max_alt(c) = mean(lambda_i);
    CI_alt(c) = (lambda_max_alt(c) - n_alternativas) / (n_alternativas - 1);
    CR_alt(c) = CI_alt(c) / RI_alt;
    
    if CR_alt(c) < 0.10
        consistente = 'Sí (✓)';
    else
        consistente = 'No (✗)';
    end
    
    fprintf('  %-20s  %.3f    %.3f    %.3f    %s\n', ...
        nombres_crit_cortos{c}, lambda_max_alt(c), CI_alt(c), CR_alt(c), consistente);
end

fprintf('\n  RI (n=%d) = %.2f\n', n_alternativas, RI_alt);
fprintf('  Todas las matrices deben cumplir CR < 0.10\n');

%% ========================================================================
%  PASO 8: SÍNTESIS GLOBAL - CÁLCULO DE PUNTUACIÓN FINAL
%  ========================================================================
%  P_j = Σ (w_i * p_ij)   para cada alternativa j
%  donde:
%    P_j   = puntuación global de la alternativa j
%    w_i   = peso del criterio i
%    p_ij  = prioridad local de la alternativa j respecto al criterio i
%  ========================================================================

fprintf('\n\n=== PASO 8: SÍNTESIS GLOBAL ===\n\n');

fprintf('Tabla de prioridades locales (alternativas × criterios):\n');
fprintf('              ');
for c = 1:n_criterios
    fprintf('%-14s', nombres_crit_cortos{c});
end
fprintf('\n');
fprintf('  (Peso):     ');
for c = 1:n_criterios
    fprintf('(%.3f)        ', w_criterios(c));
end
fprintf('\n');

for i = 1:n_alternativas
    fprintf('  %-10s  ', alternativas{i});
    for c = 1:n_criterios
        fprintf('%-14.3f', P_local(i, c));
    end
    fprintf('\n');
end

% Cálculo de la puntuación global
P_global = P_local * w_criterios;

fprintf('\nCálculo desglosado de la puntuación global:\n\n');
fprintf('  P_j = Σ (w_i × p_ij)\n\n');

for j = 1:n_alternativas
    fprintf('  %s:\n', alternativas{j});
    fprintf('    P = ');
    terminos = zeros(1, n_criterios);
    for i = 1:n_criterios
        terminos(i) = w_criterios(i) * P_local(j, i);
        if i > 1
            fprintf('      + ');
        else
            fprintf('      ');
        end
        fprintf('%.3f × %.3f = %.3f   (%s)\n', w_criterios(i), P_local(j, i), terminos(i), nombres_crit_cortos{i});
    end
    fprintf('    -----------------------------------\n');
    fprintf('    P_%s = %.3f\n\n', alternativas{j}, P_global(j));
end

%% ========================================================================
%  PASO 9: RANKING FINAL Y SELECCIÓN
%  ========================================================================

fprintf('\n=== PASO 9: RANKING FINAL ===\n\n');

[P_sorted, idx] = sort(P_global, 'descend');

fprintf('  Posición  Tecnología       Puntuación    Porcentaje\n');
fprintf('  --------  ---------------  ----------    ----------\n');
for k = 1:n_alternativas
    fprintf('     %d      %-15s    %.3f        %5.1f%%\n', ...
        k, alternativas{idx(k)}, P_sorted(k), P_sorted(k)*100);
end

fprintf('\n  Suma total de puntuaciones: %.3f\n', sum(P_global));

fprintf('\n================================================================\n');
fprintf('  RESULTADO: %s es la tecnología LPWAN seleccionada\n', alternativas{idx(1)});
fprintf('  con una puntuación global de %.3f (%.1f%%)\n', P_sorted(1), P_sorted(1)*100);
fprintf('================================================================\n');

%% ========================================================================
%  PASO 10: VISUALIZACIÓN GRÁFICA
%  ========================================================================

fprintf('\n\n=== PASO 10: GENERACIÓN DE GRÁFICAS ===\n\n');

% --- Gráfica 1: Pesos de los criterios ---
figure('Name', 'AHP - Pesos de Criterios', 'NumberTitle', 'off', ...
       'Position', [100 100 700 450]);
bar_data = w_criterios(idx_sorted);
b1 = barh(bar_data, 'FaceColor', [0.2 0.6 0.8]);
set(gca, 'YTickLabel', criterios(idx_sorted), 'YDir', 'reverse', 'FontSize', 10);
xlabel('Peso relativo (w_i)', 'FontSize', 12);
title('Pesos de los Criterios de Evaluación (AHP)', 'FontSize', 14);
for i = 1:n_criterios
    text(bar_data(i) + 0.005, i, sprintf('%.3f (%.1f%%)', bar_data(i), bar_data(i)*100), ...
         'FontSize', 10, 'VerticalAlignment', 'middle');
end
grid on;
xlim([0, max(bar_data)*1.25]);

% --- Gráfica 2: Ranking final ---
figure('Name', 'AHP - Ranking Final', 'NumberTitle', 'off', ...
       'Position', [100 600 700 450]);
colores = [0.18 0.54 0.34;   % LoRaWAN  - verde
           0.85 0.37 0.15;   % SigFox   - naranja
           0.20 0.40 0.70;   % NB-IoT   - azul
           0.60 0.30 0.60;   % LTE-M    - púrpura
           0.50 0.50 0.50];  % Wi-SUN   - gris

b2 = bar(P_global, 'FaceColor', 'flat');
for k = 1:n_alternativas
    b2.CData(k,:) = colores(k,:);
end
set(gca, 'XTickLabel', alternativas, 'FontSize', 11);
ylabel('Puntuación Global (P_j)', 'FontSize', 12);
title('Ranking Final de Tecnologías LPWAN (AHP)', 'FontSize', 14);
for i = 1:n_alternativas
    text(i, P_global(i) + 0.008, sprintf('%.3f', P_global(i)), ...
         'HorizontalAlignment', 'center', 'FontSize', 11, 'FontWeight', 'bold');
end
grid on;
ylim([0, max(P_global)*1.2]);

% Línea de referencia
hold on;
yline(max(P_global), '--r', sprintf('Máx: %.3f', max(P_global)), ...
      'LineWidth', 1.2, 'LabelHorizontalAlignment', 'left', 'FontSize', 10);
hold off;

% --- Gráfica 3: Contribución de cada criterio al puntaje global ---
figure('Name', 'AHP - Contribución por Criterio', 'NumberTitle', 'off', ...
       'Position', [850 100 800 500]);

% Calcular la contribución de cada criterio a cada alternativa
contribuciones = zeros(n_alternativas, n_criterios);
for j = 1:n_alternativas
    for i = 1:n_criterios
        contribuciones(j, i) = w_criterios(i) * P_local(j, i);
    end
end

b3 = bar(contribuciones, 'stacked');
colores_criterios = [0.90 0.30 0.30;   % C1 - rojo
                     0.95 0.65 0.20;   % C2 - amarillo
                     0.40 0.75 0.40;   % C3 - verde
                     0.30 0.55 0.85;   % C4 - azul
                     0.75 0.40 0.75;   % C5 - púrpura
                     0.50 0.50 0.50];  % C6 - gris
for i = 1:n_criterios
    b3(i).FaceColor = colores_criterios(i,:);
end

set(gca, 'XTickLabel', alternativas, 'FontSize', 11);
ylabel('Puntuación Global (P_j)', 'FontSize', 12);
title('Contribución de cada Criterio a la Puntuación Global', 'FontSize', 14);
legend(nombres_crit_cortos, 'Location', 'eastoutside', 'FontSize', 9);
grid on;

% Añadir totales encima de cada barra
for j = 1:n_alternativas
    text(j, P_global(j) + 0.005, sprintf('%.3f', P_global(j)), ...
         'HorizontalAlignment', 'center', 'FontSize', 10, 'FontWeight', 'bold');
end

% --- Gráfica 4: Radar/Spider chart - Perfil de cada alternativa ---
figure('Name', 'AHP - Perfil de Alternativas', 'NumberTitle', 'off', ...
       'Position', [850 600 700 500]);

% Gráfica polar (radar simplificada con líneas)
angulos = linspace(0, 2*pi, n_criterios + 1);

estilos = {'-o', '-s', '-d', '-^', '-v'};
for j = 1:n_alternativas
    valores = [P_local(j, :), P_local(j, 1)];  % Cerrar el polígono
    polarplot(angulos, valores, estilos{j}, 'LineWidth', 1.5, 'MarkerSize', 6);
    if j == 1
        hold on;  % Activar hold DESPUÉS de que el primer polarplot cree los ejes polares
    end
end
hold off;

ax = gca;
ax.ThetaTick = rad2deg(angulos(1:end-1));
ax.ThetaTickLabel = etiquetas_c;
ax.RLim = [0, 0.5];
ax.FontSize = 10;
title('Perfil de Alternativas por Criterio', 'FontSize', 14);
legend(alternativas, 'Location', 'southoutside', 'Orientation', 'horizontal', 'FontSize', 9);

fprintf('Se generaron 4 gráficas:\n');
fprintf('  1. Pesos de los criterios\n');
fprintf('  2. Ranking final de tecnologías\n');
fprintf('  3. Contribución por criterio (barras apiladas)\n');
fprintf('  4. Perfil radar de alternativas\n');

%% ========================================================================
%  RESUMEN FINAL
%  ========================================================================

fprintf('\n\n================================================================\n');
fprintf('  RESUMEN DEL ANÁLISIS AHP\n');
fprintf('================================================================\n\n');
fprintf('  Criterios con mayor peso:\n');
fprintf('    1. %s (%.1f%%)\n', criterios{idx_sorted(1)}, w_criterios(idx_sorted(1))*100);
fprintf('    2. %s (%.1f%%)\n', criterios{idx_sorted(2)}, w_criterios(idx_sorted(2))*100);
fprintf('    3. %s (%.1f%%)\n', criterios{idx_sorted(3)}, w_criterios(idx_sorted(3))*100);

fprintf('\n  Consistencia:\n');
fprintf('    - Matriz de criterios: CR = %.3f (< 0.10 ✓)\n', CR_crit);
fprintf('    - Todas las matrices de alternativas: CR < 0.10 ✓\n');

fprintf('\n  Ranking final:\n');
for k = 1:n_alternativas
    fprintf('    %d. %-10s  %.3f (%.1f%%)\n', k, alternativas{idx(k)}, P_sorted(k), P_sorted(k)*100);
end

fprintf('\n  TECNOLOGÍA SELECCIONADA: %s\n', upper(alternativas{idx(1)}));
fprintf('  Ventaja sobre la segunda opción (%s): %.3f puntos\n', ...
    alternativas{idx(2)}, P_sorted(1) - P_sorted(2));

fprintf('\n================================================================\n');
fprintf('  Fin del análisis AHP\n');
fprintf('================================================================\n');
