function result = mh_fiber_run_seed_target(cfg, dirs, rois, vta)
% Run MRtrix3 iFOD2 NAc/ALIC seed-target tractography in DWI space.

if nargin < 3
    rois = [];
end
if nargin < 4
    vta = [];
end

if ~isfield(cfg, 'seedTarget') || ~cfg.seedTarget.enabled
    result = struct();
    result.enabled = false;
    return;
end

fprintf('\nRunning MRtrix3 seed-target tractography...\n');
result = struct();
result.enabled = true;
result.backend = cfg.seedTarget.backend;
result.dirs = dirs.seedTarget;
result.inputRois = rois;

seedRois = mh_fiber_make_seed_target_rois(cfg, dirs);
mrtrix = prepare_mrtrix_workspace(cfg, dirs);
vtaDwi = prepare_dwi_vta_efield(cfg, dirs, vta);

items = build_seed_target_items(cfg, dirs, mrtrix, seedRois);
bundles = run_seed_target_items(cfg, dirs, mrtrix, vtaDwi, items);
[summaryRows, hitRows] = collect_seed_target_rows(items, bundles);

summary = cell2table(summaryRows, 'VariableNames', summary_columns());
result.summaryTable = summary;
result.summaryCsv = fullfile(dirs.seedTarget.reports, 'seed_target_summary.csv');
writetable(summary, result.summaryCsv);

if isempty(hitRows)
    hitTable = cell2table(cell(0, numel(hit_columns())), 'VariableNames', hit_columns());
else
    hitTable = cell2table(hitRows, 'VariableNames', hit_columns());
end
result.hitTable = hitTable;
result.hitCsv = fullfile(dirs.seedTarget.reports, 'seed_target_vta_hit_streamlines.csv');
writetable(hitTable, result.hitCsv);

result.reportMd = fullfile(dirs.seedTarget.reports, 'seed_target_summary.md');
write_seed_target_markdown(result.reportMd, cfg, summary, seedRois);
result.rois = seedRois;
result.mrtrix = mrtrix;
result.vtaDwi = vtaDwi;

fprintf('Seed-target outputs written to:\n%s\n', dirs.seedTarget.root);
end

function items = build_seed_target_items(cfg, dirs, mrtrix, seedRois)
items = {};
taskIndex = 0;
sides = cellstr(string(get_seed_option(cfg, 'sides', {'R', 'L'})));
seedNames = cellstr(string(cfg.seedTarget.seedNames));
targetNames = cellstr(string(cfg.seedTarget.targetNames));
seedVariants = cellstr(string(cfg.seedTarget.seedVariants));

for s = 1:numel(sides)
    side = sides{s};
    for seedIdx = 1:numel(seedNames)
        seedName = seedNames{seedIdx};
        if ~has_roi(seedRois.dwi, side, seedName)
            warning('mh_fiber_run_seed_target:MissingSeedRoi', ...
                'Missing seed ROI for %s %s; skipping.', side, seedName);
            continue;
        end

        for variantIdx = 1:numel(seedVariants)
            seedVariant = seedVariants{variantIdx};
            seedMask = prepare_seed_mask(cfg, dirs, mrtrix, seedRois.dwi.(side).(seedName), ...
                side, seedName, seedVariant);
            seedVoxelCount = count_mif_voxels(cfg, seedMask);

            for targetIdx = 1:numel(targetNames)
                targetName = targetNames{targetIdx};
                if cfg.seedTarget.skipSelfTargets && strcmp(seedName, targetName)
                    items{end+1} = make_skip_item(side, seedName, seedVariant, targetName, ...
                        seedVoxelCount, 'skipped_self_target'); %#ok<AGROW>
                    continue;
                end
                if ~has_roi(seedRois.dwi, side, targetName)
                    items{end+1} = make_skip_item(side, seedName, seedVariant, targetName, ...
                        seedVoxelCount, 'missing_target_roi'); %#ok<AGROW>
                    continue;
                end

                targetMask = prepare_target_mask(cfg, dirs, mrtrix, seedRois.dwi.(side).(targetName), ...
                    side, targetName);
                targetVoxelCount = count_mif_voxels(cfg, targetMask);
                taskIndex = taskIndex + 1;
                items{end+1} = make_task_item(taskIndex, side, seedName, seedVariant, targetName, ...
                    seedMask, targetMask, seedVoxelCount, targetVoxelCount); %#ok<AGROW>
            end
        end
    end
