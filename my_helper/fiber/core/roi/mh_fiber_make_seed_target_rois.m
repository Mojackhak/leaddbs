function seedRois = mh_fiber_make_seed_target_rois(cfg, dirs)
% Generate MNI, anchorNative, and DWI-space ROIs for MRtrix seed-target tracking.

specs = mh_fiber_seed_target_roi_specs(cfg);
specs = filter_requested_specs(cfg, specs);
options = lead_options(cfg);
seedRois = struct();
reportRows = {};

for i = 1:numel(specs)
    spec = specs(i);
    labelNii = ea_load_nii(spec.atlas.nii);
    labelNames = read_label_names(spec.atlas.txt);
    mask = ismember(round(double(labelNii.img)), spec.labelIds);

    if ~any(mask(:))
        error('mh_fiber_make_seed_target_rois:EmptyMniRoi', ...
            'Atlas ROI is empty: %s %s labels %s', spec.side, spec.roi, mat2str(spec.labelIds));
    end

    centroidMni = mask_centroid_mm(mask, labelNii.mat);
    spatialSide = side_from_x(centroidMni(1), spec.side);
    sideWarning = "";
    if ~strcmp(spatialSide, spec.side)
        sideWarning = sprintf('Requested side %s conflicts with MNI centroid x=%.3f; output assigned to spatial side %s.', ...
            spec.side, centroidMni(1), spatialSide);
        warning('mh_fiber_make_seed_target_rois:SideMismatch', '%s %s: %s', ...
            spec.side, spec.roi, sideWarning);
    end

    labelToken = join(string(spec.labelIds), '_');
    basename = sprintf('%s_%s_%s_labels-%s', atlas_token(spec.atlas.name), spec.roi, spatialSide, labelToken);
    mniPath = fullfile(dirs.seedTarget.rois, [basename, '_space-MNI152NLin2009bAsym.nii']);
    anchorPath = fullfile(dirs.seedTarget.rois, [basename, '_space-anchorNative.nii']);
    dwiPath = fullfile(dirs.seedTarget.rois, [basename, '_space-dwi.nii']);

    out = labelNii;
    out.img = double(mask);
    out.dt = 2;
    out.fname = mniPath;
    if should_write_roi(cfg, mniPath)
        ea_write_nii(out);
    end

    if should_write_roi(cfg, anchorPath)
        ea_apply_normalization_tofile(options, mniPath, anchorPath, 1, 'GenericLabel', cfg.paths.nativeReference);
        binarize_nii(anchorPath, 0.5);
    end

    if should_write_roi(cfg, dwiPath)
        ea_ants_apply_transforms([], anchorPath, dwiPath, 0, cfg.paths.dwiB0, ...
            cfg.paths.anchorToDwiTransform, 'GenericLabel');
        binarize_nii(dwiPath, 0.5);
    end

    dwiNii = ea_load_nii(dwiPath);
    dwiMask = double(dwiNii.img) ~= 0;
    dwiCentroid = mask_centroid_mm(dwiMask, dwiNii.mat);
    labelNameText = label_names_for_ids(labelNames, spec.labelIds);

    seedRois.mni.(spatialSide).(spec.roi) = mniPath;
    seedRois.anchorNative.(spatialSide).(spec.roi) = anchorPath;
    seedRois.dwi.(spatialSide).(spec.roi) = dwiPath;
    seedRois.spec.(spatialSide).(spec.roi) = spec;

    reportRows(end+1, :) = { ...
        spec.side, spatialSide, spec.roi, spec.atlas.name, ...
        strjoin(cellstr(string(spec.labelIds)), '+'), char(labelNameText), ...
        nnz(mask), nnz(dwiMask), centroidMni(1), centroidMni(2), centroidMni(3), ...
        dwiCentroid(1), dwiCentroid(2), dwiCentroid(3), char(sideWarning), spec.note}; %#ok<AGROW>
end

report = cell2table(reportRows, 'VariableNames', { ...
    'requested_side', 'spatial_side', 'roi', 'atlas', 'label_ids', 'label_names', ...
    'mni_voxels', 'dwi_voxels', 'mni_centroid_x', 'mni_centroid_y', 'mni_centroid_z', ...
    'dwi_centroid_x', 'dwi_centroid_y', 'dwi_centroid_z', 'warning', 'note'});

seedRois.reportTable = report;
seedRois.reportCsv = fullfile(dirs.seedTarget.reports, 'roi_side_qc.csv');
seedRois.reportMd = fullfile(dirs.seedTarget.reports, 'roi_side_qc.md');
writetable(report, seedRois.reportCsv);
write_roi_qc_markdown(seedRois.reportMd, cfg, report);

