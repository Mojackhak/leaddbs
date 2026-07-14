function [points, values, keep] = mh_vta_remove_electrode_export_samples( ...
        mesh, points, values, trajectory, sideIndex, elspec)
% Apply the standard Horn electrode-removal geometry to FEM export samples.

if ~isnumeric(values) || ~isvector(values) || ...
        numel(values) ~= size(points, 1)
    error('mh_vta:InvalidFemExportSamples', ...
        'Mesh tissue, FEM points, and field values must have aligned samples.');
end
geometry = mh_vta_prepare_electrode_export_geometry( ...
    mesh, points, trajectory, sideIndex, elspec);
points = geometry.electrode_adjusted_points_mm;
values = values(:);
values = values(geometry.final_field_value_indices);
keep = false(size(mesh.tissue(:)));
keep(geometry.final_field_value_indices) = true;
end
