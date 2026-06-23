function outputs = mh_fiber_plot_seed_vta_sift2_global_contribution(summaryCsv, outputDir)
% Plot global SIFT2-weighted seed-VTA-target pathway contributions.

if nargin < 1 || isempty(summaryCsv)
    summaryCsv = ['/Users/mojackhu/Desktop/ASD/derivatives/leaddbs/sub-001/connectomics/fiber_vis/', ...
        'clinical_twosource_L2R2_3V_L5to8R5to8_5V/seed_vta_sift2/reports/seed_vta_sift2_summary.csv'];
end

if nargin < 2 || isempty(outputDir)
    outputDir = fullfile(fileparts(fileparts(summaryCsv)), 'figures');
end

if ~isfile(summaryCsv)
    error('mh_fiber_plot_seed_vta_sift2_global_contribution:MissingSummary', ...
        'Cannot find seed-VTA-SIFT2 summary CSV: %s', summaryCsv);
end

if ~isfolder(outputDir)
    mkdir(outputDir);
end

outputs = struct();
outputs.pdf = fullfile(outputDir, 'seed_vta_sift2_global_contribution_barplot.pdf');
outputs.png = fullfile(outputDir, 'seed_vta_sift2_global_contribution_barplot.png');
outputs.methodsLegend = fullfile(outputDir, 'seed_vta_sift2_global_contribution_barplot_methods_legend.md');

summary = readtable(summaryCsv, ...
    'FileType', 'text', ...
    'Delimiter', ',', ...
    'ReadVariableNames', true, ...
    'TextType', 'string', ...
    'VariableNamingRule', 'preserve');
requiredColumns = ["side", "seed", "target", "assignment", "target_weight_sum"];
missingColumns = setdiff(requiredColumns, string(summary.Properties.VariableNames));
if ~isempty(missingColumns)
    error('mh_fiber_plot_seed_vta_sift2_global_contribution:MissingColumns', ...
        'Summary CSV is missing required columns: %s', strjoin(missingColumns, ', '));
end

summary = summary(summary.assignment == "exclusive", :);
summary = summary(~isnan(summary.target_weight_sum) & summary.target_weight_sum >= 0, :);
globalWeightSum = sum(summary.target_weight_sum);
if globalWeightSum <= 0
    error('mh_fiber_plot_seed_vta_sift2_global_contribution:EmptyWeights', ...
        'The exclusive target SIFT2 weight sum is zero.');
end

targetNames = ["mPFC", "OFC", "ACC", "amygdala", "hippocampus", "thalamus", "VTA"];
targetLabels = ["mPFC", "OFC", "ACC", "Amyg", "Hipp", "Thal", "VTA"];
seedNames = ["NAc", "ALIC"];
sideNames = ["L", "R"];
sideLabels = ["Left", "Right"];
seedColors = [hex2rgb('#82D143'); hex2rgb('#3070B7')];
stripColor = hex2rgb('#D7E3E0');

globalContribution = compute_contribution_array(summary, sideNames, seedNames, targetNames, globalWeightSum);
sumCheck = sum(globalContribution(:));
if abs(sumCheck - 100) > 1e-6
    warning('mh_fiber_plot_seed_vta_sift2_global_contribution:ContributionSum', ...
        'Global contributions sum to %.12f%% instead of 100%%.', sumCheck);
end

move_existing_to_trash(outputs.pdf);
move_existing_to_trash(outputs.png);
move_existing_to_trash(outputs.methodsLegend);

fig = make_bar_plot(globalContribution, sideLabels, seedNames, targetLabels, seedColors, stripColor);
exportgraphics(fig, outputs.pdf, 'ContentType', 'vector', 'BackgroundColor', 'white');
exportgraphics(fig, outputs.png, 'Resolution', 600, 'BackgroundColor', 'white');
close(fig);

write_methods_legend(outputs.methodsLegend, summaryCsv, globalWeightSum, globalContribution, ...
    sideNames, sideLabels, seedNames, targetNames, targetLabels);

fprintf('Seed-VTA-SIFT2 global contribution bar plot written to:\n');
fprintf('  %s\n', outputs.pdf);
fprintf('  %s\n', outputs.png);
fprintf('  %s\n', outputs.methodsLegend);
fprintf('Global contribution sum: %.6f%%\n', sumCheck);
end