end

function specs = filter_requested_specs(cfg, specs)
if ~isfield(cfg, 'seedTarget')
    return;
end

requested = strings(0, 1);
if isfield(cfg.seedTarget, 'seedNames')
    requested = [requested; string(cfg.seedTarget.seedNames(:))];
end
if isfield(cfg.seedTarget, 'targetNames')
    requested = [requested; string(cfg.seedTarget.targetNames(:))];
end
requested = unique(requested);
if isempty(requested)
    return;
end

keep = false(1, numel(specs));
for i = 1:numel(specs)
    keep(i) = any(strcmp(requested, specs(i).roi));
end
specs = specs(keep);
end

function tf = should_write_roi(cfg, path)
tf = ~isfile(path);
if isfield(cfg, 'seedTarget') && isfield(cfg.seedTarget, 'forceRois') && cfg.seedTarget.forceRois
    tf = true;
elseif isfield(cfg, 'seedTarget') && isfield(cfg.seedTarget, 'force') && cfg.seedTarget.force
    tf = true;
end
end

function options = lead_options(cfg)
options = struct();
options = ea_getptopts(cfg.subjectDir, options);
options = ea_defaultoptions(options);
options.root = [fileparts(cfg.subjectDir), filesep];
[~, options.patientname] = fileparts(cfg.subjectDir);
end

function binarize_nii(path, threshold)
nii = ea_load_nii(path);
nii.img = double(nii.img > threshold);
nii.dt = 2;
nii.fname = path;
ea_write_nii(nii);
end

function centroid = mask_centroid_mm(mask, mat)
mask = logical(mask);
if ~any(mask(:))
    centroid = [NaN, NaN, NaN];
    return;
end
[x, y, z] = ind2sub(size(mask), find(mask));
xyz = ea_vox2mm([x, y, z], mat);
centroid = mean(xyz, 1, 'omitnan');
end

function side = side_from_x(x, fallbackSide)
if ~isfinite(x) || abs(x) < 0.5
    side = fallbackSide;
elseif x < 0
    side = 'L';
else
    side = 'R';
end
end

function token = atlas_token(name)
token = regexprep(char(string(name)), '[^A-Za-z0-9]+', '_');
token = regexprep(token, '_+$', '');
end

function names = read_label_names(labelTxt)
lines = readlines(labelTxt);
names = strings(1000, 1);
for i = 1:numel(lines)
    line = strtrim(lines(i));
    if line == ""
        continue;
    end
    parts = regexp(line, '^(\d+)\s+(.+)$', 'tokens', 'once');
    if isempty(parts)
        continue;
    end
    id = str2double(parts{1});
    if id > numel(names)
        names(end+1:id) = "";
    end
    names(id) = string(parts{2});
end
end

function text = label_names_for_ids(names, ids)
parts = strings(1, numel(ids));
for i = 1:numel(ids)
    id = ids(i);
    if id <= numel(names) && names(id) ~= ""
        parts(i) = sprintf('%d:%s', id, names(id));
    else
        parts(i) = sprintf('%d:<missing label text>', id);
    end
end
text = strjoin(parts, '; ');
end

function write_roi_qc_markdown(path, cfg, report)
fid = fopen(path, 'w');
if fid < 0
    error('mh_fiber_make_seed_target_rois:ReportOpenFailed', 'Cannot write ROI QC report: %s', path);
end
cleanup = onCleanup(@() fclose(fid));

fprintf(fid, '# Seed-Target ROI Side QC\n\n');
fprintf(fid, '- Subject: `%s`\n', cfg.patientName);
fprintf(fid, '- Stimulation label: `%s`\n', cfg.stimLabel);
fprintf(fid, '- Calculation space: native DWI/b0.\n');
fprintf(fid, '- Side assignment is based on MNI centroid x when label text and spatial side disagree.\n\n');
fprintf(fid, '| Requested side | Spatial side | ROI | Atlas | Labels | MNI voxels | DWI voxels | MNI centroid x | Warning |\n');
fprintf(fid, '|---|---|---|---|---|---:|---:|---:|---|\n');
for i = 1:height(report)
    fprintf(fid, '| %s | %s | %s | %s | %s | %d | %d | %.3f | %s |\n', ...
        report.requested_side{i}, report.spatial_side{i}, report.roi{i}, report.atlas{i}, ...
        report.label_ids{i}, report.mni_voxels(i), report.dwi_voxels(i), ...
        report.mni_centroid_x(i), report.warning{i});
end
end
