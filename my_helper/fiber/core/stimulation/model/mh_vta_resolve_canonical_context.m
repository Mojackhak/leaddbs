function [context, cacheStatus] = mh_vta_resolve_canonical_context(task, runtime)
% Resolve immutable subject/lead context with process-local reuse.

if nargin < 2 || isempty(runtime)
    runtime = mh_vta_create_subject_runtime(task.subject_id);
end
sideIndex = side_to_index(task.hemisphere);
key = mh_vta_runtime_cache_key('subject_context', { ...
    mh_vta_canonical_path(task.subject_dir), ...
    mh_vta_canonical_path(task.reconstruction_path), ...
    upper(char(string(task.hemisphere))), ...
    double(task.reconstruction_lead_id), ...
    char(string(task.electrode_model))});
[base, hit] = mh_vta_runtime_cache_lookup( ...
    runtime, 'subject_context', key);
if hit
    cacheStatus = 'hit';
else
    base = resolve_base(task, sideIndex, runtime);
    mh_vta_runtime_cache_store(runtime, 'subject_context', key, base);
    cacheStatus = 'miss';
end

options = mh_vta_configure_canonical_options(base.options, task);
context = base;
context.options = options;
context.subject_context_key = key;
context.patient_gm_mask_signature = patient_gm_signature(options, task);
context.mni_reference = base.mni_reference;
end

function base = resolve_base(task, sideIndex, runtime)
subjectDir = char(string(task.subject_dir));
transformContext = mh_vta_resolve_transform_context( ...
    task, runtime);
options = transformContext.options;
options.root = [fileparts(subjectDir), filesep];
[~, options.patientname] = fileparts(subjectDir);
options.leadprod = 'dbs';
options.native = 1;
options.orignative = 1;
options.subj.recon.recon = char(string(task.reconstruction_path));
options.elmodel = char(string(task.electrode_model));
options = ea_resolve_elspec(options);

if double(task.reconstruction_lead_id) ~= sideIndex
    error('mh_vta:ReconstructionLeadMismatch', ...
        'reconstruction_lead_id does not match hemisphere %s.', ...
        char(string(task.hemisphere)));
end
options.elside = sideIndex;
try
    [~, trajectory, ~, actualModel] = ea_load_reconstruction(options);
catch ME
    wrapped = MException('mh_vta:InvalidReconstruction', ...
        'Could not load reconstruction lead %d.', sideIndex);
    wrapped = addCause(wrapped, ME);
    throw(wrapped);
end
if isempty(actualModel)
    error('mh_vta:InvalidReconstruction', ...
        'Reconstruction does not define an electrode model for lead %d.', ...
        sideIndex);
end
actual = char(string(actualModel));
expected = char(string(task.electrode_model));
if ~strcmp(actual, expected)
    error('mh_vta:ElectrodeModelMismatch', ...
        'Reconstruction model %s does not match task model %s.', ...
        actual, expected);
end
base = struct( ...
    'options', options, ...
    'side_index', sideIndex, ...
    'trajectory', {trajectory}, ...
    'native_anchor_path', ...
        options.subj.preopAnat.(options.subj.AnchorModality).coreg, ...
    'mni_reference', transformContext.mni_reference, ...
    'actual_electrode_model', actual);
end

function signature = patient_gm_signature(options, task)
base = fullfile(options.root, options.patientname, 'atlases', ...
    char(string(task.model.atlas_set)), 'gm_mask.nii');
if isfile([base, '.gz'])
    path = [base, '.gz'];
else
    path = base;
end
signature = mh_vta_file_signature(path);
end

function sideIndex = side_to_index(side)
if strcmpi(char(string(side)), 'R')
    sideIndex = 1;
else
    sideIndex = 2;
end
end
