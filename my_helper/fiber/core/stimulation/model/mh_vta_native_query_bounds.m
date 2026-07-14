function [lowerBound, upperBound] = mh_vta_native_query_bounds( ...
        pointsMm, anchorAffine, dimensions)
% Bound native-grid queries around the physical FEM sample extent.

validateattributes(pointsMm, {'numeric'}, ...
    {'2d', 'ncols', 3, 'real', 'finite', 'nonempty'}, ...
    mfilename, 'pointsMm');
validateattributes(anchorAffine, {'numeric'}, ...
    {'size', [4, 4], 'real', 'finite'}, mfilename, 'anchorAffine');
validateattributes(dimensions, {'numeric'}, ...
    {'vector', 'numel', 3, 'real', 'finite', 'positive', 'integer'}, ...
    mfilename, 'dimensions');

pointsMm = double(pointsMm);
dimensions = double(dimensions(:)');
minimum = min(pointsMm, [], 1);
maximum = max(pointsMm, [], 1);
[x, y, z] = ndgrid([minimum(1), maximum(1)], ...
    [minimum(2), maximum(2)], [minimum(3), maximum(3)]);
cornersMm = [x(:), y(:), z(:)];
cornersVox = ea_mm2vox(cornersMm, double(anchorAffine));

lowerBound = floor(min(cornersVox, [], 1) - 1);
upperBound = ceil(max(cornersVox, [], 1) + 1);
lowerBound = max(lowerBound, [1, 1, 1]);
upperBound = min(upperBound, dimensions);
if any(lowerBound > upperBound)
    lowerBound = zeros(0, 3);
    upperBound = zeros(0, 3);
end
end
