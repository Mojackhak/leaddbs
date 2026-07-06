function context = mh_fiber_orientation_correction_context(metadata, transformName)
% Compose previous and incremental orientation-correction provenance.

if nargin < 1 || isempty(metadata)
    metadata = struct();
end
transformName = validatestring(char(string(transformName)), ...
    {'identity', 'flipY', 'flipZ', 'rotX180'}, ...
    'mh_fiber_orientation_correction_context', 'transformName');

incrementalMatrix = mh_fiber_orientation_transform_matrix(transformName);
previousTransform = '';
previousMatrix = eye(3);
hasPrevious = isfield(metadata, 'ImageContentOrientationCorrection') && ...
    logical(metadata.ImageContentOrientationCorrection);

if hasPrevious
    if isfield(metadata, 'OrientationCorrectionNetTransform') && ...
            ~isempty(metadata.OrientationCorrectionNetTransform)
        previousTransform = char(string(metadata.OrientationCorrectionNetTransform));
    elseif isfield(metadata, 'OrientationCorrectionTransform') && ...
            ~isempty(metadata.OrientationCorrectionTransform)
        previousTransform = char(string(metadata.OrientationCorrectionTransform));
    end

    if isfield(metadata, 'OrientationCorrectionBvecMatrix')
        previousMatrix = double(metadata.OrientationCorrectionBvecMatrix);
    elseif ~isempty(previousTransform)
        previousMatrix = mh_fiber_orientation_transform_matrix(previousTransform);
    end
end

netMatrix = incrementalMatrix * previousMatrix;
context = struct();
context.HasPrevious = hasPrevious;
context.PreviousTransform = previousTransform;
context.PreviousMatrix = previousMatrix;
context.IncrementalTransform = transformName;
context.IncrementalMatrix = incrementalMatrix;
context.NetMatrix = netMatrix;
context.NetTransform = matrix_to_transform_name(netMatrix);
end

function transformName = matrix_to_transform_name(matrix)
names = {'identity', 'flipY', 'flipZ', 'rotX180'};
for i = 1:numel(names)
    candidate = mh_fiber_orientation_transform_matrix(names{i});
    if isequal(round(matrix), candidate)
        transformName = names{i};
        return;
    end
end
error('mh_fiber_orientation_correction_context:UnsupportedNetTransform', ...
    'The composed orientation transform is not supported.');
end
