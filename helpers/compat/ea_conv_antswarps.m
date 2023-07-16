function ea_conv_antswarps(transform_file_name, reference, float)
% switches ants transform extenstion between .h5 and .nii.gz

[~,~,ext] = fileparts(transform_file_name);

switch ext
    case '.gz'
        ext = '.nii.gz';
        out_ext = '.h5';
    case '.h5'
        out_ext = '.nii.gz';
    otherwise
        error(['Unrecognized ANTs transform file extension: ' ext])
end

out_file_name = strrep(transform_file_name, ext, out_ext);

antsdir=[ea_getearoot,'ext_libs',filesep,'ANTs',filesep];
applyTransforms = ea_path_helper([antsdir, 'antsApplyTransforms', ea_getBinExt]);


cmd = [applyTransforms ' -r ' ea_path_helper(reference) ' -t ' ea_path_helper(transform_file_name) ' -o [' ea_path_helper(out_file_name) ',1]'];

if exist('float', 'var')
    if ischar(float) && strcmp(float, 'float') || float
        cmd = [cmd, ' --float'];
    end
end

cmd = [cmd, ' -v 1'];

if ~ispc
    system(['bash -c "', cmd, '"']);
else
    system(cmd);
end

ea_delete(transform_file_name)

