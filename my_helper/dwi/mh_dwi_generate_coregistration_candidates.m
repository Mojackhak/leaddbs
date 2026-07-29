function result = mh_dwi_generate_coregistration_candidates(configPath)
% Generate isolated SPM44 and BRAINSFit44 b0 coregistration candidates.

configPath = char(string(configPath));
if ~isfile(configPath)
    error('mh_dwi_generate_coregistration_candidates:MissingConfig', ...
        'Configuration does not exist: %s', configPath);
end

config = jsondecode(fileread(configPath));
validate_config(config);
candidates = config.candidates;
if iscell(candidates)
    candidates = [candidates{:}];
end

records = repmat(empty_record(), numel(candidates), 1);
for index = 1:numel(candidates)
    records(index) = generate_candidate(candidates(index));
end

result = struct();
result.schema_version = 1;
result.config_path = configPath;
result.config_sha256 = mh_fiber_file_sha256(configPath);
result.status = 'complete';
result.candidates = records;

summaryPath = char(string(config.summary_path));
summaryParent = fileparts(summaryPath);
if ~isempty(summaryParent) && ~isfolder(summaryParent)
    mkdir(summaryParent);
end
if isfile(summaryPath)
    error('mh_dwi_generate_coregistration_candidates:SummaryExists', ...
        'Summary already exists: %s', summaryPath);
end
write_json(summaryPath, result);
fprintf('Coregistration candidate summary written to:\n%s\n', summaryPath);
end

function record = generate_candidate(candidate)
label = char(string(candidate.label));
subjectId = char(string(candidate.subject_id));
b0Path = char(string(candidate.b0));
anchorPath = char(string(candidate.anchor_native_t1));
outputRoot = char(string(candidate.output_root));

if ~isfile(b0Path)
    error('mh_dwi_generate_coregistration_candidates:MissingB0', ...
        'Corrected b0 does not exist: %s', b0Path);
end
if ~isfile(anchorPath)
    error('mh_dwi_generate_coregistration_candidates:MissingAnchor', ...
        'anchorNative T1 does not exist: %s', anchorPath);
end
if isfolder(outputRoot) || isfile(outputRoot)
    error('mh_dwi_generate_coregistration_candidates:OutputExists', ...
        'Candidate output already exists: %s', outputRoot);
end
if is_formal_coregistration_path(outputRoot, subjectId)
    error('mh_dwi_generate_coregistration_candidates:FormalOutputRejected', ...
        'Candidate output must not be the formal subject coregistration directory: %s', outputRoot);
end
mkdir(outputRoot);

record = empty_record();
record.label = label;
record.subject_id = subjectId;
record.b0 = artifact_record(b0Path);
record.anchor_native_t1 = artifact_record(anchorPath);
record.output_root = outputRoot;
record.spm = run_method('SPM', 'spm', candidate, outputRoot);
record.brainsfit = run_method('BRAINSFit', 'brainsfit', candidate, outputRoot);
record.status = 'complete';
end

function record = run_method(methodName, methodToken, candidate, outputRoot)
label = char(string(candidate.label));
subjectId = char(string(candidate.subject_id));
b0Path = char(string(candidate.b0));
anchorPath = char(string(candidate.anchor_native_t1));
methodRoot = fullfile(outputRoot, methodToken);
workRoot = fullfile(methodRoot, 'work');
mkdir(workRoot);

movingB0 = fullfile(workRoot, [sanitize_label(label), '_corrected_b0.nii']);
copyfile(b0Path, movingB0);
b0OnAnchor = fullfile(methodRoot, [subjectId, '_b0_on_anchorNative_T1w.nii']);
anchorOnB0 = fullfile(methodRoot, [subjectId, '_anchorNative_T1w_on_b0.nii']);

options = struct();
options.coregmr.method = methodName;
options.coregb0.addSyN = 0;
try
    affineFiles = ea_coregimages(options, movingB0, anchorPath, b0OnAnchor, {}, 1, [], 1);
