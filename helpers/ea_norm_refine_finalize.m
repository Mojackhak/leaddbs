function context = ea_norm_refine_finalize(options, runOptions, context)
% Compose residual and prior transforms into the final ANTs transform pair.

if ~strcmp(context.mode, 'refine')
    ea_norm_refine_update_log(options, context);
    return;
end

residualCandidates = ea_norm_get_transform_pair(runOptions);
residual = select_residual_pair(residualCandidates, runOptions.normalize.method);
if ~residual.found
    ea_error('Refinement failed because the residual normalization did not produce a complete transform pair.');
end

context.residual = residual;

priorForward = normalize_transform_to_ants(context.prior.forward, context.prior.format, ...
    context.priorForwardSource, context.forwardReference, fullfile(context.tempDir, 'prior_forward_ants.nii.gz'));
priorInverse = normalize_transform_to_ants(context.prior.inverse, context.prior.format, ...
    context.priorInverseSource, context.inverseReference, fullfile(context.tempDir, 'prior_inverse_ants.nii.gz'));
residualForward = normalize_transform_to_ants(residual.forward, residual.format, ...
    context.residualForwardSource, context.forwardReference, fullfile(context.tempDir, 'residual_forward_ants.nii.gz'));
residualInverse = normalize_transform_to_ants(residual.inverse, residual.format, ...
    context.residualInverseSource, context.residualInverseReference, fullfile(context.tempDir, 'residual_inverse_ants.nii.gz'));

finalForward = [options.subj.norm.transform.forwardBaseName, 'ants.nii.gz'];
finalInverse = [options.subj.norm.transform.inverseBaseName, 'ants.nii.gz'];
tmpForward = fullfile(context.tempDir, 'final_forward_ants.nii.gz');
tmpInverse = fullfile(context.tempDir, 'final_inverse_ants.nii.gz');

compose_ants_transforms(context.forwardReference, tmpForward, {residualForward, priorForward});
compose_ants_transforms(context.inverseReference, tmpInverse, {priorInverse, residualInverse});

ea_mkdir(fileparts(finalForward));
ea_delete({finalForward; finalInverse});
movefile(tmpForward, finalForward);
movefile(tmpInverse, finalInverse);

context.final.forward = finalForward;
context.final.inverse = finalInverse;
context.final.format = 'ants';

ea_norm_refine_update_log(options, context);
ea_apply_normalization(options);

if isfolder(context.tempDir)
    ea_delete(context.tempDir);
end


function transform = normalize_transform_to_ants(transform, format, source, reference, output)

switch format
    case 'fnirt'
        ea_fnirt_warp_to_ants(transform, source, reference, output);
        transform = output;
end


function compose_ants_transforms(reference, output, transforms)

basedir = [fileparts(which('ea_ants_apply_transforms')), filesep];
applyTransforms = ea_getExec([basedir, 'antsApplyTransforms'], escapePath = 1);

cmd = [applyTransforms, ...
    ' --verbose 1', ...
    ' --dimensionality 3', ...
    ' --float 1', ...
    ' --reference-image ', ea_path_helper(reference)];

for transformIndex = 1:numel(transforms)
    cmd = [cmd, ' --transform [', ea_path_helper(transforms{transformIndex}), ',0]']; %#ok<AGROW>
end

cmd = [cmd, ' --output [', ea_path_helper(output), ',1]'];

status = ea_runcmd(cmd);
if status
    ea_error('Failed to compose normalization refinement transforms.');
end


function residual = select_residual_pair(candidates, method)

residual = empty_pair;

if isempty(candidates)
    return;
end

targetMethod = ea_norm_method_transform_format(method);
candidateIndex = find(strcmp({candidates.method}, targetMethod), 1);

if isempty(candidateIndex) && isscalar(candidates)
    candidateIndex = 1;
end

if ~isempty(candidateIndex)
    residual = candidates(candidateIndex);
end


function pair = empty_pair

pair = struct( ...
    'found', false, ...
    'forward', '', ...
    'inverse', '', ...
    'suffix', '', ...
    'format', '', ...
    'method', '', ...
    'label', '', ...
    'modified', 0, ...
    'forwardModified', 0, ...
    'inverseModified', 0);
