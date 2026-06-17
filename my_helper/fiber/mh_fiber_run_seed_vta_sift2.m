function result = mh_fiber_run_seed_vta_sift2(cfg, dirs, vta)
% Run SIFT2-weighted seed-intersection-VTA target analysis.

if ~isfield(cfg, 'seedVtaSift2') || ~cfg.seedVtaSift2.enabled
    result = struct('enabled', false);
    return;
end

fprintf('\nRunning MRtrix3 SIFT2 seed-VTA-target analysis...\n');
result = struct();
result.enabled = true;
result.dirs = dirs.seedVtaSift2;

seedRois = make_required_rois(cfg, dirs);
mrtrix = prepare_mrtrix_workspace(cfg, dirs);
vtaDwi = prepare_dwi_stimulation_vta(cfg, dirs, vta);
[wholebrainTck, wholebrainWeights] = ensure_wholebrain_sift2(cfg, dirs, mrtrix);

rows = {};
seedResults = struct('side', {}, 'seedName', {}, 'targetResults', {});
sides = cellstr(string(cfg.seedVtaSift2.sides));
seedNames = cellstr(string(cfg.seedVtaSift2.seedNames));

for s = 1:numel(sides)
    side = sides{s};
    targetMasks = prepare_target_masks(cfg, mrtrix, seedRois, side);
    for seedIdx = 1:numel(seedNames)
        seedName = seedNames{seedIdx};
        if ~has_roi(seedRois.dwi, side, seedName)
            warning('mh_fiber_run_seed_vta_sift2:MissingSeed', ...
                'Missing seed ROI for %s %s; skipping.', side, seedName);
            continue;
        end

        seed = prepare_seed_vta_mask(cfg, dirs, mrtrix, seedRois, vtaDwi, side, seedName);
        seedResult = process_one_seed(cfg, dirs, mrtrix, side, seedName, seed, targetMasks, ...
            wholebrainTck, wholebrainWeights);
        rows = [rows; seedResult.rows]; %#ok<AGROW>
        seedResults(end+1) = struct( ...
            'side', side, ...
            'seedName', seedName, ...
            'targetResults', seedResult.targetResults); %#ok<AGROW>
    end
end

summary = cell2table(rows, 'VariableNames', summary_columns());
result.summaryTable = summary;
result.summaryCsv = fullfile(dirs.seedVtaSift2.reports, 'seed_vta_sift2_summary.csv');
writetable(summary, result.summaryCsv);
result.reportMd = fullfile(dirs.seedVtaSift2.reports, 'seed_vta_sift2_summary.md');
write_summary_markdown(result.reportMd, cfg, summary);

displayRows = write_display_outputs(cfg, dirs, seedResults);
if isempty(displayRows)
    display = cell2table(cell(0, numel(display_columns())), 'VariableNames', display_columns());
else
    display = cell2table(displayRows, 'VariableNames', display_columns());
end
result.displayTable = display;
result.displayCsv = fullfile(dirs.seedVtaSift2.reports, 'seed_vta_sift2_display.csv');
writetable(display, result.displayCsv);

if cfg.seedVtaSift2.writeScene
    result.figures = mh_fiber_make_seed_vta_sift2_scene(cfg, dirs, seedRois, vta, result);
end

result.rois = seedRois;
result.mrtrix = mrtrix;
result.vtaDwi = vtaDwi;
result.wholebrainTck = wholebrainTck;
result.wholebrainWeights = wholebrainWeights;

fprintf('Seed-VTA-SIFT2 outputs written to:\n%s\n', dirs.seedVtaSift2.root);
end

function seedRois = make_required_rois(cfg, dirs)
roiCfg = cfg;
if ~isfield(roiCfg, 'seedTarget')
    roiCfg.seedTarget = struct();
end
roiCfg.seedTarget.seedNames = unique([string(cfg.seedVtaSift2.seedNames(:)); string(cfg.seedVtaSift2.targetNames(:))], 'stable');
roiCfg.seedTarget.targetNames = roiCfg.seedTarget.seedNames;
seedRois = mh_fiber_make_seed_target_rois(roiCfg, dirs);
end

function mrtrix = prepare_mrtrix_workspace(cfg, dirs)
work = dirs.seedVtaSift2.work;
maskDir = fullfile(work, 'masks');
ea_mkdir(maskDir);

