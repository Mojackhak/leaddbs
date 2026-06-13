function [runOptions, context] = ea_norm_refine_prepare(options)
% Prepare a normalization run for shared cross-method refinement.

runOptions = options;
context = default_context(options);

prior = ea_norm_get_transform_pair(options);
context.prior = prior;

if prior.found
    context.mode = select_refine_mode(options);
else
    context.mode = 'start_from_scratch';
end

if strcmp(context.mode, 'cancelled')
    context.cancelled = true;
    return;
end

if strcmp(context.mode, 'refine') && ~prior.found
    context.mode = 'start_from_scratch';
end

if strcmp(context.mode, 'refine')
    assert_fnirt_refine_allowed(options, context);
    [runOptions, context] = prepare_refine_inputs(options, context);
else
    ea_norm_refine_cleanup_current(options);
end

runOptions.normalize.refineContext = context;


function context = default_context(options)

context = struct;
context.mode = 'start_from_scratch';
context.method = options.normalize.method;
context.prior = struct;
context.active = false;
context.tempDir = '';
context.prewarpedAnatDir = '';
context.residualNormDir = '';
context.residualTransformDir = '';
context.residualForwardBaseName = '';
context.residualInverseBaseName = '';
context.forwardReference = get_anchor_template(options);
context.inverseReference = options.subj.coreg.anat.preop.(options.subj.AnchorModality);
context.priorForwardSource = options.subj.coreg.anat.preop.(options.subj.AnchorModality);
context.priorInverseSource = context.forwardReference;
context.residualForwardSource = '';
context.residualInverseSource = context.forwardReference;
context.residualInverseReference = '';
context.finalTransformFormat = ea_norm_method_transform_format(options.normalize.method);
context.cancelled = false;


function mode = select_refine_mode(options)

explicitMode = get_explicit_refine_mode(options);
if ~isempty(explicitMode)
    mode = explicitMode;
    return;
end

if usejava('desktop') && feature('ShowFigureWindows')
    answer = questdlg( ...
        ['A valid normalization transform already exists for this subject and template space. ', ...
         'Do you want to refine it with the selected normalization method or start from scratch?'], ...
        'Existing normalization transform found', ...
        'Refine', 'Start from scratch', 'Start from scratch');

    if isempty(answer)
        mode = 'cancelled';
    elseif strcmpi(answer, 'Refine')
        mode = 'refine';
    else
        mode = 'start_from_scratch';
    end
else
    if requests_refine_in_nodisplay(options)
        mode = 'refine';
    else
        ea_cprintf('CmdWinWarnings', ...
            'MATLAB nodisplay mode detected. Automatically selecting "Start from scratch" for normalization.\n');
        mode = 'start_from_scratch';
    end
end


function mode = get_explicit_refine_mode(options)

mode = '';

if ~isfield(options, 'normalize')
    return;
end

if isfield(options.normalize, 'refineMode')
    mode = normalize_mode_value(options.normalize.refineMode);
elseif isfield(options.normalize, 'refine_mode')
    mode = normalize_mode_value(options.normalize.refine_mode);
elseif isfield(options.normalize, 'refine') && isstruct(options.normalize.refine) && ...
        isfield(options.normalize.refine, 'mode')
    mode = normalize_mode_value(options.normalize.refine.mode);
end


function mode = normalize_mode_value(value)

mode = '';

if ~(ischar(value) || isstring(value))
    return;
end

value = lower(strtrim(char(value)));

if ismember(value, {'refine', 'reuse', 'build upon', 'build_upon'})
    mode = 'refine';
elseif ismember(value, {'start', 'scratch', 'start from scratch', 'start_from_scratch', 'overwrite'})
    mode = 'start_from_scratch';
end


function tf = requests_refine_in_nodisplay(options)

explicitMode = get_explicit_refine_mode(options);
if strcmp(explicitMode, 'refine')
    tf = true;
    return;
end

try
    tf = options.prefs.machine.normsettings.ants_usepreexisting == 2;
catch
    tf = false;
end


function assert_fnirt_refine_allowed(options, context)

if ~strcmp(context.prior.format, 'fnirt') && ...
        ~strcmp(ea_norm_method_transform_format(options.normalize.method), 'fnirt')
    return;
end

if isfield(options.normalize, 'refineAllowFnirtConversion') && options.normalize.refineAllowFnirtConversion
    return;
end