end
end

function item = make_skip_item(side, seedName, seedVariant, targetName, seedVoxelCount, status)
item = struct();
item.kind = 'skip';
item.taskIndex = 0;
item.summaryRow = skipped_summary_row([], side, seedName, seedVariant, targetName, seedVoxelCount, status);
item.task = struct();
end

function item = make_task_item(taskIndex, side, seedName, seedVariant, targetName, ...
    seedMask, targetMask, seedVoxelCount, targetVoxelCount)
task = struct();
task.side = side;
task.seedName = seedName;
task.seedVariant = seedVariant;
task.targetName = targetName;
task.seedMask = seedMask;
task.targetMask = targetMask;
task.seedVoxelCount = seedVoxelCount;
task.targetVoxelCount = targetVoxelCount;

item = struct();
item.kind = 'task';
item.taskIndex = taskIndex;
item.summaryRow = {};
item.task = task;
end

function bundles = run_seed_target_items(cfg, dirs, mrtrix, vtaDwi, items)
tasks = collect_tasks(items);
taskCount = numel(tasks);
bundles = cell(taskCount, 1);
if taskCount == 0
    return;
end

[useParallel, workerCount] = should_run_parallel(cfg, taskCount);
if useParallel
    fprintf('Running %d seed-target bundle tasks with %d parallel workers...\n', taskCount, workerCount);
    parfor (taskIdx = 1:taskCount, workerCount)
        bundles{taskIdx} = run_seed_target_task(cfg, dirs, mrtrix, vtaDwi, tasks{taskIdx});
    end
else
    fprintf('Running %d seed-target bundle tasks sequentially...\n', taskCount);
    for taskIdx = 1:taskCount
        bundles{taskIdx} = run_seed_target_task(cfg, dirs, mrtrix, vtaDwi, tasks{taskIdx});
    end
end
end

function tasks = collect_tasks(items)
tasks = {};
for i = 1:numel(items)
    if strcmp(items{i}.kind, 'task')
        tasks{end+1} = items{i}.task; %#ok<AGROW>
    end
end
end

function bundle = run_seed_target_task(cfg, dirs, mrtrix, vtaDwi, task)
bundle = run_one_bundle(cfg, dirs, mrtrix, vtaDwi, task.side, task.seedName, task.seedVariant, ...
    task.targetName, task.seedMask, task.targetMask, task.seedVoxelCount, task.targetVoxelCount);
end

function [summaryRows, hitRows] = collect_seed_target_rows(items, bundles)
summaryRows = {};
hitRows = {};
for i = 1:numel(items)
    item = items{i};
    if strcmp(item.kind, 'skip')
        summaryRows(end+1, :) = item.summaryRow; %#ok<AGROW>
    else
        bundle = bundles{item.taskIndex};
        summaryRows(end+1, :) = bundle.summaryRow; %#ok<AGROW>
        hitRows = [hitRows; bundle.hitRows]; %#ok<AGROW>
    end
end
end

function [useParallel, workerCount] = should_run_parallel(cfg, taskCount)
workerCount = max(1, round(double(get_seed_option(cfg, 'parallelWorkers', 1))));
workerCount = min(workerCount, taskCount);
useParallel = logical(get_seed_option(cfg, 'parallel', false)) && workerCount > 1 && taskCount > 1;
if ~useParallel
    workerCount = 1;
    return;
end

