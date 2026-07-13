function mh_vta_threshold_efield(efieldPath, thresholdVPerM, outputPath)
% Threshold a continuous E-field NIfTI using an inclusive indicator.

efieldPath = char(string(efieldPath));
outputPath = char(string(outputPath));
validateattributes(thresholdVPerM, {'numeric'}, ...
    {'real', 'finite', 'scalar', 'nonnegative'}, mfilename, 'thresholdVPerM');
if ~isfile(efieldPath)
    error('mh_vta_threshold_efield:MissingInput', ...
        'E-field NIfTI does not exist: %s', efieldPath);
end

nii = ea_load_nii(efieldPath);
nii.img = uint8(isfinite(nii.img) & nii.img >= double(thresholdVPerM));
nii.dt = [2, machine_endian_code()];
nii.pinfo = [1; 0; 0];
nii.descrip = sprintf('VTA indicator E >= %.12g V/m', thresholdVPerM);
nii.fname = outputPath;
ensure_parent_directory(outputPath);
ea_write_nii(nii);
end

function code = machine_endian_code()
[~, ~, endian] = computer;
code = double(endian == 'B');
end

function ensure_parent_directory(path)
parent = fileparts(path);
if ~isempty(parent) && ~isfolder(parent)
    mkdir(parent);
end
end