mrtrix = struct();
mrtrix.work = work;
mrtrix.maskDir = maskDir;
mrtrix.dwiMif = fullfile(work, 'dwi.mif');
mrtrix.brainMaskMif = fullfile(work, 'brainmask.mif');
mrtrix.trackingMaskMif = fullfile(work, 'trackingmask.mif');
mrtrix.responseWm = fullfile(work, 'response_wm.txt');
mrtrix.wmFod = fullfile(work, 'wm_fod.mif');
mrtrix.t1Dwi = fullfile(work, [cfg.patientName, '_T1w_space-dwi.nii']);
mrtrix.fiveTt = fullfile(work, '5tt.mif');

brainMask = resolve_dwi_grid_mask(cfg, cfg.paths.brainMask, cfg.paths.trackingMask, 'brain');
trackingMask = resolve_dwi_grid_mask(cfg, cfg.paths.trackingMask, '', 'tracking');

run_if_missing(cfg, mrtrix.dwiMif, sprintf('mrconvert %s %s -fslgrad %s %s -force', ...
    q(cfg.paths.dwi), q(mrtrix.dwiMif), q(cfg.paths.dwiBvec), q(cfg.paths.dwiBval)));
run_if_missing(cfg, mrtrix.brainMaskMif, sprintf('mrconvert %s %s -datatype bit -force', ...
    q(brainMask), q(mrtrix.brainMaskMif)));
run_if_missing(cfg, mrtrix.trackingMaskMif, sprintf('mrconvert %s %s -datatype bit -force', ...
    q(trackingMask), q(mrtrix.trackingMaskMif)));

seedTargetFod = fullfile(dirs.seedTarget.work, 'wm_fod.mif');
seedTargetResponse = fullfile(dirs.seedTarget.work, 'response_wm.txt');
if isfile(seedTargetFod) && ~isfile(mrtrix.wmFod)
    copyfile(seedTargetFod, mrtrix.wmFod);
end
if isfile(seedTargetResponse) && ~isfile(mrtrix.responseWm)
    copyfile(seedTargetResponse, mrtrix.responseWm);
end

if cfg.seedVtaSift2.force || ~isfile(mrtrix.responseWm)
    mh_fiber_mrtrix_run(cfg, sprintf('dwi2response tournier %s %s -mask %s -force', ...
        q(mrtrix.dwiMif), q(mrtrix.responseWm), q(mrtrix.brainMaskMif)));
end
if cfg.seedVtaSift2.force || ~isfile(mrtrix.wmFod)
    mh_fiber_mrtrix_run(cfg, sprintf('dwi2fod csd %s %s %s -mask %s -force', ...
        q(mrtrix.dwiMif), q(mrtrix.responseWm), q(mrtrix.wmFod), q(mrtrix.brainMaskMif)));
end

if cfg.seedVtaSift2.useAct
    if cfg.seedVtaSift2.force || cfg.seedVtaSift2.force5tt || ~isfile(mrtrix.t1Dwi)
        ea_ants_apply_transforms([], cfg.paths.nativeReference, mrtrix.t1Dwi, 0, cfg.paths.dwiB0, ...
            cfg.paths.anchorToDwiTransform, 'Linear');
    end
    if cfg.seedVtaSift2.force || cfg.seedVtaSift2.force5tt || ~isfile(mrtrix.fiveTt)
        mh_fiber_mrtrix_run(cfg, sprintf('5ttgen fsl %s %s -force', q(mrtrix.t1Dwi), q(mrtrix.fiveTt)));
    end
end
end

function vtaDwi = prepare_dwi_stimulation_vta(cfg, dirs, vta)
vtaDir = fullfile(dirs.seedVtaSift2.work, 'stimulation_vta_dwi');
ea_mkdir(vtaDir);
vtaDwi = struct();
for sideCell = {'R', 'L'}
    side = sideCell{1};
    binaryNii = fullfile(vtaDir, sprintf('%s_hemi-%s_stimulationVTA_space-dwi.nii', cfg.patientName, side));
    binaryMif = fullfile(vtaDir, sprintf('%s_hemi-%s_stimulationVTA_space-dwi.mif', cfg.patientName, side));
    if cfg.seedVtaSift2.force || ~isfile(binaryNii)
        ea_ants_apply_transforms([], vta.native.(side).binaryNii, binaryNii, 0, cfg.paths.dwiB0, ...
            cfg.paths.anchorToDwiTransform, 'GenericLabel');
        binarize_nii(binaryNii, 0.5);
    end
    run_if_missing(cfg, binaryMif, sprintf('mrconvert %s %s -datatype bit -force', q(binaryNii), q(binaryMif)));
    vtaDwi.(side).binaryNii = binaryNii;
    vtaDwi.(side).binaryMif = binaryMif;