function values = compute_contribution_array(summary, sideNames, seedNames, targetNames, globalWeightSum)
values = zeros(numel(sideNames), numel(seedNames), numel(targetNames));
for sideIdx = 1:numel(sideNames)
    for seedIdx = 1:numel(seedNames)
        for targetIdx = 1:numel(targetNames)
            isPathway = summary.side == sideNames(sideIdx) & ...
                summary.seed == seedNames(seedIdx) & ...
                summary.target == targetNames(targetIdx);
            values(sideIdx, seedIdx, targetIdx) = 100 * sum(summary.target_weight_sum(isPathway)) / globalWeightSum;
        end
    end
end
end

function fig = make_bar_plot(values, sideLabels, seedNames, targetLabels, seedColors, stripColor)
fig = figure('Color', 'w', ...
    'Units', 'centimeters', ...
    'Position', [2, 2, 12.0, 6.0], ...
    'Renderer', 'painters', ...
    'Visible', 'off');

yMax = max(values(:));
yMax = max(5, ceil((yMax * 1.18) / 5) * 5);
barWidth = 0.32;
offsets = [-0.18, 0.18];

panelPositions = [0.145, 0.235, 0.355, 0.535; ...
                  0.585, 0.235, 0.355, 0.535];
stripHeight = 0.105;
stripGap = 0.02;

for sideIdx = 1:numel(sideLabels)
    ax = axes('Parent', fig, 'Position', panelPositions(sideIdx, :));
    hold(ax, 'on');

    x = 1:numel(targetLabels);
    for seedIdx = 1:numel(seedNames)
        y = squeeze(values(sideIdx, seedIdx, :))';
        h = bar(ax, x + offsets(seedIdx), y, barWidth, ...
            'FaceColor', seedColors(seedIdx, :), ...
            'EdgeColor', 'none');
        h.Annotation.LegendInformation.IconDisplayStyle = 'off';
    end

    set(ax, ...
        'Box', 'off', ...
        'TickDir', 'out', ...
        'LineWidth', 0.9, ...
        'FontName', 'Arial', ...
        'FontSize', 7, ...
        'XLim', [0.5, numel(targetLabels) + 0.5], ...
        'YLim', [0, yMax], ...
        'XTick', x, ...
        'XTickLabel', targetLabels, ...
        'YTick', 0:5:yMax);
    ax.XAxis.TickLength = [0, 0];
    ax.YAxis.TickLength = [0.018, 0.018];
    ax.XColor = 'k';
    ax.YColor = 'k';
    grid(ax, 'off');

    if sideIdx == 1
        ylabel(ax, 'Global SIFT2-weighted contribution (%)', ...
            'FontName', 'Arial', 'FontSize', 7);
    else
        ax.YTickLabel = [];
    end
    xlabel(ax, 'Target', 'FontName', 'Arial', 'FontSize', 7);

    stripPosition = panelPositions(sideIdx, :);
    stripPosition(2) = panelPositions(sideIdx, 2) + panelPositions(sideIdx, 4) + stripGap;
    stripPosition(4) = stripHeight;
    stripAx = axes('Parent', fig, 'Position', stripPosition);
    set(stripAx, 'Color', stripColor, 'XTick', [], 'YTick', [], ...
        'XColor', 'none', 'YColor', 'none', 'Box', 'off');
    text(stripAx, 0.5, 0.5, sideLabels(sideIdx), ...
        'HorizontalAlignment', 'center', ...
        'VerticalAlignment', 'middle', ...
        'FontName', 'Arial', ...
        'FontSize', 8, ...
        'FontWeight', 'bold', ...
        'Color', 'k');
    axis(stripAx, [0, 1, 0, 1]);
end

add_manual_legend(fig, seedNames, seedColors);
end

function add_manual_legend(fig, seedNames, seedColors)
legendAx = axes('Parent', fig, 'Position', [0.60, 0.92, 0.34, 0.055]);
hold(legendAx, 'on');
axis(legendAx, [0, 1, 0, 1]);
axis(legendAx, 'off');

labels = seedNames;
xStart = [0.00, 0.48];
for i = 1:numel(seedNames)
    rectangle(legendAx, 'Position', [xStart(i), 0.27, 0.10, 0.46], ...
        'FaceColor', seedColors(i, :), ...
        'EdgeColor', 'none');
    text(legendAx, xStart(i) + 0.125, 0.5, labels(i), ...
        'HorizontalAlignment', 'left', ...
        'VerticalAlignment', 'middle', ...
        'FontName', 'Arial', ...
        'FontSize', 7, ...
        'Color', 'k');
end
end

function write_methods_legend(outPath, summaryCsv, globalWeightSum, values, sideNames, sideLabels, ...
    seedNames, targetNames, targetLabels)
fid = fopen(outPath, 'w');
if fid == -1
    error('mh_fiber_plot_seed_vta_sift2_global_contribution:CannotWriteMd', ...
        'Cannot write methods/legend file: %s', outPath);
