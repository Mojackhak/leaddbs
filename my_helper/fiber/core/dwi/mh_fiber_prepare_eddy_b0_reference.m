function result = mh_fiber_prepare_eddy_b0_reference(dwiPath, bvalPath, ...
    bvecPath, workDir, strategy, threshold, force)
% Select a b0 reference and prepare reference-first inputs for eddy.

if nargin < 7
    force = false;
end
strategy = lower(strtrim(char(string(strategy))));
threshold = double(threshold);
if ~ismember(strategy, {'mean', 'last'})
    error('mh_fiber_prepare_eddy_b0_reference:InvalidStrategy', ...
        'Reference strategy must be mean or last.');
end
if ~isscalar(threshold) || ~isfinite(threshold) || threshold <= 0
    error('mh_fiber_prepare_eddy_b0_reference:InvalidThreshold', ...
        'b0 threshold must be a positive scalar.');
end

bvals = mh_fiber_load_bval(bvalPath);
V = spm_vol(dwiPath);
if numel(V) ~= numel(bvals)
    error('mh_fiber_prepare_eddy_b0_reference:VolumeCountMismatch', ...
        'DWI volume count does not match bval count.');
end
b0Indices = find(bvals < threshold);
if isempty(b0Indices)
    error('mh_fiber_prepare_eddy_b0_reference:MissingB0', ...
        'No b0 volume satisfies bval < %.12g.', threshold);
end

mh_util_make_dir(workDir);
referenceB0 = fullfile(workDir, 'selected_reference_b0.nii');
inputDwi = fullfile(workDir, 'eddy_input_reference_first.nii');
inputBval = fullfile(workDir, 'eddy_input_reference_first.bval');
inputBvec = fullfile(workDir, 'eddy_input_reference_first.bvec');
mappingPath = fullfile(workDir, 'eddy_volume_mapping.json');

if strcmp(strategy, 'last')
    selectedSourceIndex = b0Indices(end);
    eddyToSource = [selectedSourceIndex, setdiff(1:numel(V), selectedSourceIndex, 'stable')];
else
    selectedSourceIndex = NaN;
    eddyToSource = 1:numel(V);
end
mh_fiber_extract_b0_reference(dwiPath, referenceB0, bvals, ...
    strategy, threshold, force);
sourceToEddy = zeros(1, numel(V));
sourceToEddy(eddyToSource) = 1:numel(V);
if strcmp(strategy, 'last')
    mh_fiber_reorder_dwi_series(dwiPath, bvalPath, bvecPath, ...
        inputDwi, inputBval, inputBvec, eddyToSource, force);
else
    inputDwi = dwiPath;
    inputBval = bvalPath;
    inputBvec = bvecPath;
end

mapping = struct();
mapping.strategy = strategy;
mapping.b0_threshold = threshold;
mapping.b0_source_indices_one_based = b0Indices;
mapping.selected_source_index_one_based = selectedSourceIndex;
mapping.eddy_to_source_one_based = eddyToSource;
mapping.source_to_eddy_one_based = sourceToEddy;
mapping.reference_b0_path = referenceB0;
mapping.reference_b0_sha256 = mh_fiber_file_sha256(referenceB0);
mh_util_write_json(mappingPath, mapping, ...
    'mh_fiber_prepare_eddy_b0_reference:WriteFailed');

result = mapping;
result.inputDwi = inputDwi;
result.inputBval = inputBval;
result.inputBvec = inputBvec;
result.referenceB0 = referenceB0;
result.mappingPath = mappingPath;
end