if exist('parpool', 'file') ~= 2 || exist('gcp', 'file') ~= 2 || ...
        ~license('test', 'Distrib_Computing_Toolbox')
    warning('mh_fiber_run_seed_target:ParallelUnavailable', ...
        'Parallel Computing Toolbox is unavailable. Falling back to sequential seed-target tasks.');
    useParallel = false;
    workerCount = 1;
    return;
end

pool = gcp('nocreate');
if isempty(pool)
    parpool('local', workerCount);
else
    workerCount = min(workerCount, pool.NumWorkers);
end
end

function mrtrix = prepare_mrtrix_workspace(cfg, dirs)
work = dirs.seedTarget.work;
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
mrtrix.sourceBrainMask = resolve_dwi_grid_mask(cfg, cfg.paths.brainMask, cfg.paths.trackingMask, 'brain');
mrtrix.sourceTrackingMask = resolve_dwi_grid_mask(cfg, cfg.paths.trackingMask, '', 'tracking');

run_if_missing(cfg, mrtrix.dwiMif, sprintf('mrconvert %s %s -fslgrad %s %s -force', ...
    q(cfg.paths.dwi), q(mrtrix.dwiMif), q(cfg.paths.dwiBvec), q(cfg.paths.dwiBval)));
run_if_missing(cfg, mrtrix.brainMaskMif, sprintf('mrconvert %s %s -datatype bit -force', ...
    q(mrtrix.sourceBrainMask), q(mrtrix.brainMaskMif)));
run_if_missing(cfg, mrtrix.trackingMaskMif, sprintf('mrconvert %s %s -datatype bit -force', ...
    q(mrtrix.sourceTrackingMask), q(mrtrix.trackingMaskMif)));

if cfg.seedTarget.forceFod || ~isfile(mrtrix.responseWm)
    mh_fiber_mrtrix_run(cfg, sprintf('dwi2response tournier %s %s -mask %s -force', ...
        q(mrtrix.dwiMif), q(mrtrix.responseWm), q(mrtrix.brainMaskMif)));
end

function maskPath = resolve_dwi_grid_mask(cfg, requestedMask, fallbackMask, role)
maskPath = requestedMask;
if mask_matches_dwi_grid(cfg.paths.dwi, requestedMask)
    return;
end

if strcmp(role, 'brain') && get_seed_option(cfg, 'allowBrainMaskFallbackToTrackingMask', true) && ...
        strlength(string(fallbackMask)) > 0 && mask_matches_dwi_grid(cfg.paths.dwi, fallbackMask)
    warning('mh_fiber_run_seed_target:BrainMaskFallback', ...
        'Brain mask is not on the DWI grid. Using tracking mask for MRtrix response/FOD mask: %s', fallbackMask);
    maskPath = fallbackMask;
    return;
end

error('mh_fiber_run_seed_target:MaskGridMismatch', ...
    'The %s mask is not on the DWI grid: %s', role, requestedMask);
end

function tf = mask_matches_dwi_grid(dwiPath, maskPath)
if ~isfile(maskPath)
    tf = false;
    return;
end
dwiInfo = niftiinfo(dwiPath);
maskInfo = niftiinfo(maskPath);
dwiSize = double(dwiInfo.ImageSize(1:3));
maskSize = double(maskInfo.ImageSize(1:3));
tf = isequal(dwiSize, maskSize);
end
if cfg.seedTarget.forceFod || ~isfile(mrtrix.wmFod)
    mh_fiber_mrtrix_run(cfg, sprintf('dwi2fod csd %s %s %s -mask %s -force', ...
        q(mrtrix.dwiMif), q(mrtrix.responseWm), q(mrtrix.wmFod), q(mrtrix.brainMaskMif)));
end
end

function vtaDwi = prepare_dwi_vta_efield(cfg, dirs, vta)
if isempty(vta)
    vta = mh_fiber_vta_paths(cfg, []);
end

vtaDir = fullfile(dirs.seedTarget.qc, 'vta_efield_dwi');
ea_mkdir(vtaDir);
vtaDwi = struct();