end
end

function [wholebrainTck, wholebrainWeights] = ensure_wholebrain_sift2(cfg, dirs, mrtrix)
wholebrainTck = fullfile(dirs.seedVtaSift2.tracks, sprintf('%s_wholebrain_%d.tck', ...
    cfg.patientName, cfg.seedVtaSift2.wholebrainSelect));
wholebrainWeights = fullfile(dirs.seedVtaSift2.tracks, sprintf('%s_wholebrain_%d_sift2_weights.txt', ...
    cfg.patientName, cfg.seedVtaSift2.wholebrainSelect));

if cfg.seedVtaSift2.force || cfg.seedVtaSift2.forceWholebrain || ~isfile(wholebrainTck)
    if cfg.seedVtaSift2.useAct
        cmd = sprintf(['tckgen %s %s -algorithm iFOD2 -act %s -backtrack ', ...
            '-seed_dynamic %s -select %d -force'], ...
            q(mrtrix.wmFod), q(wholebrainTck), q(mrtrix.fiveTt), q(mrtrix.wmFod), ...
            cfg.seedVtaSift2.wholebrainSelect);
    else
        cmd = sprintf('tckgen %s %s -algorithm iFOD2 -seed_dynamic %s -select %d -force', ...
            q(mrtrix.wmFod), q(wholebrainTck), q(mrtrix.wmFod), cfg.seedVtaSift2.wholebrainSelect);
    end
    mh_fiber_mrtrix_run(cfg, cmd);
end

if cfg.seedVtaSift2.force || cfg.seedVtaSift2.forceSift2 || ~isfile(wholebrainWeights)
    if cfg.seedVtaSift2.useAct
        cmd = sprintf('tcksift2 %s %s %s -act %s -force', ...
            q(wholebrainTck), q(mrtrix.wmFod), q(wholebrainWeights), q(mrtrix.fiveTt));
    else
        cmd = sprintf('tcksift2 %s %s %s -force', ...
            q(wholebrainTck), q(mrtrix.wmFod), q(wholebrainWeights));
    end
    mh_fiber_mrtrix_run(cfg, cmd);
end
end

function targetMasks = prepare_target_masks(cfg, mrtrix, seedRois, side)
targetNames = cellstr(string(cfg.seedVtaSift2.targetNames));
targetMasks = struct('name', {}, 'nii', {}, 'mif', {}, 'voxels', {});
for i = 1:numel(targetNames)
    targetName = targetNames{i};
    if ~has_roi(seedRois.dwi, side, targetName)
        warning('mh_fiber_run_seed_vta_sift2:MissingTarget', ...
            'Missing target ROI for %s %s; skipping.', side, targetName);
        continue;
    end
    targetNii = seedRois.dwi.(side).(targetName);
    targetMif = fullfile(mrtrix.maskDir, sprintf('%s_hemi-%s_target-%s.mif', cfg.patientName, side, targetName));
    run_if_missing(cfg, targetMif, sprintf('mrconvert %s %s -datatype bit -force', q(targetNii), q(targetMif)));
    targetMasks(end+1) = struct( ...
        'name', targetName, ...
        'nii', targetNii, ...
        'mif', targetMif, ...
        'voxels', count_mif_voxels(cfg, targetMif)); %#ok<AGROW>
end
end

function seed = prepare_seed_vta_mask(cfg, dirs, mrtrix, seedRois, vtaDwi, side, seedName)
seedRoiNii = seedRois.dwi.(side).(seedName);
seedRoiMif = fullfile(mrtrix.maskDir, sprintf('%s_hemi-%s_seed-%s_exact.mif', cfg.patientName, side, seedName));
seedVtaMif = fullfile(mrtrix.maskDir, sprintf('%s_hemi-%s_seed-%s_intersect-stimulationVTA.mif', cfg.patientName, side, seedName));
seedVtaNii = fullfile(dirs.seedVtaSift2.work, sprintf('%s_hemi-%s_seed-%s_intersect-stimulationVTA_space-dwi.nii', cfg.patientName, side, seedName));
seedVtaAnchorNii = fullfile(dirs.seedVtaSift2.work, sprintf('%s_hemi-%s_seed-%s_intersect-stimulationVTA_space-anchorNative.nii', cfg.patientName, side, seedName));
seedVtaMniNii = fullfile(dirs.seedVtaSift2.work, sprintf('%s_hemi-%s_seed-%s_intersect-stimulationVTA_space-MNI152NLin2009bAsym.nii', cfg.patientName, side, seedName));

