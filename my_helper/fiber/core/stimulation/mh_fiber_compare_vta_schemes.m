function comparison = mh_fiber_compare_vta_schemes(subjectDir, labelA, labelB, varargin)
% Compare two Fiber/VTA visualization schemes for one subject.

parser = inputParser;
parser.FunctionName = 'mh_fiber_compare_vta_schemes';
addParameter(parser, 'OutputName', 'two_scheme_comparison', @(x) ischar(x) || isstring(x));
parse(parser, varargin{:});
outputName = char(string(parser.Results.OutputName));

cfgA = mh_fiber_default_config(subjectDir, labelA);
cfgB = mh_fiber_default_config(subjectDir, labelB);
vtaA = mh_fiber_vta_paths(cfgA, []);
vtaB = mh_fiber_vta_paths(cfgB, []);

outDir = fullfile(cfgA.outputRoot, outputName);
mh_util_make_dir(outDir);

sides = {'R', 'L'};
rows = {};
for i = 1:numel(sides)
    side = sides{i};
    sideA = vtaA.mni.(side);
    sideB = vtaB.mni.(side);
    diceStats = dice_binary_nii(sideA.binaryNii, sideB.binaryNii);
    volumeA = mh_vta_read_vat_volume(sideA.binaryMat);
    volumeB = mh_vta_read_vat_volume(sideB.binaryMat);
    activationA = read_activation(cfgA, side);
    activationB = read_activation(cfgB, side);

    rows(end+1, :) = {side, volumeA, volumeB, diceStats.dice, ...
        diceStats.intersection_voxels, diceStats.a_voxels, diceStats.b_voxels, ...
        activationA.vta_hit_count, activationB.vta_hit_count, ...
        activationA.nac_alic_vta_hit_count, activationB.nac_alic_vta_hit_count, ...
        activationA.efield_peak_max, activationB.efield_peak_max, ...
        activationA.efield_peak_median, activationB.efield_peak_median}; %#ok<AGROW>
end

comparisonVars = { ...
    'side', ...
    'mni_vta_volume_a_mm3', 'mni_vta_volume_b_mm3', 'mni_binary_dice', ...
    'mni_intersection_voxels', 'mni_a_voxels', 'mni_b_voxels', ...
    'vta_hit_fibers_a', 'vta_hit_fibers_b', ...
    'nac_alic_vta_hit_fibers_a', 'nac_alic_vta_hit_fibers_b', ...
    'efield_peak_max_a', 'efield_peak_max_b', ...
    'efield_peak_median_a', 'efield_peak_median_b'};
comparison = mh_util_cell_rows_to_table(rows, comparisonVars);

csvPath = fullfile(outDir, 'scheme_comparison.csv');
mdPath = fullfile(outDir, 'scheme_comparison.md');
writetable(comparison, csvPath);
write_markdown(mdPath, labelA, labelB, comparison);

fprintf('Wrote VTA scheme comparison:\n%s\n%s\n', csvPath, mdPath);
end

function stats = dice_binary_nii(pathA, pathB)
niiA = ea_load_nii(pathA);
pathBToLoad = pathB;
tmpPath = '';
if ~isequal(size(niiA.img), size(ea_load_nii(pathB).img)) || ...
        ~isequal(round(niiA.mat, 8), round(ea_load_nii(pathB).mat, 8))
    tmpPath = fullfile(tempdir, ['mh_fiber_dice_', char(java.util.UUID.randomUUID), '.nii']);
    copyfile(pathB, tmpPath);
    ea_conformspaceto(pathA, tmpPath, 0);
    pathBToLoad = tmpPath;
end

niiB = ea_load_nii(pathBToLoad);
a = niiA.img > 0;
b = niiB.img > 0;
inter = nnz(a & b);
denom = nnz(a) + nnz(b);
if denom == 0
    dice = NaN;
else
    dice = 2 * inter / denom;
end

stats = struct();
stats.dice = dice;
stats.intersection_voxels = inter;
stats.a_voxels = nnz(a);
stats.b_voxels = nnz(b);

if ~isempty(tmpPath) && isfile(tmpPath)
    delete(tmpPath);
end
end

function stats = read_activation(cfg, side)
csvPath = fullfile(cfg.outputDir, 'activation', sprintf('%s_hemi-%s_efield_peak.csv', cfg.patientName, side));
stats = struct( ...
    'vta_hit_count', 0, ...
    'nac_alic_vta_hit_count', 0, ...
    'efield_peak_max', NaN, ...
    'efield_peak_median', NaN);
if ~isfile(csvPath)
    return;
end
tbl = readtable(csvPath);
stats.vta_hit_count = height(tbl);
if ismember('hit_NAc_ALIC', tbl.Properties.VariableNames)
    stats.nac_alic_vta_hit_count = sum(tbl.hit_NAc_ALIC);
end
if height(tbl) > 0 && ismember('efield_peak_v_per_m', tbl.Properties.VariableNames)
    stats.efield_peak_max = max(tbl.efield_peak_v_per_m);
    stats.efield_peak_median = median(tbl.efield_peak_v_per_m);
end
end

function write_markdown(path, labelA, labelB, comparison)
fid = fopen(path, 'w');
if fid < 0
    error('mh_fiber_compare_vta_schemes:ReportOpenFailed', ...
        'Cannot write comparison report: %s', path);
end
cleanup = onCleanup(@() fclose(fid));

fprintf(fid, '# Two-Scheme VTA/Fiber Comparison\n\n');
fprintf(fid, '- Scheme A: `%s`\n', labelA);
fprintf(fid, '- Scheme B: `%s`\n\n', labelB);
fprintf(fid, '| Side | VTA A mm3 | VTA B mm3 | Dice | VTA-hit A | VTA-hit B | NAc-ALIC-VTA A | NAc-ALIC-VTA B | Peak max A | Peak max B |\n');
fprintf(fid, '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n');
for i = 1:height(comparison)
    fprintf(fid, '| %s | %.3f | %.3f | %.4f | %d | %d | %d | %d | %.3f | %.3f |\n', ...
        comparison.side{i}, ...
        comparison.mni_vta_volume_a_mm3(i), comparison.mni_vta_volume_b_mm3(i), ...
        comparison.mni_binary_dice(i), ...
        comparison.vta_hit_fibers_a(i), comparison.vta_hit_fibers_b(i), ...
        comparison.nac_alic_vta_hit_fibers_a(i), comparison.nac_alic_vta_hit_fibers_b(i), ...
        comparison.efield_peak_max_a(i), comparison.efield_peak_max_b(i));
end
end