end
cleaner = onCleanup(@() fclose(fid));

fprintf(fid, '# Seed-VTA-SIFT2 Global Contribution Bar Plot\n\n');
fprintf(fid, 'Source table: `%s`\n\n', summaryCsv);
fprintf(fid, 'Exclusive target SIFT2 weight denominator: `%.12f`.\n\n', globalWeightSum);

fprintf(fid, '## Methods Update\n\n');
fprintf(fid, ['For the bar-plot summary, each exclusive seed-stimulation-VTA-to-target ', ...
    'pathway was quantified as the SIFT2 weight sum for that pathway divided by ', ...
    'the total SIFT2 weight sum across all exclusive pathways from both hemispheres, ', ...
    'both seed regions, and all targets. The resulting global contribution values ', ...
    'were multiplied by 100 and plotted as percentages. Ambiguous streamlines and ', ...
    'streamlines without a target assignment were reported separately in the seed-VTA-SIFT2 ', ...
    'summary table and were not included in the global-contribution denominator. This ', ...
    'bar-plot metric is distinct from the seed-normalized `target_fraction` column and ', ...
    'from the fixed-budget 3D streamline display counts.\n\n']);
fprintf(fid, ['SIFT2-weighted streamline contribution was used as a tractography-derived ', ...
    'connectivity measure and should not be interpreted as a true axon count.\n\n']);

fprintf(fid, '## Figure Legend\n\n');
fprintf(fid, ['Global SIFT2-weighted contributions of stimulation-covered NAc and ALIC ', ...
    'pathways. Left and right hemisphere results are shown in separate panels. Within ', ...
    'each panel, bars are grouped by target region and colored by seed region. The plot ', ...
    'legend is labeled NAc and ALIC for readability; these labels refer to stimulation-VTA-intersecting ', ...
    'seed pathways, with NAc in green (`#82D143`) and ALIC in blue (`#3070B7`). Bar height ', ...
    'indicates the pathway SIFT2 weight sum divided by the total SIFT2 weight sum across ', ...
    'all exclusive side x seed x target pathways, so all bars across the full figure sum ', ...
    'to 100%%. The plot therefore represents global pathway contribution rather than ', ...
    'seed-normalized target fraction. Streamline-based measures are tractography estimates ', ...
    'and do not represent the number of anatomical axons.\n\n']);
fprintf(fid, ['Abbreviations: ACC, anterior cingulate cortex; ALIC, anterior limb of the ', ...
    'internal capsule; Amyg, amygdala; Hipp, hippocampus; mPFC, medial prefrontal cortex; ', ...
    'NAc, nucleus accumbens; OFC, orbitofrontal cortex; Thal, thalamus; VTA, ventral ', ...
    'tegmental area.\n\n']);

fprintf(fid, '## Chinese Note\n\n');
fprintf(fid, ['该柱状图的分母是所有左/右侧、NAc/ALIC seed、全部 target 的 exclusive pathway ', ...
    'SIFT2 weight sum，因此整张图所有柱子相加为 100%%。它不是每个 seed 内部归一化的 ', ...
    '`target_fraction`，也不是 3D figure 中按固定预算抽样后显示的 streamline 条数。', ...
    'SIFT2-weighted contribution 是 tractography-derived connectivity 指标，不应解释为真实轴突数量。\n\n']);

fprintf(fid, '## Values\n\n');
fprintf(fid, '| Side | Seed | Target | Global contribution (%%) |\n');
fprintf(fid, '|---|---|---:|---:|\n');
for sideIdx = 1:numel(sideNames)
    for seedIdx = 1:numel(seedNames)
        for targetIdx = 1:numel(targetNames)
            fprintf(fid, '| %s | %s | %s | %.6f |\n', ...
                sideLabels(sideIdx), seedNames(seedIdx), targetLabels(targetIdx), ...
                values(sideIdx, seedIdx, targetIdx));
        end
    end
end
end

function rgb = hex2rgb(hex)
hex = char(erase(string(hex), '#'));
rgb = reshape(sscanf(hex, '%2x'), 1, 3) / 255;
end

function move_existing_to_trash(path)
if ~isfile(path)
    return;
end

trashDir = fullfile(getenv('HOME'), '.Trash');
if ~isfolder(trashDir)
    trashDir = fileparts(path);
end

[~, name, ext] = fileparts(path);
stamp = char(datetime('now', 'Format', 'yyyyMMdd_HHmmssSSS'));
trashPath = fullfile(trashDir, sprintf('%s_%s%s', name, stamp, ext));
movefile(path, trashPath);
end