run_if_missing(cfg, seedRoiMif, sprintf('mrconvert %s %s -datatype bit -force', q(seedRoiNii), q(seedRoiMif)));
run_if_missing(cfg, seedVtaMif, sprintf('mrcalc %s %s -mult %s -datatype bit -force', ...
    q(seedRoiMif), q(vtaDwi.(side).binaryMif), q(seedVtaMif)));
run_if_missing(cfg, seedVtaNii, sprintf('mrconvert %s %s -datatype bit -force', q(seedVtaMif), q(seedVtaNii)));
if should_write_downstream(cfg, seedVtaAnchorNii)
    ea_ants_apply_transforms([], seedVtaNii, seedVtaAnchorNii, 0, cfg.paths.nativeReference, ...
        cfg.paths.dwiToAnchorTransform, 'GenericLabel');
    binarize_nii(seedVtaAnchorNii, 0.5);
end
if should_write_downstream(cfg, seedVtaMniNii)
    ea_ants_apply_transforms([], seedVtaAnchorNii, seedVtaMniNii, 0, cfg.paths.mniReference, ...
        cfg.paths.anchorToMniTransform, 'GenericLabel');
    binarize_nii(seedVtaMniNii, 0.5);
end

seed = struct();
seed.name = seedName;
seed.side = side;
seed.roiNii = seedRoiNii;
seed.roiMif = seedRoiMif;
seed.seedVtaMif = seedVtaMif;
seed.seedVtaNii = seedVtaNii;
seed.seedVtaAnchorNii = seedVtaAnchorNii;
seed.seedVtaMniNii = seedVtaMniNii;
seed.roiVoxels = count_mif_voxels(cfg, seedRoiMif);
seed.seedVtaVoxels = count_mif_voxels(cfg, seedVtaMif);
end

function seedResult = process_one_seed(cfg, dirs, mrtrix, side, seedName, seed, targetMasks, wholebrainTck, wholebrainWeights)
prefix = sprintf('%s_hemi-%s_seed-%s_intersect-stimulationVTA', cfg.patientName, side, seedName);
seedVtaTck = fullfile(dirs.seedVtaSift2.tracks, [prefix, '.tck']);
seedVtaWeights = fullfile(dirs.seedVtaSift2.tracks, [prefix, '_sift2_weights.txt']);

if seed.seedVtaVoxels == 0
    warning('mh_fiber_run_seed_vta_sift2:EmptySeedVta', ...
        '%s %s seed intersects zero stimulation VTA voxels.', side, seedName);
    mh_fiber_write_tck(seedVtaTck, {});
    write_weights(seedVtaWeights, zeros(0, 1));
else
    cmd = sprintf('tckedit %s %s -include %s -tck_weights_in %s -tck_weights_out %s -force', ...
        q(wholebrainTck), q(seedVtaTck), q(seed.seedVtaMif), q(wholebrainWeights), q(seedVtaWeights));
    run_if_missing(cfg, seedVtaTck, cmd);
end

tck = mh_fiber_load_tck(seedVtaTck, Inf, 1);
weights = read_weights(seedVtaWeights);
if numel(weights) ~= tck.streamlineCount
    error('mh_fiber_run_seed_vta_sift2:WeightCountMismatch', ...
        'Weight count does not match streamline count for %s (%d vs %d).', ...
        seedVtaTck, numel(weights), tck.streamlineCount);
end

classification = classify_streamlines_by_targets(tck, targetMasks);
targetResults = write_target_outputs(cfg, dirs, mrtrix, side, seedName, seed, tck, weights, targetMasks, classification);
rows = make_summary_rows(side, seedName, seed, tck, weights, targetMasks, classification, targetResults);

seedResult = struct();
seedResult.rows = rows;
seedResult.targetResults = targetResults;
end

function classification = classify_streamlines_by_targets(tck, targetMasks)
targetCount = numel(targetMasks);
hit = false(tck.streamlineCount, targetCount);
maskData = cell(targetCount, 1);
for j = 1:targetCount
    nii = ea_load_nii(targetMasks(j).nii);
    maskData{j} = struct('img', double(nii.img) ~= 0, 'mat', nii.mat, 'size', size(nii.img));