for sideCell = {'R', 'L'}
    side = sideCell{1};
    binaryOut = fullfile(vtaDir, sprintf('%s_hemi-%s_sim-binary_space-dwi.nii', cfg.patientName, side));
    efieldOut = fullfile(vtaDir, sprintf('%s_hemi-%s_sim-efield_space-dwi.nii', cfg.patientName, side));
    binaryMif = fullfile(vtaDir, sprintf('%s_hemi-%s_sim-binary_space-dwi.mif', cfg.patientName, side));

    if cfg.seedTarget.force || ~isfile(binaryOut)
        ea_ants_apply_transforms([], vta.native.(side).binaryNii, binaryOut, 0, cfg.paths.dwiB0, ...
            cfg.paths.anchorToDwiTransform, 'GenericLabel');
        binarize_nii(binaryOut, 0.5);
    end
    if cfg.seedTarget.force || ~isfile(efieldOut)
        ea_ants_apply_transforms([], vta.native.(side).efieldNii, efieldOut, 0, cfg.paths.dwiB0, ...
            cfg.paths.anchorToDwiTransform, 'Linear');
    end
    run_if_missing(cfg, binaryMif, sprintf('mrconvert %s %s -datatype bit -force', q(binaryOut), q(binaryMif)));

    vtaDwi.(side).binaryNii = binaryOut;
    vtaDwi.(side).binaryMif = binaryMif;
    vtaDwi.(side).efieldNii = efieldOut;
end
end

function seedMask = prepare_seed_mask(cfg, ~, mrtrix, seedNii, side, seedName, variant)
base = sprintf('%s_hemi-%s_seed-%s_variant-%s', cfg.patientName, side, seedName, variant);
roiMif = fullfile(mrtrix.maskDir, [base, '_roi.mif']);
exactMif = fullfile(mrtrix.maskDir, [base, '_exact.mif']);
seedMask = fullfile(mrtrix.maskDir, [base, '.mif']);

run_if_missing(cfg, roiMif, sprintf('mrconvert %s %s -datatype bit -force', q(seedNii), q(roiMif)));
run_if_missing(cfg, exactMif, sprintf('mrcalc %s %s -mult %s -datatype bit -force', ...
    q(roiMif), q(mrtrix.brainMaskMif), q(exactMif)));

switch lower(variant)
    case 'exact'
        if cfg.seedTarget.force || ~isfile(seedMask)
            copyfile(exactMif, seedMask);
        end
    case 'interface'
        dilated = fullfile(mrtrix.maskDir, [base, '_dilated.mif']);
        if cfg.seedTarget.force || ~isfile(dilated)
            mh_fiber_mrtrix_run(cfg, sprintf('maskfilter %s dilate %s -npass %d -force', ...
                q(exactMif), q(dilated), cfg.seedTarget.interfaceDilatePasses));
        end
        run_if_missing(cfg, seedMask, sprintf('mrcalc %s %s -mult %s -datatype bit -force', ...
            q(dilated), q(mrtrix.trackingMaskMif), q(seedMask)));
    otherwise
        error('mh_fiber_run_seed_target:UnknownSeedVariant', 'Unknown seed variant: %s', variant);
end
end

function targetMask = prepare_target_mask(cfg, ~, mrtrix, targetNii, side, targetName)
base = sprintf('%s_hemi-%s_target-%s', cfg.patientName, side, targetName);
roiMif = fullfile(mrtrix.maskDir, [base, '_roi.mif']);
targetMask = fullfile(mrtrix.maskDir, [base, '.mif']);
run_if_missing(cfg, roiMif, sprintf('mrconvert %s %s -datatype bit -force', q(targetNii), q(roiMif)));
run_if_missing(cfg, targetMask, sprintf('mrcalc %s %s -mult %s -datatype bit -force', ...
    q(roiMif), q(mrtrix.brainMaskMif), q(targetMask)));