ea_error(['Cross-method refinement involving FNIRT requires FSL-to-ANTs displacement conversion, ', ...
    'which is disabled by default because it must be validated for the current image geometry. ', ...
    'Choose "Start from scratch" or set options.normalize.refineAllowFnirtConversion = true after validation.'], ...
    showdlg=false, simpleStack=true);


function [runOptions, context] = prepare_refine_inputs(options, context)

context.active = true;
context.finalTransformFormat = 'ants';
context.tempDir = fullfile(ea_getleadtempdir, ['norm_refine_', ea_generate_uuid]);
context.prewarpedAnatDir = fullfile(context.tempDir, 'coregistration', 'anat');
context.residualNormDir = fullfile(context.tempDir, 'normalization', 'anat');
context.residualTransformDir = fullfile(context.tempDir, 'normalization', 'transformations');
ea_mkdir(context.prewarpedAnatDir);
ea_mkdir(context.residualNormDir);
ea_mkdir(context.residualTransformDir);

runOptions = options;
preopFields = fieldnames(options.subj.coreg.anat.preop);

for fieldIndex = 1:numel(preopFields)
    field = preopFields{fieldIndex};
    source = options.subj.coreg.anat.preop.(field);
    target = make_temp_bids_path(source, context.prewarpedAnatDir, 'refineInput');
    reference = match_template_safely(source, options);

    ea_norm_refine_apply_pair(options, context.prior, source, target, false, reference);
    runOptions.subj.coreg.anat.preop.(field) = target;
end

if isfield(options.subj.norm.anat, 'preop')
    normFields = fieldnames(options.subj.norm.anat.preop);
    for fieldIndex = 1:numel(normFields)
        field = normFields{fieldIndex};
        runOptions.subj.norm.anat.preop.(field) = ...
            make_temp_bids_path(options.subj.norm.anat.preop.(field), context.residualNormDir, 'residualNorm');
    end
end

context.residualInverseReference = runOptions.subj.coreg.anat.preop.(options.subj.AnchorModality);
context.residualForwardSource = context.residualInverseReference;

subjectLabel = get_subject_label(options);
spaceLabel = ea_getspace;
context.residualForwardBaseName = fullfile(context.residualTransformDir, ...
    [subjectLabel, '_from-anchorNative_to-', spaceLabel, '_desc-residual']);
context.residualInverseBaseName = fullfile(context.residualTransformDir, ...
    [subjectLabel, '_from-', spaceLabel, '_to-anchorNative_desc-residual']);

runOptions.subj.norm.transform.forwardBaseName = context.residualForwardBaseName;
runOptions.subj.norm.transform.inverseBaseName = context.residualInverseBaseName;
runOptions.normalize.deferApply = true;


function target = make_temp_bids_path(source, targetDir, desc)

if isBIDSFileName(source)
    target = setBIDSEntity(source, 'dir', targetDir, 'desc', desc);
else
    [~, name, ext] = ea_niifileparts(source);
    if isempty(ext)
        ext = '.nii';
    end
    target = fullfile(targetDir, [name, '_desc-', desc, ext]);
end


function reference = match_template_safely(source, options)

try
    if isfield(options, 'bids') && isfield(options.bids, 'spacedef')
        reference = ea_matchTemplate(source, options.bids.spacedef);
    else
        reference = ea_matchTemplate(source);
    end
catch
    reference = get_anchor_template(options);
end


function reference = get_anchor_template(options)

try
    reference = ea_matchTemplate(options.subj.coreg.anat.preop.(options.subj.AnchorModality), options.bids.spacedef);
catch
    reference = [ea_space, options.primarytemplate, '.nii'];
end


function label = get_subject_label(options)

try
    parsed = parseBIDSFilePath(options.subj.coreg.anat.preop.(options.subj.AnchorModality));
    label = ['sub-', parsed.sub];
catch
    label = options.patientname;
end


function ea_norm_refine_apply_pair(options, pair, source, target, useinverse, reference)

if strcmp(pair.format, 'fnirt')
    if useinverse
        transform = pair.inverse;
    else
        transform = pair.forward;
    end
    ea_fsl_apply_normalization(options, {source}, {target}, useinverse, reference, transform, 'trilinear');
else
    if useinverse
        transform = pair.inverse;
    else
        transform = pair.forward;
    end
    ea_ants_apply_transforms(options, {source}, {target}, useinverse, reference, transform, 'LanczosWindowedSinc');
end
