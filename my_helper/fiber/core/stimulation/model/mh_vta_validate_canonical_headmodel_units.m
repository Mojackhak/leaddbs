function mh_vta_validate_canonical_headmodel_units(vol, mesh)
% Validate canonical millimeter mesh and meter volume coordinates.

meshPoints = coordinate_array(mesh, 'pnt', 'mesh.pnt');
volumePoints = coordinate_array(vol, 'pos', 'vol.pos');
if size(meshPoints, 1) ~= size(volumePoints, 1)
    invalid_contract('mesh.pnt and vol.pos must contain the same number of nodes.');
end
if isfield(mesh, 'unit')
    unit = mesh.unit;
    isTextScalar = (ischar(unit) && isrow(unit)) || ...
        (isstring(unit) && isscalar(unit));
    if ~isTextScalar || ~strcmpi(strtrim(char(unit)), 'mm')
        invalid_contract('mesh.unit must be mm when the field is present.');
    end
end
meshPoints = double(meshPoints);
volumePoints = double(volumePoints);
maxAbsPositionM = max(abs(volumePoints(:)));
if maxAbsPositionM >= 2
    invalid_contract( ...
        'vol.pos exceeds the canonical 2 m absolute coordinate bound (%.17g m).', ...
        maxAbsPositionM);
end
maxMismatchM = max(abs(meshPoints(:) / 1000 - volumePoints(:)));
if maxMismatchM > 1e-6
    invalid_contract( ...
        ['mesh.pnt / 1000 does not match vol.pos within 1e-6 m ', ...
         '(maximum mismatch %.17g m).'], maxMismatchM);
end
end

function value = coordinate_array(container, fieldName, displayName)
if ~isstruct(container) || ~isscalar(container) || ~isfield(container, fieldName)
    invalid_contract('%s is required.', displayName);
end
value = container.(fieldName);
if ~isnumeric(value) || ~isreal(value) || isempty(value) || ...
        ~ismatrix(value) || size(value, 2) ~= 3
    invalid_contract('%s must be a nonempty real numeric N x 3 array.', displayName);
end
if any(~isfinite(value(:)))
    invalid_contract('%s must contain only finite values.', displayName);
end
end

function invalid_contract(message, varargin)
error('mh_vta:InvalidCanonicalHeadmodelUnits', message, varargin{:});
end