end

function bundle = run_one_bundle(cfg, dirs, mrtrix, vtaDwi, side, seedName, seedVariant, ...
    targetName, seedMask, targetMask, seedVoxelCount, targetVoxelCount)

name = sprintf('%s_hemi-%s_seed-%s_variant-%s_to-%s', ...
    cfg.patientName, side, seedName, seedVariant, targetName);
tckPath = fullfile(dirs.seedTarget.native, [name, '.tck']);
vtkPath = fullfile(dirs.seedTarget.native, [name, '.vtk']);
densityPath = fullfile(dirs.seedTarget.qc, [name, '_density.nii']);
nativeMatPath = fullfile(dirs.seedTarget.native, [name, '.mat']);
mniMatPath = fullfile(dirs.seedTarget.mni, [name, '.mat']);
seedVtaMask = fullfile(mrtrix.maskDir, [name, '_VTA_seed_mask.mif']);
seedHitName = [name, '_VTA_seed_hit'];
seedHitTckPath = fullfile(dirs.seedTarget.native, [seedHitName, '.tck']);
seedHitVtkPath = fullfile(dirs.seedTarget.native, [seedHitName, '.vtk']);
seedHitDensityPath = fullfile(dirs.seedTarget.qc, [seedHitName, '_density.nii']);
seedHitNativeMatPath = fullfile(dirs.seedTarget.native, [seedHitName, '.mat']);
seedHitMniMatPath = fullfile(dirs.seedTarget.mni, [seedHitName, '.mat']);

status = 'ok';
mainComplete = tract_output_complete(cfg, tckPath, nativeMatPath, mniMatPath);
if seedVoxelCount == 0
    status = 'empty_seed_mask';
    write_empty_tck(tckPath);
elseif targetVoxelCount == 0
    status = 'empty_target_mask';
    write_empty_tck(tckPath);
elseif should_run_tractography(cfg, tckPath, mainComplete)
    cmd = sprintf(['tckgen %s %s -algorithm iFOD2 -seed_image %s -include %s -mask %s ', ...
        '-select %d -seeds %d -cutoff %.6g -minlength %.6g -maxlength %.6g -nthreads %d -force'], ...
        q(mrtrix.wmFod), q(tckPath), q(seedMask), q(targetMask), q(mrtrix.trackingMaskMif), ...
        cfg.seedTarget.select, cfg.seedTarget.seeds, cfg.seedTarget.cutoff, ...
        cfg.seedTarget.minLength, cfg.seedTarget.maxLength, cfg.seedTarget.threads);
    mh_fiber_mrtrix_run(cfg, cmd);
end

if cfg.seedTarget.writeVtk && isfile(tckPath) && ~strcmp(status, 'empty_seed_mask') && ~strcmp(status, 'empty_target_mask')
    if cfg.seedTarget.force || ~isfile(vtkPath)
        mh_fiber_mrtrix_run(cfg, sprintf('tckconvert %s %s -force', q(tckPath), q(vtkPath)), true);
    end
end
if cfg.seedTarget.writeDensity && isfile(tckPath) && ~strcmp(status, 'empty_seed_mask') && ~strcmp(status, 'empty_target_mask')
    if cfg.seedTarget.force || ~isfile(densityPath)
        mh_fiber_mrtrix_run(cfg, sprintf('tckmap %s %s -template %s -force', ...
            q(tckPath), q(densityPath), q(cfg.paths.dwiB0)), true);
    end
end

displayInfo = mh_fiber_tck_to_display_ftr(cfg, tckPath, nativeMatPath, mniMatPath);
stats = mh_fiber_tck_vta_efield_stats(cfg, tckPath, vtaDwi.(side).binaryNii, vtaDwi.(side).efieldNii);
lengthStats = tck_length_stats(cfg, tckPath);
seedHit = run_seed_hit_bundle(cfg, mrtrix, seedMask, targetMask, vtaDwi.(side).binaryMif, ...
    seedVtaMask, seedHitTckPath, seedHitVtkPath, seedHitDensityPath, ...
    seedHitNativeMatPath, seedHitMniMatPath, seedVoxelCount, targetVoxelCount);

