function ea_fnirt_warp_to_ants(fslWarp, source, reference, antsWarp)
% Convert an FSL/FNIRT warp into an ANTs-compatible displacement field.

ea_mkdir(fileparts(antsWarp));

if endsWith(antsWarp, '.gz')
    antsWarpNii = antsWarp(1:end-3);
else
    antsWarpNii = antsWarp;
end

tmpDir = fullfile(ea_getleadtempdir, ['fnirt_to_ants_', ea_generate_uuid]);
ea_mkdir(tmpDir);

basedir = [fileparts(which('ea_fnirt')), filesep];
APPLYWARP = ea_getExec([basedir, 'applywarp'], escapePath = 1);

sourceNii = ea_load_nii(source);
referenceNii = ea_load_nii(reference);
referenceSize = size(referenceNii.img);
referenceSize = referenceSize(1:3);

field = zeros([referenceSize, 1, 3], 'single');

for component = 1:3
    sourceCoord = fullfile(tmpDir, ['source_coord_', num2str(component), '.nii']);
    warpedCoord = fullfile(tmpDir, ['warped_coord_', num2str(component), '.nii']);

    coordNii = sourceNii;
    coordNii.img = coordinate_component(size(sourceNii.img), sourceNii.mat, component);
    coordNii.dt(1) = 16;
    coordNii.fname = sourceCoord;
    ea_write_nii(coordNii);

    cmd = [APPLYWARP, ...
        ' --in=', ea_path_helper(sourceCoord), ...
        ' --ref=', ea_path_helper(reference), ...
        ' --warp=', ea_path_helper(fslWarp), ...
        ' --out=', ea_path_helper(warpedCoord), ...
        ' --interp=trilinear'];

    status = ea_runcmd(cmd, env='FSLOUTPUTTYPE=NIFTI');
    if status
        ea_error('Failed to apply FNIRT warp to coordinate image.');
    end

    warpedNii = ea_load_nii(warpedCoord);
    displacement = single(warpedNii.img) - coordinate_component(referenceSize, referenceNii.mat, component);

    if component <= 2
        displacement = -displacement;
    end

    field(:,:,:,1,component) = displacement;
end

nii = load_nii(reference);
nii.img = field;
nii.hdr.dime.dim(1) = 5;
nii.hdr.dime.dim(2:4) = referenceSize;
nii.hdr.dime.dim(5) = 1;
nii.hdr.dime.dim(6) = 3;
nii.hdr.dime.dim(7:8) = 1;
nii.hdr.dime.datatype = 16;
nii.hdr.dime.bitpix = 32;
nii.hdr.dime.intent_code = 1007;
nii.hdr.dime.xyzt_units = 2;
nii.hdr.hist.descrip = '';

save_nii(nii, antsWarpNii, []);

if endsWith(antsWarp, '.gz')
    gzip(antsWarpNii);
    delete(antsWarpNii);
end

ea_delete(tmpDir);


function componentImage = coordinate_component(imageSize, matrix, component)

imageSize = imageSize(1:3);

i = single((1:imageSize(1))');
j = single(1:imageSize(2));
k = single(reshape(1:imageSize(3), 1, 1, []));

componentImage = single(matrix(component, 1)) .* i + ...
    single(matrix(component, 2)) .* j + ...
    single(matrix(component, 3)) .* k + ...
    single(matrix(component, 4));
