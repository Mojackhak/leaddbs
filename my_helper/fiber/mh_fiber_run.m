function result = mh_fiber_run(cfg)
% Run HybraPD ROI, VTA-hit, e-field peak, native back-write, reports, and figures.

if ~isfield(cfg, 'stimLabel') || strlength(string(cfg.stimLabel)) == 0
    error('mh_fiber_run:MissingStimLabel', 'cfg.stimLabel is required.');
end

dirs = mh_fiber_prepare_output_dirs(cfg);
vta = mh_fiber_vta_paths(cfg, []);
mh_fiber_validate_inputs(cfg, vta);

fprintf('Generating HybraPD ROI masks...\n');
rois = mh_fiber_make_hybrapd_rois(cfg, dirs);

fprintf('Writing contacts report...\n');
contacts = mh_fiber_write_contacts_report(cfg, dirs);

fprintf('Loading MNI fibers...\n');
ftrMni = mh_fiber_load_ftr(cfg.paths.mniFiber);
fprintf('Loading native fibers...\n');
ftrNative = mh_fiber_load_ftr(cfg.paths.nativeFiber);

if numel(ftrMni.idx) ~= numel(ftrNative.idx)
    error('mh_fiber_run:NativeMniIdxMismatch', ...
        'MNI and native FTR files have different fiber counts (%d vs %d).', ...
        numel(ftrMni.idx), numel(ftrNative.idx));
end

sides = {'R', 'L'};
result = struct();
result.cfg = cfg;
result.dirs = dirs;
result.vta = vta;
result.rois = rois;
result.contacts = contacts;
activationTables = cell(numel(sides), 1);

for s = 1:numel(sides)
    side = sides{s};
    fprintf('\nProcessing %s hemisphere...\n', side);

    ids = struct();
    ids.NAc_only = mh_fiber_select_by_mask(ftrMni, rois.(side).NAc);
    ids.ALIC_only = mh_fiber_select_by_mask(ftrMni, rois.(side).ALIC);
    ids.NAc_ALIC_intersection = intersect(ids.NAc_only, ids.ALIC_only);

    vtaStats = mh_fiber_select_vta_efield( ...
        ftrMni, vta.mni.(side).binaryNii, vta.mni.(side).efieldNii, ...
        cfg.activation.efieldThresholdVPerM);
    ids.VTA_hit = vtaStats.fiber_ids;
    ids.NAc_ALIC_VTA_hit = intersect(ids.NAc_ALIC_intersection, ids.VTA_hit);

    activationTables{s} = write_side_outputs(cfg, dirs, side, ftrMni, ftrNative, ids, vtaStats);
    result.(side).ids = ids;
    result.(side).vtaStats = vtaStats;
end

activationTable = vertcat(activationTables{:});
result.activationTable = activationTable;
result.activationCsv = fullfile(dirs.activation, 'efield_peak_all_vta_hit_fibers.csv');
writetable(activationTable, result.activationCsv);

result.summaryMd = fullfile(dirs.reports, 'fiber_vta_summary.md');
write_summary_markdown(result.summaryMd, cfg, result);

if isfield(cfg, 'seedTarget') && isfield(cfg.seedTarget, 'enabled') && cfg.seedTarget.enabled
    result.seedTarget = mh_fiber_run_seed_target(cfg, dirs, rois, vta);
end

if isfield(cfg, 'seedVtaSift2') && isfield(cfg.seedVtaSift2, 'enabled') && cfg.seedVtaSift2.enabled
    result.seedVtaSift2 = mh_fiber_run_seed_vta_sift2(cfg, dirs, vta);
end

fprintf('\nGenerating scene figure...\n');
result.figures = mh_fiber_make_scene(cfg, dirs, rois, vta);

fprintf('\nFiber/VTA visualization outputs written to:\n%s\n', dirs.root);
end

function activationTable = write_side_outputs(cfg, dirs, side, ftrMni, ftrNative, ids, vtaStats)
stageNames = {'NAc_only', 'ALIC_only', 'NAc_ALIC_intersection', 'VTA_hit', 'NAc_ALIC_VTA_hit'};

peakById = nan(ftrMni.fiberCount, 1);
flagById = false(ftrMni.fiberCount, 1);
peakById(vtaStats.fiber_ids) = vtaStats.efield_peak_v_per_m;
flagById(vtaStats.fiber_ids) = vtaStats.peak_ge_threshold;