bundle.summaryRow = { ...
    side, seedName, seedVariant, targetName, status, ...
    seedVoxelCount, targetVoxelCount, stats.streamline_count, ...
    lengthStats.mean_mm, lengthStats.min_mm, lengthStats.max_mm, ...
    stats.vta_hit_count, stats.efield_peak_max_v_per_m, stats.efield_peak_mean_v_per_m, ...
    stats.peak_ge_threshold_count, seedHit.seed_vta_voxels, seedHit.streamline_count, ...
    tckPath, vtkPath, densityPath, nativeMatPath, mniMatPath, ...
    seedHitTckPath, seedHitVtkPath, seedHitDensityPath, seedHitNativeMatPath, seedHitMniMatPath};

hitIds = stats.hit_streamline_ids(:);
bundle.hitRows = cell(numel(hitIds), numel(hit_columns()));
for i = 1:numel(hitIds)
    streamlineId = hitIds(i);
    bundle.hitRows(i, :) = { ...
        side, seedName, seedVariant, targetName, 'VTA_exact_hit', streamlineId, ...
        stats.efield_peak_v_per_m(streamlineId), ...
        stats.peak_ge_threshold(streamlineId), tckPath};
end
bundle.display = displayInfo;
bundle.seedHit = seedHit;
end

function seedHit = run_seed_hit_bundle(cfg, mrtrix, seedMask, targetMask, vtaBinaryMif, seedVtaMask, ...
    tckPath, vtkPath, densityPath, nativeMatPath, mniMatPath, seedVoxelCount, targetVoxelCount)

seedHit = struct();
run_if_missing(cfg, seedVtaMask, sprintf('mrcalc %s %s -mult %s -datatype bit -force', ...
    q(seedMask), q(vtaBinaryMif), q(seedVtaMask)));
seedHit.seed_vta_voxels = count_mif_voxels(cfg, seedVtaMask);
seedHitComplete = tract_output_complete(cfg, tckPath, nativeMatPath, mniMatPath);

if seedVoxelCount == 0 || targetVoxelCount == 0 || seedHit.seed_vta_voxels == 0
    write_empty_tck(tckPath);
else
    if should_run_tractography(cfg, tckPath, seedHitComplete)
        cmd = sprintf(['tckgen %s %s -algorithm iFOD2 -seed_image %s -include %s -mask %s ', ...
            '-select %d -seeds %d -cutoff %.6g -minlength %.6g -maxlength %.6g -nthreads %d -force'], ...
            q(mrtrix.wmFod), q(tckPath), q(seedVtaMask), q(targetMask), q(mrtrix.trackingMaskMif), ...
            cfg.seedTarget.select, cfg.seedTarget.seeds, cfg.seedTarget.cutoff, ...
            cfg.seedTarget.minLength, cfg.seedTarget.maxLength, cfg.seedTarget.threads);
        mh_fiber_mrtrix_run(cfg, cmd);
    end
end

if cfg.seedTarget.writeVtk && isfile(tckPath) && seedHit.seed_vta_voxels > 0
    if cfg.seedTarget.force || ~isfile(vtkPath)
        mh_fiber_mrtrix_run(cfg, sprintf('tckconvert %s %s -force', q(tckPath), q(vtkPath)), true);
    end
end
if cfg.seedTarget.writeDensity && isfile(tckPath) && seedHit.seed_vta_voxels > 0
    if cfg.seedTarget.force || ~isfile(densityPath)
        mh_fiber_mrtrix_run(cfg, sprintf('tckmap %s %s -template %s -force', ...
            q(tckPath), q(densityPath), q(cfg.paths.dwiB0)), true);
    end
end

