function [points, values, keep] = mh_vta_filter_export_samples( ...
        mesh, points, values)
% Exclude contact and insulating tetrahedra before E-field interpolation.

if ~isstruct(mesh) || ~isfield(mesh, 'tissue') || ...
        ~isnumeric(points) || size(points, 2) ~= 3 || ...
        ~isnumeric(values) || ~isvector(values)
    invalid_samples();
end
tissue = double(mesh.tissue(:));
values = values(:);
sampleCount = size(points, 1);
if numel(tissue) ~= sampleCount || numel(values) ~= sampleCount
    invalid_samples();
end

keep = isfinite(tissue) & tissue <= 2;
if ~any(keep)
    error('mh_vta:MissingFemExportSamples', ...
        'No brain-tissue FEM samples remain after electrode removal.');
end
points = points(keep, :);
values = values(keep);
end

function invalid_samples()
error('mh_vta:InvalidFemExportSamples', ...
    'Mesh tissue, FEM points, and field values must have aligned samples.');
end
