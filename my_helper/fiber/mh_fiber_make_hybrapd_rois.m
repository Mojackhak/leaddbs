function rois = mh_fiber_make_hybrapd_rois(cfg, dirs)
% Generate bilateral ALIC and NAc binary ROI masks from HybraPD Whole Brain labels.

labelNames = read_label_names(cfg.rois.labelingTxt);
labelNii = ea_load_nii(cfg.rois.labelingNii);

specs = { ...
    'R', 'ALIC', cfg.rois.labels.ALIC_R; ...
    'L', 'ALIC', cfg.rois.labels.ALIC_L; ...
    'L', 'NAc', cfg.rois.labels.NAc_L; ...
    'R', 'NAc', cfg.rois.labels.NAc_R};

rois = struct();
reportRows = cell(size(specs, 1), 5);

for i = 1:size(specs, 1)
    side = specs{i, 1};
    roiName = specs{i, 2};
    labelId = specs{i, 3};
    mask = round(labelNii.img) == labelId;

    if ~any(mask(:))
        error('mh_fiber_make_hybrapd_rois:EmptyRoi', ...
            'HybraPD label %d (%s_%s) is empty.', labelId, roiName, side);
    end

    out = labelNii;
    out.img = double(mask);
    out.dt = 2;
    out.fname = fullfile(dirs.rois, sprintf('HybraPD_%s_%s_%d_mni.nii', roiName, side, labelId));
    ea_write_nii(out);

    rois.mni.(side).(roiName) = out.fname;
    rois.(side).(roiName) = out.fname;
    reportRows(i, :) = {side, roiName, labelId, labelNames(labelId), nnz(mask)};
end

rois.native = make_native_rois(cfg, rois.mni);

report = cell2table(reportRows, ...
    'VariableNames', {'side', 'roi', 'label_id', 'label_name', 'voxel_count'});
rois.reportTable = report;
rois.reportCsv = fullfile(dirs.reports, 'roi_report.csv');
rois.reportMd = fullfile(dirs.reports, 'roi_report.md');
writetable(report, rois.reportCsv);
write_roi_markdown(rois.reportMd, cfg, report);

end

function nativeRois = make_native_rois(cfg, mniRois)
options = struct();
options = ea_getptopts(cfg.subjectDir, options);
options = ea_defaultoptions(options);
options.root = [fileparts(cfg.subjectDir), filesep];
[~, options.patientname] = fileparts(cfg.subjectDir);

nativeRois = struct();
for sideCell = {'R', 'L'}
    side = sideCell{1};
    for roiCell = {'NAc', 'ALIC'}
        roiName = roiCell{1};
        mniPath = mniRois.(side).(roiName);
        [roiDir, roiBase] = fileparts(mniPath);
        nativePath = fullfile(roiDir, [roiBase, '_anchorNative.nii']);

        ea_apply_normalization_tofile(options, mniPath, nativePath, 1, 0, cfg.paths.nativeReference);
        nativeNii = ea_load_nii(nativePath);
        nativeNii.img = double(nativeNii.img > 0.5);
        nativeNii.dt = 2;
        nativeNii.fname = nativePath;
        ea_write_nii(nativeNii);

        nativeRois.(side).(roiName) = nativePath;
    end
end
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

function write_roi_markdown(path, cfg, report)
fid = fopen(path, 'w');
if fid < 0
    error('mh_fiber_make_hybrapd_rois:ReportOpenFailed', 'Cannot write ROI report: %s', path);
end
cleanup = onCleanup(@() fclose(fid));

fprintf(fid, '# ROI Report\n\n');
fprintf(fid, '- Subject: `%s`\n', cfg.patientName);
fprintf(fid, '- Stimulation label: `%s`\n', cfg.stimLabel);
fprintf(fid, '- Atlas: `%s`\n', cfg.rois.atlasName);
fprintf(fid, '- Label image: `%s`\n\n', cfg.rois.labelingNii);
fprintf(fid, '| Side | ROI | Label ID | Label name | Voxels |\n');
fprintf(fid, '|---|---|---:|---|---:|\n');
for i = 1:height(report)
    fprintf(fid, '| %s | %s | %d | %s | %d |\n', ...
        report.side{i}, report.roi{i}, report.label_id(i), report.label_name{i}, report.voxel_count(i));
end
end