mh_fiber_tck_to_display_ftr(cfg, tckPath, nativeMatPath, mniMatPath);
seedHit.streamline_count = tck_count(tckPath);
seedHit.tck_path = tckPath;
seedHit.native_display_mat = nativeMatPath;
seedHit.mni_display_mat = mniMatPath;
end

function tf = should_run_tractography(cfg, tckPath, complete)
if cfg.seedTarget.force
    tf = true;
    return;
end
if logical(get_seed_option(cfg, 'resume', true))
    tf = ~complete;
else
    tf = ~isfile(tckPath);
end
end

function complete = tract_output_complete(cfg, tckPath, nativeMatPath, mniMatPath)
if ~isfile(tckPath) || ~isfile(nativeMatPath) || ~isfile(mniMatPath)
    complete = false;
    return;
end

if file_bytes(tckPath) < 256 || file_bytes(nativeMatPath) == 0 || file_bytes(mniMatPath) == 0
    complete = false;
    return;
end

try
    mh_fiber_load_tck(tckPath, 1, max(1, cfg.seedTarget.displayPointStride));
    nativeInfo = whos('-file', nativeMatPath);
    mniInfo = whos('-file', mniMatPath);
    complete = ~isempty(nativeInfo) && ~isempty(mniInfo);
catch
    complete = false;
end
end

function bytes = file_bytes(path)
info = dir(path);
if isempty(info)
    bytes = 0;
else
    bytes = info(1).bytes;
end
end

