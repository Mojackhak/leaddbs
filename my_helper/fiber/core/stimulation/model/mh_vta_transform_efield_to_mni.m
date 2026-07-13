function mh_vta_transform_efield_to_mni( ...
        nativeEfieldPath, options, mniReferencePath, outputPath)
% Transform a continuous native E-field onto the canonical MNI grid.

nativeEfieldPath = char(string(nativeEfieldPath));
mniReferencePath = char(string(mniReferencePath));
outputPath = char(string(outputPath));
if ~isfile(nativeEfieldPath)
    error('mh_vta_transform_efield_to_mni:MissingInput', ...
        'Native E-field NIfTI does not exist: %s', nativeEfieldPath);
end
if ~isfile(mniReferencePath)
    error('mh_vta_transform_efield_to_mni:MissingReference', ...
        'Canonical MNI reference NIfTI does not exist: %s', mniReferencePath);
end
if ~isstruct(options) || ~isfield(options, 'subj')
    error('mh_vta_transform_efield_to_mni:InvalidOptions', ...
        'Lead-DBS subject options are required for normalization.');
end

ensure_parent_directory(outputPath);
ea_apply_normalization_tofile( ...
    options, nativeEfieldPath, outputPath, 0, 1, mniReferencePath);
if ~isfile(outputPath)
    error('mh_vta_transform_efield_to_mni:MissingOutput', ...
        'Lead-DBS normalization did not create the MNI E-field: %s', outputPath);
end
end

function ensure_parent_directory(path)
parent = fileparts(path);
if ~isempty(parent) && ~isfolder(parent)
    mkdir(parent);
end
end