end

for i = 1:tck.streamlineCount
    points = tck.streamlines{i};
    if isempty(points)
        continue;
    end
    for j = 1:targetCount
        vox = round(ea_mm2vox(points, maskData{j}.mat));
        inside = vox(:, 1) >= 1 & vox(:, 1) <= maskData{j}.size(1) & ...
            vox(:, 2) >= 1 & vox(:, 2) <= maskData{j}.size(2) & ...
            vox(:, 3) >= 1 & vox(:, 3) <= maskData{j}.size(3);
        if ~any(inside)
            continue;
        end
        vox = vox(inside, :);
        ind = sub2ind(maskData{j}.size, vox(:, 1), vox(:, 2), vox(:, 3));
        hit(i, j) = any(maskData{j}.img(ind));
    end
end

classification.hit = hit;
classification.hitCount = sum(hit, 2);
classification.exclusiveTarget = zeros(tck.streamlineCount, 1);
for i = 1:tck.streamlineCount
    if classification.hitCount(i) == 1
        classification.exclusiveTarget(i) = find(hit(i, :), 1, 'first');
    end
end
classification.ambiguous = classification.hitCount > 1;
classification.noTarget = classification.hitCount == 0;
end

function targetResults = write_target_outputs(cfg, dirs, ~, side, seedName, ~, tck, weights, targetMasks, classification)
targetResults = struct('name', {}, 'indices', {}, 'streamlineCount', {}, 'weightSum', {}, ...
    'tck', {}, 'weights', {}, 'density', {}, 'relativeDensity', {}, 'nativeDisplayMat', {}, 'mniDisplayMat', {});

exclusiveWeightSum = 0;
for j = 1:numel(targetMasks)
    indices = find(classification.exclusiveTarget == j);
    targetName = targetMasks(j).name;
    targetPrefix = sprintf('%s_hemi-%s_seed-%sVTA_to-%s', cfg.patientName, side, seedName, targetName);
    targetTck = fullfile(dirs.seedVtaSift2.tracks, [targetPrefix, '.tck']);
    targetWeights = fullfile(dirs.seedVtaSift2.tracks, [targetPrefix, '_sift2_weights.txt']);
    density = fullfile(dirs.seedVtaSift2.density, [targetPrefix, '_density_sift2.nii']);
    relativeDensity = fullfile(dirs.seedVtaSift2.density, [targetPrefix, '_density_relative.nii']);
    nativeDisplayMat = fullfile(dirs.seedVtaSift2.display, [targetPrefix, '_space-anchorNative_display.mat']);
    mniDisplayMat = fullfile(dirs.seedVtaSift2.display, [targetPrefix, '_space-MNI152NLin2009bAsym_display.mat']);

    streamlines = tck.streamlines(indices);
    targetWeightValues = weights(indices);
    if should_write_downstream(cfg, targetTck)
        mh_fiber_write_tck(targetTck, streamlines);
    end
    if should_write_downstream(cfg, targetWeights)
        write_weights(targetWeights, targetWeightValues);
    end

    weightSum = sum(targetWeightValues, 'omitnan');
    exclusiveWeightSum = exclusiveWeightSum + weightSum;
    if cfg.seedVtaSift2.writeDensity
        if isempty(indices)
            write_zero_like(cfg.paths.dwiB0, density);
            write_zero_like(cfg.paths.dwiB0, relativeDensity);
        else
            if should_write_downstream(cfg, density)
                mh_fiber_mrtrix_run(cfg, sprintf('tckmap %s %s -template %s -precise -tck_weights_in %s -force', ...
                    q(targetTck), q(density), q(cfg.paths.dwiB0), q(targetWeights)));
            end
        end
    end

    targetResults(end+1) = struct( ...
        'name', targetName, ...
        'indices', indices, ...
        'streamlineCount', numel(indices), ...
        'weightSum', weightSum, ...
        'tck', targetTck, ...
        'weights', targetWeights, ...
        'density', density, ...
        'relativeDensity', relativeDensity, ...
        'nativeDisplayMat', nativeDisplayMat, ...
        'mniDisplayMat', mniDisplayMat); %#ok<AGROW>
end

