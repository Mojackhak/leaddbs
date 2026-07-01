function record = mh_atlas_build_roi_mask(spec, roi, side, tempDir, opts)
% Build one side of one ROI and write a reference-grid binary mask.

if nargin < 5
    opts = struct('Force', true);
end

side = char(string(side));
sideDir = side_to_dir(side);
sideSpec = roi.sides.(side);

roiName = char(string(roi.name));
operation = lower(char(string(roi.operation)));
category = get_optional_string(roi, 'category', 'primary');
role = get_optional_string(roi, 'role', 'target');
notes = get_optional_string(roi, 'notes', '');
thresholdText = '';

outputFile = fullfile(spec.output_dir, sideDir, [roiName, '.nii.gz']);
if isfile(outputFile) && ~opts.Force
    error('mh_atlas_build_roi_mask:OutputExists', ...
        'Output exists and Force is false: %s', outputFile);
end

ensure_dir(fileparts(outputFile));
ensure_dir(tempDir);

[mask, sourceInfo, sourceFiles, sourceLabels, thresholdText] = build_mask(spec, roi, sideSpec, side, operation);

safeName = regexprep([roiName, '_', side], '[^A-Za-z0-9_]+', '_');
rawPath = fullfile(tempDir, [safeName, '_raw.nii']);
reslicedPath = fullfile(tempDir, [safeName, '_reference.nii.gz']);

write_mask_nifti(mask, sourceInfo, rawPath);
mh_atlas_reslice_to_reference(rawPath, spec.reference_image, reslicedPath);
run_command(sprintf('mrcalc %s 0 -gt %s -force -quiet', ...
    shell_quote(reslicedPath), shell_quote(outputFile)));

record = struct();
record.atlas_name = spec.atlas_name;
record.roi_name = roiName;
record.side = side;
record.role = role;
record.category = category;
record.operation = operation;
record.threshold = thresholdText;
record.source_files = strjoin(string(sourceFiles), '; ');
record.source_labels = sourceLabels;
record.output_file = outputFile;
record.notes = notes;
end

function [mask, info, sourceFiles, sourceLabels, thresholdText] = build_mask(spec, roi, sideSpec, side, operation)
sourceFiles = strings(0, 1);
sourceLabels = '';
thresholdText = '';

switch operation
    case 'threshold'
        sourceFile = resolve_source_file(spec, sideSpec);
        threshold = get_numeric_field(roi, sideSpec, 'threshold');
        operator = get_optional_string(roi, 'threshold_operator', '>');
        if isfield(sideSpec, 'threshold_operator')
            operator = char(string(sideSpec.threshold_operator));
        end
        [data, info] = load_image(sourceFile);
        mask = apply_threshold(data, threshold, operator);
        sourceFiles = string(sourceFile);
        thresholdText = sprintf('%s %g', operator, threshold);

    case 'copy_binary'
        sourceFile = resolve_source_file(spec, sideSpec);
        [data, info] = load_image(sourceFile);
        mask = data > 0;
        sourceFiles = string(sourceFile);
        thresholdText = '> 0';

    case 'label_union'
        sourceFile = resolve_source_file(spec, sideSpec);
        labels = get_labels(sideSpec);
        [data, info] = load_image(sourceFile);
        mask = ismember(round(double(data)), labels);
        sourceFiles = string(sourceFile);
        sourceLabels = labels_to_text(labels, sideSpec);
        thresholdText = 'exact labels';

    case 'posterior_split'
        sourceFile = resolve_source_file(spec, sideSpec);
        labels = get_labels(sideSpec);
        splitMode = get_optional_string(roi, 'split', 'posterior_half');
        if isfield(sideSpec, 'split')
            splitMode = char(string(sideSpec.split));
        end
        [data, info] = load_image(sourceFile);
        baseMask = ismember(round(double(data)), labels);
        mask = posterior_split_mask(baseMask, info, splitMode);
        sourceFiles = string(sourceFile);
        sourceLabels = labels_to_text(labels, sideSpec);
        thresholdText = splitMode;

    case {'union', 'intersect', 'subtract'}
        [mask, info, sourceFiles, sourceLabels, thresholdText] = build_composite_mask(spec, roi, side, operation);

    otherwise
        error('mh_atlas_build_roi_mask:UnsupportedOperation', ...
            'Unsupported operation `%s` for ROI `%s`.', operation, char(string(roi.name)));
end

mask = logical(mask);
if ~any(mask(:))
    warning('mh_atlas_build_roi_mask:EmptyMask', ...
        'ROI %s side %s is empty before reference resampling.', char(string(roi.name)), side);
end
end

function [mask, info, sourceFiles, sourceLabels, thresholdText] = build_composite_mask(spec, roi, side, operation)
if ~isfield(roi, 'sources') || isempty(roi.sources)
    error('mh_atlas_build_roi_mask:MissingSources', ...
        'Composite ROI `%s` requires a non-empty sources array.', char(string(roi.name)));
end

sourceFiles = strings(0, 1);
sourceLabels = strings(0, 1);
thresholdParts = strings(0, 1);
mask = [];
info = [];

for i = 1:numel(roi.sources)
    src = roi.sources(i);
    if ~isfield(src, 'sides')
        src.sides = roi.sides;
    end
    sideSpec = src.sides.(side);
    srcOperation = lower(char(string(src.operation)));
    [srcMask, srcInfo, srcFiles, srcLabelText, srcThresholdText] = build_mask(spec, src, sideSpec, side, srcOperation);
    if isempty(mask)
        mask = srcMask;
        info = srcInfo;
    else
        assert_same_grid(info, srcInfo, char(string(roi.name)));
        switch operation
            case 'union'
                mask = mask | srcMask;
            case 'intersect'
                mask = mask & srcMask;
            case 'subtract'
                mask = mask & ~srcMask;
        end
    end
    sourceFiles = [sourceFiles; srcFiles(:)]; %#ok<AGROW>
    if strlength(string(srcLabelText)) > 0
        sourceLabels(end+1) = string(srcLabelText); %#ok<AGROW>
    end
    thresholdParts(end+1) = string(srcThresholdText); %#ok<AGROW>