catch ME
    if strcmp(methodToken, 'brainsfit') && is_methods_record_error(ME)
        affineFiles = expected_brainsfit_transforms(methodRoot, movingB0, anchorPath);
        if ~isfile(b0OnAnchor) || ~all(cellfun(@isfile, affineFiles))
            rethrow(ME);
        end
        warning('mh_dwi_generate_coregistration_candidates:MethodsRecordSkipped', ...
            ['BRAINSFit completed for %s, but the Lead-DBS methods recorder rejected ', ...
             'the isolated staging path. Registration artifacts were preserved.'], label);
    else
        rethrow(ME);
    end
end
if numel(affineFiles) ~= 2 || ~all(cellfun(@isfile, affineFiles))
    error('mh_dwi_generate_coregistration_candidates:MissingTransform', ...
        '%s did not return both transforms for %s.', methodName, label);
end

forwardNative = fullfile(methodRoot, sprintf( ...
    '%s_from-b0_to-anchorNative_desc-%s.mat', subjectId, methodToken));
inverseNative = fullfile(methodRoot, sprintf( ...
    '%s_from-anchorNative_to-b0_desc-%s.mat', subjectId, methodToken));
copyfile(affineFiles{1}, forwardNative);
copyfile(affineFiles{2}, inverseNative);

forward44 = fullfile(methodRoot, sprintf( ...
    '%s_from-b0_to-anchorNative_desc-%s44.mat', subjectId, methodToken));
inverse44 = fullfile(methodRoot, sprintf( ...
    '%s_from-anchorNative_to-b0_desc-%s44.mat', subjectId, methodToken));
forwardTmat = export_tmat(forwardNative, methodToken, forward44);
inverseTmat = export_tmat(inverseNative, methodToken, inverse44);

if strcmp(methodToken, 'brainsfit')
    resample_with_world_tmat(movingB0, anchorPath, anchorOnB0, ...
        inverseTmat, fullfile(workRoot, [subjectId, '_anchor_to_b0_spmapply.mat']));
else
    ea_apply_coregistration(movingB0, anchorPath, anchorOnB0, inverseNative, 'linear');
end
if ~isfile(b0OnAnchor) || ~isfile(anchorOnB0)
    error('mh_dwi_generate_coregistration_candidates:MissingResampledImage', ...
        '%s did not generate both resampled images for %s.', methodName, label);
end

b0OnAnchorPng = fullfile(methodRoot, [subjectId, '_b0_on_anchorNative_T1w.png']);
anchorOnB0Png = fullfile(methodRoot, [subjectId, '_anchorNative_T1w_on_b0.png']);
ea_gencheckregpair(b0OnAnchor, anchorPath, b0OnAnchorPng);
ea_gencheckregpair(anchorOnB0, movingB0, anchorOnB0Png);

record = struct();
record.method = methodName;
record.method_token = methodToken;
record.forward_transform = artifact_record(forwardNative);
record.inverse_transform = artifact_record(inverseNative);
record.forward_transform_44 = artifact_record(forward44);
record.inverse_transform_44 = artifact_record(inverse44);
record.b0_on_anchor_native_t1 = artifact_record(b0OnAnchor);
record.anchor_native_t1_on_b0 = artifact_record(anchorOnB0);
record.b0_on_anchor_native_t1_png = optional_artifact_record(b0OnAnchorPng);
record.anchor_native_t1_on_b0_png = optional_artifact_record(anchorOnB0Png);
record.forward_determinant = det(forwardTmat(1:3, 1:3));
record.inverse_determinant = det(inverseTmat(1:3, 1:3));
record.inverse_consistency_frobenius = norm(forwardTmat * inverseTmat - eye(4), 'fro');
record.status = 'complete';
end

function affineFiles = expected_brainsfit_transforms(methodRoot, movingB0, anchorPath)
[~, movingName] = ea_niifileparts(movingB0);
[~, anchorName] = ea_niifileparts(anchorPath);
affineFiles = { ...
    fullfile(methodRoot, [movingName, '2', anchorName, '_brainsfit.mat']); ...
    fullfile(methodRoot, [anchorName, '2', movingName, '_brainsfit.mat'])};
end