for j = 1:numel(targetResults)
    if cfg.seedVtaSift2.writeDensity && targetResults(j).streamlineCount > 0
        if exclusiveWeightSum > 0
            if should_write_downstream(cfg, targetResults(j).relativeDensity)
                mh_fiber_mrtrix_run(cfg, sprintf('mrcalc %s %.17g -div %s -force', ...
                    q(targetResults(j).density), exclusiveWeightSum, q(targetResults(j).relativeDensity)));
            end
        else
            write_zero_like(cfg.paths.dwiB0, targetResults(j).relativeDensity);
        end
    end
end
end

function displayRows = write_display_outputs(cfg, dirs, seedResults)
displayRows = {};
items = flatten_display_items(seedResults);
if isempty(items)
    return;
end

budget = double(cfg.seedVtaSift2.displayBudget);
mode = display_budget_mode(cfg);

if strcmp(mode, 'per_seed')
    allocation = zeros(numel(items), 1);
    keys = strings(numel(items), 1);
    for i = 1:numel(items)
        keys(i) = string(items(i).side) + "|" + string(items(i).seedName);
    end
    uniqueKeys = unique(keys, 'stable');
    for k = 1:numel(uniqueKeys)
        group = find(keys == uniqueKeys(k));
        allocation(group) = allocate_display_counts([items(group).weightSum]', ...
            [items(group).streamlineCount]', budget);
    end
else
    allocation = allocate_display_counts([items.weightSum]', [items.streamlineCount]', budget);
end

for j = 1:numel(items)
    nDisplay = allocation(j);
    if nDisplay <= 0
        continue;
    end
    tck = mh_fiber_load_tck(items(j).tck, Inf, max(1, cfg.seedVtaSift2.displayPointStride));
    targetWeights = read_weights(items(j).weights);
    selected = mh_fiber_weighted_sample_indices(targetWeights, nDisplay, cfg.seedVtaSift2.randomSeed + j);
    selectedTck = fullfile(dirs.seedVtaSift2.display, sprintf('%s_hemi-%s_seed-%sVTA_to-%s_display.tck', ...
        cfg.patientName, items(j).side, items(j).seedName, items(j).name));
    mh_fiber_write_tck(selectedTck, tck.streamlines(selected));
    mh_fiber_tck_to_display_ftr(cfg, selectedTck, items(j).nativeDisplayMat, items(j).mniDisplayMat, ...
        nDisplay, cfg.seedVtaSift2.displayPointStride);
    try
        mh_fiber_write_ftr_vtk(items(j).nativeDisplayMat, replace_extension(items(j).nativeDisplayMat, '.vtk'));
        mh_fiber_write_ftr_vtk(items(j).mniDisplayMat, replace_extension(items(j).mniDisplayMat, '.vtk'));
    catch ME
        warning('mh_fiber_run_seed_vta_sift2:VtkFailed', 'Could not write display VTK: %s', ME.message);
    end

    displayRows(end+1, :) = {items(j).side, items(j).seedName, items(j).name, nDisplay, ...
        selectedTck, items(j).nativeDisplayMat, items(j).mniDisplayMat}; %#ok<AGROW>
end
end

function items = flatten_display_items(seedResults)
items = struct('side', {}, 'seedName', {}, 'name', {}, 'streamlineCount', {}, 'weightSum', {}, ...
    'tck', {}, 'weights', {}, 'nativeDisplayMat', {}, 'mniDisplayMat', {});
for i = 1:numel(seedResults)
    for j = 1:numel(seedResults(i).targetResults)
        target = seedResults(i).targetResults(j);
        if target.streamlineCount <= 0 || target.weightSum <= 0
            continue;
        end
        items(end+1) = struct( ...
            'side', seedResults(i).side, ...
            'seedName', seedResults(i).seedName, ...
            'name', target.name, ...
            'streamlineCount', target.streamlineCount, ...
            'weightSum', target.weightSum, ...
            'tck', target.tck, ...
            'weights', target.weights, ...
            'nativeDisplayMat', target.nativeDisplayMat, ...
            'mniDisplayMat', target.mniDisplayMat); %#ok<AGROW>
    end
end
end

function allocation = allocate_display_counts(weights, maxCounts, budget)
weights = double(weights(:));
maxCounts = double(maxCounts(:));
allocation = zeros(size(weights));
if budget <= 0 || isempty(weights) || sum(weights, 'omitnan') <= 0
    return;
end

capacity = max(0, floor(maxCounts));
targetBudget = min(round(budget), sum(capacity));
exact = targetBudget .* weights ./ sum(weights, 'omitnan');
allocation = min(floor(exact), capacity);

remaining = targetBudget - sum(allocation);
fractional = exact - floor(exact);
while remaining > 0
    candidates = find(allocation < capacity);
    if isempty(candidates)
        break;
    end
    [~, order] = sort(fractional(candidates), 'descend');
    candidates = candidates(order);
    for i = 1:numel(candidates)
        if remaining <= 0
            break;
        end
        idx = candidates(i);
        allocation(idx) = allocation(idx) + 1;
        remaining = remaining - 1;
    end
    fractional(:) = 0;
end
end

function mode = display_budget_mode(cfg)
mode = 'global';
if isfield(cfg.seedVtaSift2, 'displayBudgetMode') && strlength(string(cfg.seedVtaSift2.displayBudgetMode)) > 0
    mode = char(lower(string(cfg.seedVtaSift2.displayBudgetMode)));
end
if ~ismember(mode, {'global', 'per_seed'})
    error('mh_fiber_run_seed_vta_sift2:InvalidDisplayBudgetMode', ...
        'Unsupported cfg.seedVtaSift2.displayBudgetMode: %s', mode);
end
end

function rows = make_summary_rows(side, seedName, seed, tck, weights, targetMasks, classification, targetResults)
rows = {};
exclusiveTotalCount = nnz(classification.hitCount == 1);
exclusiveTotalWeight = 0;
for j = 1:numel(targetResults)
    exclusiveTotalWeight = exclusiveTotalWeight + targetResults(j).weightSum;
end
ambiguousCount = nnz(classification.ambiguous);
ambiguousWeight = sum(weights(classification.ambiguous), 'omitnan');
noTargetCount = nnz(classification.noTarget);
noTargetWeight = sum(weights(classification.noTarget), 'omitnan');
seedVtaCount = tck.streamlineCount;
seedVtaWeight = sum(weights, 'omitnan');

for j = 1:numel(targetResults)
    if exclusiveTotalWeight > 0
        fraction = targetResults(j).weightSum / exclusiveTotalWeight;
    else
        fraction = 0;
    end
    rows(end+1, :) = {side, seedName, targetResults(j).name, 'exclusive', ...
        seed.roiVoxels, seed.seedVtaVoxels, targetMasks(j).voxels, ...
        seedVtaCount, seedVtaWeight, targetResults(j).streamlineCount, targetResults(j).weightSum, fraction, ...
        exclusiveTotalCount, exclusiveTotalWeight, ambiguousCount, ambiguousWeight, noTargetCount, noTargetWeight, ...
        targetResults(j).tck, targetResults(j).weights, targetResults(j).density, targetResults(j).relativeDensity, ...
        targetResults(j).nativeDisplayMat, targetResults(j).mniDisplayMat}; %#ok<AGROW>
end
end

function columns = summary_columns()
columns = {'side', 'seed', 'target', 'assignment', ...
    'seed_roi_voxels', 'seed_vta_voxels', 'target_voxels', ...
    'seed_vta_streamline_count', 'seed_vta_weight_sum', ...
    'target_streamline_count', 'target_weight_sum', 'target_fraction', ...
    'exclusive_streamline_count', 'exclusive_weight_sum', ...
    'ambiguous_streamline_count', 'ambiguous_weight_sum', ...
    'no_target_streamline_count', 'no_target_weight_sum', ...
    'target_tck_path', 'target_weights_path', 'density_sift2_path', 'density_relative_path', ...
    'native_display_mat', 'mni_display_mat'};
end

function columns = display_columns()
columns = {'side', 'seed', 'target', 'display_streamline_count', ...
    'display_tck_path', 'native_display_mat', 'mni_display_mat'};
end

function write_summary_markdown(path, cfg, summary)
fid = fopen(path, 'w');
if fid < 0
    error('mh_fiber_run_seed_vta_sift2:ReportOpenFailed', 'Cannot write report: %s', path);
end
cleanup = onCleanup(@() fclose(fid));

fprintf(fid, '# Seed-VTA SIFT2 Summary\n\n');
fprintf(fid, '- Subject: `%s`\n', cfg.patientName);
fprintf(fid, '- Stimulation label: `%s`\n', cfg.stimLabel);
fprintf(fid, '- Seeds: `NAc ∩ stimulation VTA`, `ALIC ∩ stimulation VTA`.\n');
fprintf(fid, '- Whole-brain tractogram target: `%d` streamlines.\n', cfg.seedVtaSift2.wholebrainSelect);
fprintf(fid, '- Display budget: `%d` streamlines, mode `%s`.\n', ...
    cfg.seedVtaSift2.displayBudget, display_budget_mode(cfg));
fprintf(fid, '- Main metric: SIFT2 target weight fraction. Raw streamline counts are QC only.\n\n');

fprintf(fid, '| Side | Seed | Target | Seed-VTA voxels | Target count | Target weight | Target fraction | Ambiguous weight | No-target weight |\n');
fprintf(fid, '|---|---|---|---:|---:|---:|---:|---:|---:|\n');
for i = 1:height(summary)
    fprintf(fid, '| %s | %s | %s | %d | %d | %.9g | %.6f | %.9g | %.9g |\n', ...
        char(summary.side(i)), char(summary.seed(i)), char(summary.target(i)), ...
        summary.seed_vta_voxels(i), summary.target_streamline_count(i), ...
        summary.target_weight_sum(i), summary.target_fraction(i), ...
        summary.ambiguous_weight_sum(i), summary.no_target_weight_sum(i));
end
end

function maskPath = resolve_dwi_grid_mask(cfg, requestedMask, fallbackMask, role)
maskPath = requestedMask;
if mask_matches_dwi_grid(cfg.paths.dwi, requestedMask)
    return;
end
if strcmp(role, 'brain') && strlength(string(fallbackMask)) > 0 && mask_matches_dwi_grid(cfg.paths.dwi, fallbackMask)
    warning('mh_fiber_run_seed_vta_sift2:BrainMaskFallback', ...
        'Brain mask is not on the DWI grid. Using tracking mask for MRtrix response/FOD mask: %s', fallbackMask);
    maskPath = fallbackMask;
    return;
end
error('mh_fiber_run_seed_vta_sift2:MaskGridMismatch', ...
    'The %s mask is not on the DWI grid: %s', role, requestedMask);
end

function tf = mask_matches_dwi_grid(dwiPath, maskPath)
if ~isfile(maskPath)
    tf = false;
    return;
end
dwiInfo = niftiinfo(dwiPath);
maskInfo = niftiinfo(maskPath);
tf = isequal(dwiInfo.ImageSize(1:3), maskInfo.ImageSize(1:3));
end

function tf = has_roi(roiStruct, side, name)
tf = isfield(roiStruct, side) && isfield(roiStruct.(side), name) && isfile(roiStruct.(side).(name));
end

function run_if_missing(cfg, outputPath, command)
forceDownstream = isfield(cfg.seedVtaSift2, 'forceDownstream') && cfg.seedVtaSift2.forceDownstream;
if cfg.seedVtaSift2.force || forceDownstream || ~isfile(outputPath)
    mh_fiber_mrtrix_run(cfg, command);
end
end

function tf = should_write_downstream(cfg, outputPath)
forceDownstream = isfield(cfg.seedVtaSift2, 'forceDownstream') && cfg.seedVtaSift2.forceDownstream;
tf = cfg.seedVtaSift2.force || forceDownstream || ~isfile(outputPath);
end

function quoted = q(value)
quoted = mh_fiber_shell_quote(value);
end

function count = count_mif_voxels(cfg, path)
output = mh_fiber_mrtrix_run(cfg, sprintf('mrstats %s -output count -ignorezero', q(path)));
count = str2double(strtrim(output));
if ~isfinite(count)
    count = 0;
end
end

function weights = read_weights(path)
if ~isfile(path)
    weights = zeros(0, 1);
    return;
end
weights = readmatrix(path, 'FileType', 'text');
weights = double(weights(:));
weights(~isfinite(weights)) = 0;
end

function write_weights(path, weights)
ea_mkdir(fileparts(path));
writematrix(double(weights(:)), path, 'FileType', 'text');
end

function binarize_nii(path, threshold)
nii = ea_load_nii(path);
nii.img = double(nii.img > threshold);
nii.dt = 2;
nii.fname = path;
ea_write_nii(nii);
end

function write_zero_like(referencePath, outputPath)
ea_mkdir(fileparts(outputPath));
nii = ea_load_nii(referencePath);
nii.img = zeros(size(nii.img));
nii.dt = 16;
nii.fname = outputPath;
ea_write_nii(nii);
end

function out = replace_extension(path, ext)
[folder, name] = fileparts(path);
out = fullfile(folder, [name, ext]);
end
