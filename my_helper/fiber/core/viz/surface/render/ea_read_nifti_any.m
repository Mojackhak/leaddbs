function [Y, M, meta] = ea_read_nifti_any(niftiInput)
%EA_READ_NIFTI_ANY Read a NIfTI volume and affine from multiple input types.
%
%   [Y, M, meta] = EA_READ_NIFTI_ANY(niftiInput)
%
% Inputs
%   niftiInput can be:
%     1) A file path to a NIfTI image (.nii or .nii.gz)
%     2) An SPM volume struct (output of spm_vol)
%     3) An SPM nifti object (class 'nifti')
%
% Outputs
%   Y    : 3D volume (double)
%   M    : 4x4 affine matrix mapping voxel coordinates -> world (mm)
%   meta : struct with minimal provenance (source file, reader, etc.)
%
% Notes
%   - This helper prefers SPM (spm_vol/spm_read_vols) when available because
%     Lead-DBS depends on SPM conventions.
%   - For .nii.gz paths, the file is temporarily unzipped to a temp folder.
%   - The temp folder is removed after reading.
%
% Requirements (recommended)
%   - SPM12 on the MATLAB path.

    meta = struct();
    M = eye(4);

    % Case 1: file path input
    if ischar(niftiInput) || (isstring(niftiInput) && isscalar(niftiInput))
        srcPath = char(niftiInput);
        if ~exist(srcPath, 'file')
            error('EA_READ_NIFTI_ANY:FileNotFound', 'File not found: %s', srcPath);
        end

        meta.sourceFile = srcPath;
        [readPath, cleanupObj] = local_prepare_file(srcPath); %#ok<ASGLU>

        if exist('spm_vol', 'file') == 2 && exist('spm_read_vols', 'file') == 2
            V = spm_vol(readPath);
            Y = spm_read_vols(V);
            M = V.mat;
            meta.reader = 'spm_vol/spm_read_vols';
            meta.spm = V;
        else
            if exist('niftiinfo', 'file') ~= 2 || exist('niftiread', 'file') ~= 2
                error('EA_READ_NIFTI_ANY:NoReader', ...
                    ['Neither SPM (spm_vol) nor MATLAB niftiinfo/niftiread are available. ' ...
                     'Please add SPM12 (required by Lead-DBS) to the MATLAB path.']);
            end
            info = niftiinfo(readPath);
            Y = niftiread(info);
            Y = double(Y);

            if isfield(info, 'Transform') && ~isempty(info.Transform) && isprop(info.Transform, 'T')
                M = info.Transform.T;
            end

            meta.reader = 'niftiinfo/niftiread';
            meta.matlabInfo = info;
        end

        Y = double(Y);
        clear cleanupObj; % ensures the onCleanup triggers here if needed
        return;
    end

    % Case 2: SPM volume struct (spm_vol output)
    if isstruct(niftiInput) && isfield(niftiInput, 'fname') && isfield(niftiInput, 'mat')
        if exist('spm_read_vols', 'file') ~= 2
            error('EA_READ_NIFTI_ANY:MissingSPM', ...
                'spm_read_vols was not found. Please add SPM12 to the MATLAB path.');
        end
        V = niftiInput;
        Y = spm_read_vols(V);
        Y = double(Y);
        M = V.mat;

        meta.reader = 'spm_read_vols';
        meta.sourceFile = V.fname;
        meta.spm = V;
        return;
    end

    % Case 3: SPM nifti object (class 'nifti')
    if exist('nifti', 'class') == 8 && isa(niftiInput, 'nifti')
        ni = niftiInput;

        % ni.dat is a file_array; indexing loads data on demand.
        Y = double(ni.dat(:,:,:));
        M = ni.mat;

        meta.reader = 'spm_nifti_object';
        meta.sourceFile = '';
        try
            if isfield(ni.dat, 'fname')
                meta.sourceFile = ni.dat.fname;
            end
        catch
        end
        meta.spmNifti = ni;
        return;
    end

    error('EA_READ_NIFTI_ANY:UnsupportedInput', ...
        ['Unsupported input type. Provide a file path, an SPM volume struct, ' ...
         'or an SPM nifti object.']);
end

function [readPath, cleanupObj] = local_prepare_file(srcPath)
%LOCAL_PREPARE_FILE Unzip .nii.gz to a temporary folder if needed.

    cleanupObj = [];
    readPath = srcPath;

    isGz = endsWith(lower(srcPath), '.gz');
    if ~isGz
        return;
    end

    tmpDir = tempname;
    mkdir(tmpDir);

    % Ensure temp folder is removed after reading.
    cleanupObj = onCleanup(@() local_cleanup_tmpdir(tmpDir));

    gunzip(srcPath, tmpDir);

    % Find the first .nii file in the temp folder.
    d = dir(fullfile(tmpDir, '*.nii'));
    if isempty(d)
        error('EA_READ_NIFTI_ANY:GunzipFailed', ...
            'gunzip did not produce a .nii file in: %s', tmpDir);
    end
    readPath = fullfile(tmpDir, d(1).name);
end

function local_cleanup_tmpdir(tmpDir)
%LOCAL_CLEANUP_TMPDIR Best-effort removal of a temporary folder.

    if exist(tmpDir, 'dir') ~= 7
        return;
    end
    try
        rmdir(tmpDir, 's');
    catch
        % Do nothing (best effort).
    end
end