function tf = is_methods_record_error(exception)
stackNames = string({exception.stack.name});
tf = any(stackNames == "ea_methods") && ...
    contains(string(exception.message), "Subject ID");
end

function resample_with_world_tmat(fixedPath, movingPath, outputPath, tmat, transformPath)
movingmat = spm_get_space(movingPath);
fixedmat = spm_get_space(fixedPath);
spmaffine = tmat * movingmat;
save(transformPath, 'spmaffine', 'movingmat', 'fixedmat', 'tmat');
ea_spm_apply_coregistration(fixedPath, movingPath, outputPath, transformPath, 1);
end

function tmat = export_tmat(nativePath, methodToken, outputPath)
payload = load(nativePath);
switch methodToken
    case 'spm'
        if ~isfield(payload, 'tmat')
            error('SPM transform does not contain tmat: %s', nativePath);
        end
        tmat = double(payload.tmat);
    case 'brainsfit'
        required = {'AffineTransform_double_3_3', 'fixed'};
        if ~all(isfield(payload, required))
            error('BRAINSFit transform is incomplete: %s', nativePath);
        end
        tmat = double(ea_antsmat2mat( ...
            payload.AffineTransform_double_3_3, payload.fixed));
    otherwise
        error('Unsupported candidate method token: %s', methodToken);
end
if ~isequal(size(tmat), [4, 4]) || any(~isfinite(tmat), 'all')
    error('Invalid 4-by-4 transform generated from: %s', nativePath);
end
save(outputPath, 'tmat');
end

function validate_config(config)
required = {'schema_version', 'summary_path', 'candidates'};
if ~isstruct(config) || ~all(isfield(config, required))
    error('mh_dwi_generate_coregistration_candidates:InvalidConfig', ...
        'Configuration must contain schema_version, summary_path, and candidates.');
end
if config.schema_version ~= 1
    error('mh_dwi_generate_coregistration_candidates:InvalidSchema', ...
        'schema_version must equal 1.');
end
if isempty(config.candidates)
    error('mh_dwi_generate_coregistration_candidates:NoCandidates', ...
        'candidates must not be empty.');
end
requiredCandidate = {'label', 'subject_id', 'b0', 'anchor_native_t1', 'output_root'};
candidates = config.candidates;
if iscell(candidates)
    candidates = [candidates{:}];
end
for index = 1:numel(candidates)
    if ~isstruct(candidates(index)) || ~all(isfield(candidates(index), requiredCandidate))
        error('mh_dwi_generate_coregistration_candidates:InvalidCandidate', ...
            'Each candidate must contain label, subject_id, b0, anchor_native_t1, and output_root.');
    end
end
end

function tf = is_formal_coregistration_path(path, subjectId)
normalized = strrep(char(string(path)), '\\', '/');
pattern = ['/derivatives/leaddbs/sub-', regexptranslate('escape', subjectId), '/coregistration'];
tf = ~isempty(regexp(normalized, pattern, 'once')) && ...
    isempty(regexp(normalized, '/import_logs/', 'once'));
end

function value = sanitize_label(value)
value = regexprep(char(string(value)), '[^A-Za-z0-9._-]+', '_');
end

function record = artifact_record(path)
record = struct();
record.path = char(string(path));
record.bytes = file_bytes(path);
record.sha256 = mh_fiber_file_sha256(path);
end

function record = optional_artifact_record(path)
if isfile(path)
    record = artifact_record(path);
else
    record = struct('path', char(string(path)), 'bytes', 0, 'sha256', '');
end
end

function bytes = file_bytes(path)
info = dir(path);
if isempty(info)
    error('Artifact does not exist: %s', path);
end
bytes = info(1).bytes;
end

function record = empty_record()
record = struct( ...
    'label', '', ...
    'subject_id', '', ...
    'b0', struct(), ...
    'anchor_native_t1', struct(), ...
    'output_root', '', ...
    'spm', struct(), ...
    'brainsfit', struct(), ...
    'status', '');
end

function write_json(path, value)
text = jsonencode(value, PrettyPrint=true);
fid = fopen(path, 'w');
if fid < 0
    error('Could not open JSON output: %s', path);
end
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', text);
end