for i = 1:numel(stageNames)
    stage = stageNames{i};
    selectedIds = ids.(stage);
    metadata = struct();
    if contains(stage, 'VTA')
        metadata.activation_definition = 'fiber intersects binary VTA; peak e-field sampled at intersecting VTA voxels';
        metadata.efield_threshold_v_per_m = cfg.activation.efieldThresholdVPerM;
        metadata.efield_peak_v_per_m = peakById(selectedIds);
        metadata.peak_ge_200_v_per_m = flagById(selectedIds);
    end

    mniSubset = mh_fiber_subset_ftr(ftrMni, selectedIds, metadata);
    nativeSubset = mh_fiber_subset_ftr(ftrNative, selectedIds, metadata);

    mniOut = fullfile(dirs.fibersMni, sprintf('%s_hemi-%s_%s.mat', cfg.patientName, side, stage));
    nativeOut = fullfile(dirs.fibersNative, sprintf('%s_hemi-%s_%s.mat', cfg.patientName, side, stage));
    mh_fiber_save_ftr(mniSubset, mniOut, cfg.paths.mniReference);
    mh_fiber_save_ftr(nativeSubset, nativeOut, cfg.paths.nativeReference);
end

hitNac = ismember(vtaStats.fiber_ids, ids.NAc_only);
hitAlic = ismember(vtaStats.fiber_ids, ids.ALIC_only);
hitNacAlic = ismember(vtaStats.fiber_ids, ids.NAc_ALIC_intersection);
activationTable = table( ...
    repmat({side}, numel(vtaStats.fiber_ids), 1), ...
    vtaStats.fiber_ids(:), ...
    vtaStats.efield_peak_v_per_m(:), ...
    vtaStats.peak_ge_threshold(:), ...
    hitNac(:), hitAlic(:), hitNacAlic(:), ...
    'VariableNames', {'side', 'original_fiber_id', 'efield_peak_v_per_m', ...
    'peak_ge_200_v_per_m', 'hit_NAc', 'hit_ALIC', 'hit_NAc_ALIC'});

sideCsv = fullfile(dirs.activation, sprintf('%s_hemi-%s_efield_peak.csv', cfg.patientName, side));
writetable(activationTable, sideCsv);
end

function write_summary_markdown(path, cfg, result)
fid = fopen(path, 'w');
if fid < 0
    error('mh_fiber_run:SummaryOpenFailed', 'Cannot write summary report: %s', path);
end
cleanup = onCleanup(@() fclose(fid));

fprintf(fid, '# Fiber/VTA Summary\n\n');
fprintf(fid, '- Subject: `%s`\n', cfg.patientName);
fprintf(fid, '- Stimulation label: `%s`\n', cfg.stimLabel);
fprintf(fid, '- Activation proxy: fiber intersects binary VTA; peak e-field sampled at intersecting VTA voxels.\n');
fprintf(fid, '- E-field threshold flag: `peak >= %.3f V/m`\n\n', cfg.activation.efieldThresholdVPerM);

fprintf(fid, '| Side | NAc | ALIC | NAc+ALIC | VTA-hit | NAc+ALIC+VTA | MNI VTA volume mm3 |\n');
fprintf(fid, '|---|---:|---:|---:|---:|---:|---:|\n');
for sideCell = {'R', 'L'}
    side = sideCell{1};
    ids = result.(side).ids;
    stats = result.(side).vtaStats;
    fprintf(fid, '| %s | %d | %d | %d | %d | %d | %.6f |\n', ...
        side, numel(ids.NAc_only), numel(ids.ALIC_only), ...
        numel(ids.NAc_ALIC_intersection), numel(ids.VTA_hit), ...
        numel(ids.NAc_ALIC_VTA_hit), stats.vta_volume_mm3);
end

fprintf(fid, '\n## Output folders\n\n');
fprintf(fid, '- ROIs: `%s`\n', result.dirs.rois);
fprintf(fid, '- MNI fibers: `%s`\n', result.dirs.fibersMni);
fprintf(fid, '- Native fibers: `%s`\n', result.dirs.fibersNative);
fprintf(fid, '- Activation tables: `%s`\n', result.dirs.activation);
fprintf(fid, '- Figures: `%s`\n', result.dirs.figures);
end
