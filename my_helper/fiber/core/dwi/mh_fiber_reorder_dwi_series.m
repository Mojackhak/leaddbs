function mh_fiber_reorder_dwi_series(sourceDwi, sourceBval, sourceBvec, ...
    outputDwi, outputBval, outputBvec, outputToSourceOrder, force)
% Reorder a DWI series and its gradients using one explicit volume mapping.

if nargin < 8
    force = false;
end
sourceDwi = char(string(sourceDwi));
sourceBval = char(string(sourceBval));
sourceBvec = char(string(sourceBvec));
outputDwi = char(string(outputDwi));
outputBval = char(string(outputBval));
outputBvec = char(string(outputBvec));
force = logical(force);

V = spm_vol(sourceDwi);
bvals = mh_fiber_load_bval(sourceBval);
bvecs = load_bvecs(sourceBvec);
nVolumes = numel(V);
order = validate_order(outputToSourceOrder, nVolumes);
if numel(bvals) ~= nVolumes || size(bvecs, 2) ~= nVolumes
    error('mh_fiber_reorder_dwi_series:GradientCountMismatch', ...
        'DWI, bval, and bvec counts must match before reordering.');
end

outputs = {outputDwi, outputBval, outputBvec};
if all(cellfun(@isfile, outputs)) && ~force
    return;
end
if any(cellfun(@isfile, outputs)) && ~force
    error('mh_fiber_reorder_dwi_series:PartialOutput', ...
        'A partial reordered DWI output already exists. Use a clean staging directory.');
end
mh_util_make_dir(fileparts(outputDwi));
delete_if_file(outputDwi);
delete_if_file(outputBval);
delete_if_file(outputBvec);

for outputIndex = 1:nVolumes
    sourceIndex = order(outputIndex);
    Vo = V(sourceIndex);
    Vo.fname = outputDwi;
    Vo.n = [outputIndex, 1];
    Vo.descrip = sprintf('Source DWI volume %d reordered to output volume %d', ...
        sourceIndex, outputIndex);
    spm_write_vol(Vo, spm_read_vols(V(sourceIndex)));
end
write_numeric_rows(outputBval, bvals(order), '%.12g');
write_numeric_rows(outputBvec, bvecs(:, order), '%.12g');
end

function order = validate_order(value, nVolumes)
order = double(value(:)');
if numel(order) ~= nVolumes || any(~isfinite(order)) || ...
        any(order ~= round(order)) || ~isequal(sort(order), 1:nVolumes)
    error('mh_fiber_reorder_dwi_series:InvalidOrder', ...
        'Volume order must be a permutation of 1:%d.', nVolumes);
end
end

function bvecs = load_bvecs(path)
bvecs = load(path);
if size(bvecs, 1) ~= 3 && size(bvecs, 2) == 3
    bvecs = bvecs';
end
if size(bvecs, 1) ~= 3
    error('mh_fiber_reorder_dwi_series:InvalidBvec', ...
        'bvec file must contain a 3 x N or N x 3 matrix: %s', path);
end
end

function write_numeric_rows(path, values, formatSpec)
fid = fopen(path, 'w');
if fid < 0
    error('mh_fiber_reorder_dwi_series:WriteFailed', ...
        'Could not write numeric sidecar: %s', path);
end
cleanupObj = onCleanup(@() fclose(fid)); %#ok<NASGU>
for row = 1:size(values, 1)
    for column = 1:size(values, 2)
        if column > 1
            fprintf(fid, ' ');
        end
        fprintf(fid, formatSpec, values(row, column));
    end
    fprintf(fid, '\n');
end
end

function delete_if_file(path)
if isfile(path)
    delete(path);
end
end
