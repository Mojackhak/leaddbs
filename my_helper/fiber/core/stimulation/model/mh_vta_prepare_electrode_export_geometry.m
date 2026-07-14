function geometry = mh_vta_prepare_electrode_export_geometry( ...
        mesh, points, trajectory, sideIndex, elspec)
% Prepare field-independent FEM export coordinates and value indices.

if ~isstruct(mesh) || ~isfield(mesh, 'tissue') || ...
        ~isnumeric(points) || size(points, 2) ~= 3
    invalid_samples();
end
tissue = double(mesh.tissue(:));
if numel(tissue) ~= size(points, 1)
    invalid_samples();
end
tissueKeep = isfinite(tissue) & tissue <= 2;
if ~any(tissueKeep)
    error('mh_vta:MissingFemExportSamples', ...
        'No brain-tissue FEM samples remain after electrode removal.');
end
validate_geometry_inputs(trajectory, sideIndex, elspec);

tissueIndices = find(tissueKeep);
filteredPoints = double(points(tissueKeep, :));
electrodeTrajectory = double(trajectory{sideIndex});
origin = electrodeTrajectory(1, :);
relativeTrajectory = electrodeTrajectory - origin;
relativePoints = filteredPoints - origin;
rotation = electrode_axis_rotation(relativeTrajectory(end, :));
rotatedPoints = rotation * relativePoints';

shaftMask = rotatedPoints(2, :) > 0;
shaftPoints = rotatedPoints(:, shaftMask);
radialNorm = vecnorm(shaftPoints([1, 3], :), 2, 1);
leadRadius = double(elspec.lead_diameter) / 2;
radialFactor = (radialNorm - leadRadius) ./ radialNorm;
shaftPoints([1, 3], :) = shaftPoints([1, 3], :) .* radialFactor;
shaftPoints(:, radialFactor < 0) = NaN;
rotatedPoints(:, shaftMask) = shaftPoints;

adjustedPoints = rotation' * rotatedPoints + origin';
artifactMask = isnan(adjustedPoints(1, :));
adjustedPoints(:, artifactMask) = [];
tissueIndices(artifactMask) = [];
if isempty(tissueIndices)
    error('mh_vta:MissingFemExportSamples', ...
        'No brain-tissue FEM samples remain after electrode removal.');
end
geometry = struct( ...
    'tetrahedron_midpoints_mm', double(points), ...
    'tissue_keep_indices', find(tissueKeep), ...
    'electrode_adjusted_points_mm', adjustedPoints', ...
    'final_field_value_indices', tissueIndices);
end

function validate_geometry_inputs(trajectory, sideIndex, elspec)
if ~iscell(trajectory) || ~isnumeric(sideIndex) || ~isscalar(sideIndex) || ...
        sideIndex < 1 || sideIndex ~= fix(sideIndex) || ...
        sideIndex > numel(trajectory) || ...
        ~isnumeric(trajectory{sideIndex}) || ...
        size(trajectory{sideIndex}, 2) ~= 3 || ...
        size(trajectory{sideIndex}, 1) < 2 || ...
        any(~isfinite(trajectory{sideIndex}(:))) || ...
        ~isstruct(elspec) || ~isfield(elspec, 'lead_diameter') || ...
        ~isnumeric(elspec.lead_diameter) || ...
        ~isscalar(elspec.lead_diameter) || ...
        ~isfinite(elspec.lead_diameter) || elspec.lead_diameter <= 0
    error('mh_vta:InvalidElectrodeRemovalGeometry', ...
        'Trajectory, side index, and lead diameter must define valid geometry.');
end
end

function rotation = electrode_axis_rotation(electrodeVector)
targetVector = [0; 1; 0];
electrodeVector = electrodeVector(:);
if norm(electrodeVector) == 0
    error('mh_vta:InvalidElectrodeRemovalGeometry', ...
        'Electrode trajectory must have nonzero length.');
end
thetaElectrode = atan2d(electrodeVector(2), electrodeVector(1));
thetaTarget = atan2d(targetVector(2), targetVector(1));
firstZ = rotation_z(-thetaElectrode);
targetZ = rotation_z(-thetaTarget);
rotatedElectrode = firstZ * electrodeVector;
rotatedTarget = targetZ * targetVector;
targetAngle = atan2d(rotatedTarget(1), rotatedTarget(3));
electrodeAngle = atan2d(rotatedElectrode(1), rotatedElectrode(3));
rotation = targetZ' * rotation_y(targetAngle - electrodeAngle) * firstZ;
end

function matrix = rotation_y(angle)
matrix = [cosd(angle), 0, sind(angle); 0, 1, 0; ...
    -sind(angle), 0, cosd(angle)];
end

function matrix = rotation_z(angle)
matrix = [cosd(angle), -sind(angle), 0; ...
    sind(angle), cosd(angle), 0; 0, 0, 1];
end

function invalid_samples()
error('mh_vta:InvalidFemExportSamples', ...
    'Mesh tissue, FEM points, and field values must have aligned samples.');
end
