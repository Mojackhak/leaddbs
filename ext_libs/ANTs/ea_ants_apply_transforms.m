function ea_ants_apply_transforms(varargin)
% Wrapper for antsApplyTransforms used for reapplying coregistration
% (linear registration) and normalization (non-linear registration)

ea_libs_helper;

options = varargin{1};

useinverse = 0;
storedD99Preset = false;

if nargin == 1
    [transformfiles, methodLog] = ea_gettransformfiles(options);
    storedD99Preset = isfield(methodLog, 'settings') && ...
        isfield(methodLog.settings, 'preset_id') && ...
        strcmp(methodLog.settings.preset_id, 'ea_antspreset_macaque_d99_deep');
    useBrainshift = (strcmp(options.subj.postopModality, 'MRI') || ...
        strcmp(options.subj.postopModality, 'CT')) && ...
        exist(options.subj.brainshift.transform.scrf, 'file');
    if useBrainshift && storedD99Preset && isfield(methodLog, 'downstream') && ...
            isfield(methodLog.downstream, 'brainshift') && ...
            isfield(methodLog.downstream.brainshift, 'requires_rerun') && ...
            methodLog.downstream.brainshift.requires_rerun
        useBrainshift = false;
        if isfile(options.subj.brainshift.log.method)
            brainshiftLog = loadjson(options.subj.brainshift.log.method);
            useBrainshift = isfield(brainshiftLog, 'approval') && brainshiftLog.approval == 1;
        end
    end

    preopFields = fieldnames(options.subj.coreg.anat.preop);
    input = cell(numel(preopFields), 1);
    output = cell(numel(preopFields), 1);
    for preopFile = 1:numel(preopFields)
        input{preopFile} = options.subj.coreg.anat.preop.(preopFields{preopFile});
        output{preopFile} = options.subj.norm.anat.preop.(preopFields{preopFile});
    end

    if strcmp(options.subj.postopModality, 'MRI')
        if useBrainshift % apply brainshift correction to postop files on the fly.
            fn=fieldnames(options.subj.coreg.anat.postop);
            for postopfile=1:length(fn)
                uuid=ea_generate_uuid;
                copyfile(options.subj.coreg.anat.postop.(fn{postopfile}),[ea_getleadtempdir,uuid,'.nii']);
                nii=ea_load_nii([ea_getleadtempdir,uuid,'.nii']);
                scrf=load(options.subj.brainshift.transform.scrf);
                nii.mat=scrf.mat*nii.mat;
                ea_write_nii(nii);
                input = [input; [ea_getleadtempdir,uuid,'.nii']];
            end
        else
            input = [input; struct2cell(options.subj.coreg.anat.postop)];
        end
        output = [output; struct2cell(options.subj.norm.anat.postop)];
    elseif strcmp(options.subj.postopModality, 'CT')
        if useBrainshift % apply brainshift correction to postop files on the fly.
            uuid=ea_generate_uuid;
            copyfile(options.subj.coreg.anat.postop.CT,[ea_getleadtempdir,uuid,'.nii']);
            nii=ea_load_nii([ea_getleadtempdir,uuid,'.nii']);
            scrf=load(options.subj.brainshift.transform.scrf);
            nii.mat=scrf.mat*nii.mat;
            ea_write_nii(nii);
            input = [input; [ea_getleadtempdir,uuid,'.nii']];
        else
            input = [input; options.subj.coreg.anat.postop.CT];
        end
        output = [output; options.subj.norm.anat.postop.CT];
    end
elseif nargin > 1 % manual application
    input = GetFullPath(varargin{2});
    output = GetFullPath(varargin{3});
    if ischar(input)
        input = {input};
    end
    if ischar(output)
        output = {output};
    end
    useinverse = varargin{4};
end

if nargin >= 5
    ref = varargin{5};
else
    ref = ''; % use defaults
end

if nargin >= 6
    transform = varargin{6};
else
    transform = ''; % use defaults
end

% Linear, NearestNeighbor, MultiLabel, Gaussian, BSpline
% CosineWindowedSinc, WelchWindowedSinc, HammingWindowedSinc, LanczosWindowedSinc
% GenericLabel (Recommanded for label image)
if nargin >= 7
    interp = varargin{7};
    if ~ischar(interp)
        switch interp
            case 0
                interp = 'NearestNeighbor';
            case 1
                interp = 'Linear';
            case -1
                interp = 'GenericLabel';
            otherwise
                interp = 'BSpline';
        end
    end
else
    if useinverse
        interp = 'GenericLabel';
    else
        interp = 'LanczosWindowedSinc';
    end
end

if nargin >= 8
    imageDim = varargin{8};
    if isnumeric(imageDim)
        imageDim = num2str(imageDim);
    end
else
    imageDim = '3';
end

% Image type (-e 0/1/2/3/4): scalar/vector/tensor/time-series/multichannel
if nargin == 9
    imageType = varargin{9};
    if isnumeric(imageType)
        imageType = num2str(imageType);
    end
else
    imageType = '0';
end

floatPrecision = '1';
if isempty(transform)
    if nargin ~= 1
        transformfiles = ea_gettransformfiles(options);
    end
    if useinverse
        transform = transformfiles.inverse;
    else
        transform = transformfiles.forward;
    end
end
if storedD99Preset
    interp = methodLog.settings.interpolation;
    floatPrecision = num2str(~strcmp(methodLog.settings.precision, 'double'));
end

basedir = [fileparts(mfilename('fullpath')), filesep];
applyTransforms = ea_getExec([basedir, 'antsApplyTransforms'], escapePath = 1);

for i = 1:length(input)
    if ~exist(input{i},'file')   % skip if unnormalized file doesn't exist
        fprintf('%s not found. Skip normalization...\n',input{i});
        continue
    end

    ea_mkdir(fileparts(output{i}));
    cmd = [applyTransforms, ...
        ' --verbose 1' ...
        ' --dimensionality ', imageDim, ...
        ' --input-image-type ', imageType, ...
        ' --float ', floatPrecision, ...
        ' --input ',ea_path_helper(input{i}), ...
        ' --output ',ea_path_helper(output{i})];

    if isempty(ref)
        if useinverse
            ref = options.subj.coreg.anat.preop.(options.subj.AnchorModality);
        else
            spacedef = ea_getspacedef;
            ref = [ea_space, spacedef.templates{1}, '.nii'];
        end
    end

    cmd = [cmd, ...
        ' --reference-image ',ea_path_helper(ref),...
        ' --transform [',ea_path_helper(transform),',0]'];

    if ~isempty(interp)
        cmd = [cmd, ' --interpolation ', interp];
    end

    [~, inputFileName] = ea_niifileparts(input{i});
    fprintf('\nRegister %s ...\n', inputFileName);

    status = ea_runcmd(cmd);
    if storedD99Preset && status ~= 0
        error('ea_ants_apply_transforms:CommandFailed', ...
            'ANTs normalization application failed for %s (exit status %d).', input{i}, status);
    end
end
