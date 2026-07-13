function outputPath = mh_vta_compose_group_peak(sourcePaths, outputPath)
% Compose an alternating-group E-field using a voxelwise source maximum.

if ischar(sourcePaths) || isstring(sourcePaths)
    sourcePaths = cellstr(sourcePaths);
end
if ~iscell(sourcePaths) || isempty(sourcePaths)
    error('mh_vta:InvalidGroupPeakInputs', ...
        'sourcePaths must contain at least one E-field NIfTI.');
end

reference = ea_load_nii(sourcePaths{1});
peak = single(reference.img);
peak(~isfinite(peak)) = NaN;

for index = 2:numel(sourcePaths)
    current = ea_load_nii(sourcePaths{index});
    assert_same_grid(reference, current, sourcePaths{index});
    values = single(current.img);
    values(~isfinite(values)) = NaN;
    peakFinite = isfinite(peak);
    valueFinite = isfinite(values);
    peak(~peakFinite & valueFinite) = values(~peakFinite & valueFinite);
    bothFinite = peakFinite & valueFinite;
    peak(bothFinite) = max(peak(bothFinite), values(bothFinite));
end

outputDir = fileparts(outputPath);
if ~isempty(outputDir) && ~isfolder(outputDir)
    mkdir(outputDir);
end
reference.img = peak;
reference.fname = outputPath;
reference.dt = [16 0];
ea_write_nii(reference);
end

function assert_same_grid(reference, current, path)
if ~isequal(size(reference.img), size(current.img)) || ...
        ~isequal(size(reference.mat), size(current.mat)) || ...
        any(abs(double(reference.mat(:)) - double(current.mat(:))) > 1e-12)
    error('mh_vta:GridMismatch', ...
        'Source E-field does not match the reference grid: %s', path);
end
end
