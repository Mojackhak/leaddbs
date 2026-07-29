function selectedSourceIndex = mh_fiber_extract_b0_reference( ...
    dwiPath, b0Path, bvals, strategy, threshold, force)
% Extract a configured b0 reference without changing its spatial header.

if nargin < 6
    force = false;
end
strategy = lower(strtrim(char(string(strategy))));
threshold = double(threshold);
bvals = double(bvals(:)');
if ~ismember(strategy, {'mean', 'last'})
    error('mh_fiber_extract_b0_reference:InvalidStrategy', ...
        'Reference strategy must be mean or last.');
end
b0Indices = find(bvals < threshold);
if isempty(b0Indices)
    error('mh_fiber_extract_b0_reference:MissingB0', ...
        'No b0 volume satisfies bval < %.12g.', threshold);
end
V = spm_vol(dwiPath);
if numel(V) ~= numel(bvals)
    error('mh_fiber_extract_b0_reference:VolumeCountMismatch', ...
        'DWI volume count does not match bval count.');
end
if strcmp(strategy, 'last')
    selectedSourceIndex = b0Indices(end);
    indices = selectedSourceIndex;
else
    selectedSourceIndex = NaN;
    indices = b0Indices;
end
if isfile(b0Path) && ~logical(force)
    return;
end

data = zeros(V(1).dim, 'double');
for index = indices
    data = data + double(spm_read_vols(V(index)));
end
data = data ./ numel(indices);
Vo = V(indices(1));
Vo.fname = b0Path;
Vo.n = [1, 1];
Vo.dt = [16, 0];
Vo.descrip = sprintf('%s b0 reference using bval < %.12g', strategy, threshold);
if isfile(b0Path)
    delete(b0Path);
end
spm_write_vol(Vo, data);
end