function row = skipped_summary_row(~, side, seedName, seedVariant, targetName, seedVoxelCount, status)
row = {side, seedName, seedVariant, targetName, status, seedVoxelCount, 0, 0, ...
    0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', '', '', '', '', '', '', '', ''};
end

function stats = tck_length_stats(~, tckPath)
stats = struct('mean_mm', 0, 'min_mm', 0, 'max_mm', 0);
if ~isfile(tckPath)
    return;
end
[~, outMean] = system(sprintf('tckstats %s -output mean', q(tckPath)));
[~, outMin] = system(sprintf('tckstats %s -output min', q(tckPath)));
[~, outMax] = system(sprintf('tckstats %s -output max', q(tckPath)));
stats.mean_mm = first_number(outMean);
stats.min_mm = first_number(outMin);
stats.max_mm = first_number(outMax);
if ~isfinite(stats.mean_mm), stats.mean_mm = 0; end
if ~isfinite(stats.min_mm), stats.min_mm = 0; end
if ~isfinite(stats.max_mm), stats.max_mm = 0; end
end

function count = tck_count(tckPath)
[status, out] = system(sprintf('tckstats %s -output count', q(tckPath)));
if status ~= 0
    count = 0;
    return;
end
count = first_number(out);
if ~isfinite(count)
    count = 0;
end
end

function value = first_number(text)
tokens = regexp(text, '[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', 'match', 'once');
if isempty(tokens)
    value = NaN;
else
    value = str2double(tokens);
end
end

function count = count_mif_voxels(~, maskMif)
[status, out] = system(sprintf('mrstats %s -mask %s -output count', q(maskMif), q(maskMif)));
if status ~= 0
    warning('mh_fiber_run_seed_target:MrstatsFailed', 'Could not count mask voxels: %s', maskMif);
    count = 0;
    return;
end
count = first_number(out);
if ~isfinite(count)
    count = 0;
end
end

function run_if_missing(cfg, outputPath, command)
if cfg.seedTarget.force || ~isfile(outputPath)
    mh_fiber_mrtrix_run(cfg, command);
end
end

function value = get_seed_option(cfg, fieldName, defaultValue)
if isfield(cfg, 'seedTarget') && isfield(cfg.seedTarget, fieldName)
    value = cfg.seedTarget.(fieldName);
else
    value = defaultValue;
end
end

function present = has_roi(roiStruct, side, roiName)
present = isfield(roiStruct, side) && isfield(roiStruct.(side), roiName) && isfile(roiStruct.(side).(roiName));
end

function binarize_nii(path, threshold)
nii = ea_load_nii(path);
nii.img = double(nii.img > threshold);
nii.dt = 2;
nii.fname = path;
ea_write_nii(nii);
end

function write_empty_tck(tckPath)
ea_mkdir(fileparts(tckPath));
offset = 256;
header = sprintf('mrtrix tracks\ncount: 0\ndatatype: Float32LE\nfile: . %d\nEND\n', offset);
padding = repmat(' ', 1, max(0, offset - numel(header)));
fid = fopen(tckPath, 'w', 'ieee-le');
if fid < 0
    error('mh_fiber_run_seed_target:EmptyTckOpenFailed', 'Cannot write empty TCK: %s', tckPath);
end
cleanup = onCleanup(@() fclose(fid));
fwrite(fid, [header, padding], 'char');
fwrite(fid, single([Inf, Inf, Inf]), 'float32');
end

function qpath = q(path)
qpath = mh_fiber_shell_quote(path);
end

function columns = summary_columns()
columns = {'side', 'seed', 'seed_variant', 'target', 'status', ...
    'seed_voxels', 'target_voxels', 'streamline_count', ...
    'length_mean_mm', 'length_min_mm', 'length_max_mm', ...
    'vta_exact_hit_count', 'efield_peak_max_v_per_m', 'efield_peak_mean_v_per_m', ...
    'peak_ge_200_v_per_m_count', 'vta_seed_mask_voxels', 'vta_seed_hit_count', ...
    'tck_path', 'vtk_path', 'density_path', 'native_display_mat', 'mni_display_mat', ...
    'vta_seed_hit_tck_path', 'vta_seed_hit_vtk_path', 'vta_seed_hit_density_path', ...
    'vta_seed_hit_native_display_mat', 'vta_seed_hit_mni_display_mat'};
end

function columns = hit_columns()
columns = {'side', 'seed', 'seed_variant', 'target', 'vta_hit_type', 'streamline_id', ...
    'efield_peak_v_per_m', 'peak_ge_200_v_per_m', 'tck_path'};
end

function write_seed_target_markdown(path, cfg, summary, seedRois)
fid = fopen(path, 'w');
if fid < 0
    error('mh_fiber_run_seed_target:ReportOpenFailed', 'Cannot write seed-target report: %s', path);
end
cleanup = onCleanup(@() fclose(fid));

fprintf(fid, '# MRtrix3 Seed-Target Summary\n\n');
fprintf(fid, '- Subject: `%s`\n', cfg.patientName);
fprintf(fid, '- Stimulation label: `%s`\n', cfg.stimLabel);
fprintf(fid, '- Backend: `%s`\n', cfg.seedTarget.backend);
fprintf(fid, '- Calculation space: native DWI/b0.\n');
fprintf(fid, '- Seed variants: `%s`\n', strjoin(cellstr(string(cfg.seedTarget.seedVariants)), '`, `'));
fprintf(fid, '- Exact FTR definitions are unchanged; seed-target streamlines are probabilistic tractography results.\n');
fprintf(fid, '- ROI QC report: `%s`\n\n', seedRois.reportMd);

fprintf(fid, '| Side | Seed | Variant | Target | Status | Streamlines | VTA exact-hit | VTA seed-hit | Peak max V/m | Peak >= 200 V/m |\n');
fprintf(fid, '|---|---|---|---|---|---:|---:|---:|---:|---:|\n');
for i = 1:height(summary)
    fprintf(fid, '| %s | %s | %s | %s | %s | %d | %d | %d | %.3f | %d |\n', ...
        summary.side{i}, summary.seed{i}, summary.seed_variant{i}, summary.target{i}, ...
        summary.status{i}, summary.streamline_count(i), summary.vta_exact_hit_count(i), ...
        summary.vta_seed_hit_count(i), summary.efield_peak_max_v_per_m(i), ...
        summary.peak_ge_200_v_per_m_count(i));
end
end