end

sourceLabels = strjoin(sourceLabels, ' | ');
thresholdText = sprintf('%s(%s)', operation, strjoin(thresholdParts, ', '));
end

function sourceFile = resolve_source_file(spec, sideSpec)
if ~isfield(sideSpec, 'source_file')
    error('mh_atlas_build_roi_mask:MissingSourceFile', 'Side spec is missing source_file.');
end
sourceFile = char(string(sideSpec.source_file));
if ~startsWith(sourceFile, filesep)
    sourceFile = fullfile(spec.repo_dir, sourceFile);
end
if ~isfile(sourceFile)
    error('mh_atlas_build_roi_mask:MissingSourceFile', 'Source file does not exist: %s', sourceFile);
end
end

function [data, info] = load_image(sourceFile)
info = niftiinfo(sourceFile);
data = niftiread(info);
end

function mask = apply_threshold(data, threshold, operator)
data = double(data);
switch strtrim(operator)
    case '>'
        mask = data > threshold;
    case '>='
        mask = data >= threshold;
    otherwise
        error('mh_atlas_build_roi_mask:UnsupportedThresholdOperator', ...
            'Unsupported threshold operator: %s', operator);
end
end

function labels = get_labels(sideSpec)
if ~isfield(sideSpec, 'label_ids')
    error('mh_atlas_build_roi_mask:MissingLabels', 'Side spec is missing label_ids.');
end
labels = double(sideSpec.label_ids(:)');
end

function text = labels_to_text(labels, sideSpec)
if isfield(sideSpec, 'label_names')
    names = cellstr(string(sideSpec.label_names(:)));
    parts = strings(1, numel(labels));
    for i = 1:numel(labels)
        if i <= numel(names)
            parts(i) = sprintf('%g:%s', labels(i), names{i});
        else
            parts(i) = sprintf('%g', labels(i));
        end
    end
    text = char(strjoin(parts, '; '));
else
    text = char(strjoin(string(labels), '; '));
end
end

function value = get_numeric_field(roi, sideSpec, fieldName)
if isfield(sideSpec, fieldName)
    value = double(sideSpec.(fieldName));
elseif isfield(roi, fieldName)
    value = double(roi.(fieldName));
else
    error('mh_atlas_build_roi_mask:MissingNumericField', ...
        'Missing numeric field: %s', fieldName);
end
end

function value = get_optional_string(s, fieldName, defaultValue)
if isfield(s, fieldName)
    value = char(string(s.(fieldName)));
else
    value = defaultValue;
end
end

function mask = posterior_split_mask(baseMask, info, splitMode)
idx = find(baseMask);
if isempty(idx)
    mask = false(size(baseMask));
    return;
end
[~, yIdx, ~] = ind2sub(size(baseMask), idx);
yWorld = voxel_axis_world(info, yIdx, 2);
sorted = sort(yWorld(:));
switch lower(splitMode)
    case 'posterior_half'
        cutoff = sorted(max(1, floor(numel(sorted) / 2)));
    case 'posterior_third'
        cutoff = sorted(max(1, floor(numel(sorted) / 3)));
    otherwise
        error('mh_atlas_build_roi_mask:UnsupportedSplit', ...
            'Unsupported posterior split: %s', splitMode);
end
keep = yWorld <= cutoff;
mask = false(size(baseMask));
mask(idx(keep)) = true;
end

function coord = voxel_axis_world(info, index, axisNumber)
T = info.Transform.T;
coord = T(4, axisNumber) + (double(index(:)) - 1) .* T(axisNumber, axisNumber);
end

function write_mask_nifti(mask, info, outputPath)
outInfo = info;
outInfo.Datatype = 'uint8';
outInfo.BitsPerPixel = 8;
outInfo.ImageSize = size(mask);
if isfield(outInfo, 'Filename')
    outInfo.Filename = outputPath;
end
if isfile(outputPath)
    delete(outputPath);
end
niftiwrite(uint8(mask), outputPath, outInfo);
end

function assert_same_grid(infoA, infoB, roiName)
sameSize = isequal(infoA.ImageSize, infoB.ImageSize);
samePix = max(abs(double(infoA.PixelDimensions(1:3)) - double(infoB.PixelDimensions(1:3)))) < 1e-6;
sameTransform = max(abs(infoA.Transform.T(:) - infoB.Transform.T(:))) < 1e-6;
if ~(sameSize && samePix && sameTransform)
    error('mh_atlas_build_roi_mask:CompositeGridMismatch', ...
        'Composite ROI `%s` sources are not on the same grid.', roiName);
end
end

function ensure_dir(path)
if ~isfolder(path)
    mkdir(path);
end
end

function sideDir = side_to_dir(side)
switch upper(side)
    case 'L'
        sideDir = 'lh';
    case 'R'
        sideDir = 'rh';
    otherwise
        error('mh_atlas_build_roi_mask:InvalidSide', 'Invalid side: %s', side);
end
end

function run_command(cmd)
[status, output] = system(cmd);
if status ~= 0
    error('mh_atlas_build_roi_mask:CommandFailed', ...
        'Command failed:\n%s\n\n%s', cmd, output);
end
end

function q = shell_quote(path)
path = char(string(path));
q = ['''', strrep(path, '''', '''"''"'''), ''''];
end
