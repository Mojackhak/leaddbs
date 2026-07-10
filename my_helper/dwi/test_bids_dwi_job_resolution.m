% Validate session-aware BIDS subject discovery, job specs, and preflight.

repoDir = fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(genpath(repoDir));

workDir = tempname;
mkdir(workDir);
cleanupObj = onCleanup(@() mh_fiber_cleanup_temp_dir(workDir));
studyRoot = fullfile(workDir, 'study');
session = 'research';

create_subject(studyRoot, 'Subject002', session, 'acq-ax', [0 1000]);
create_subject(studyRoot, 'Subject001', session, 'dir-AP', [0 1000]);

config = struct();
config.project = struct('study_root', studyRoot, 'session', session);
config.subjects = struct('mode', 'auto');
subjects = mh_fiber_dwi_resolve_subjects(config);
assert(isequal(subjects, {'Subject001', 'Subject002'}), ...
    'Auto discovery should return sorted subject IDs for the configured session.');

config.subjects = struct('mode', 'explicit', 'ids', {{'Subject002'}});
subjects = mh_fiber_dwi_resolve_subjects(config);
assert(isequal(subjects, {'Subject002'}), ...
    'Explicit selection should preserve only configured subjects.');

jobSpec = mh_fiber_dwi_bids_jobspec(studyRoot, 'Subject001', ...
    'Session', session, ...
    'CoregistrationTag', 'dwi_synb0_fakeb0', ...
    'AnchorModality', 'T2w', ...
    'RequireT1', true);
expectedRawDir = fullfile(studyRoot, 'rawdata', 'sub-Subject001', ...
    'ses-research', 'dwi');
assert(strcmp(jobSpec.paths.rawDwiDir, expectedRawDir), ...
    'Job spec should resolve the configured BIDS session.');
assert(strcmp(jobSpec.paths.outputBase, 'sub-Subject001_ses-research_dwi'), ...
    'Formal output basename should include the configured session.');
assert(contains(jobSpec.paths.fakeB0Coreg, ...
    'sub-Subject001_ses-research_space-anchorNative_desc-preproc_B0.nii'), ...
    'Lead-DBS B0 target should include the configured session.');
assert(strcmp(jobSpec.session, session), 'Job spec should record its session.');

summary = mh_fiber_dwi_validate_jobspec(jobSpec, 'RequireT1', true);
assert(summary.dwiVolumes == 2, 'Preflight should report two DWI volumes.');
assert(summary.bvalCount == 2 && summary.bvecCount == 2, ...
    'Preflight should report matching gradient counts.');
assert(summary.b0Count == 1, 'Preflight should report one b0 volume.');
assert(endsWith(summary.rawDwi, '_dir-AP_dwi.nii'), ...
    'Preflight should report the discovered acquisition-labeled DWI.');

create_subject(studyRoot, 'Ambiguous001', session, 'run-1', [0 1000]);
create_dwi_four_file_set(studyRoot, 'Ambiguous001', session, 'run-2', [0 1000]);
assert_error(@() mh_fiber_dwi_bids_jobspec(studyRoot, 'Ambiguous001', ...
    'Session', session, 'AnchorModality', 'T2w', 'RequireT1', true), ...
    'mh_fiber_dwi_bids_jobspec:AmbiguousRawDwi');

create_subject(studyRoot, 'Mismatch001', session, 'acq-ax', [0 1000 2000]);
mismatch = mh_fiber_dwi_bids_jobspec(studyRoot, 'Mismatch001', ...
    'Session', session, 'AnchorModality', 'T2w', 'RequireT1', true);
assert_error(@() mh_fiber_dwi_validate_jobspec(mismatch, 'RequireT1', true), ...
    'mh_fiber_dwi_validate_jobspec:GradientMismatch');

create_subject(studyRoot, 'NoB0001', session, 'acq-ax', [1000 1000]);
noB0 = mh_fiber_dwi_bids_jobspec(studyRoot, 'NoB0001', ...
    'Session', session, 'AnchorModality', 'T2w', 'RequireT1', true);
assert_error(@() mh_fiber_dwi_validate_jobspec(noB0, 'RequireT1', true), ...
    'mh_fiber_dwi_validate_jobspec:MissingB0');

create_subject(studyRoot, 'MissingJson001', session, 'acq-ax', [0 1000]);
missingJson = mh_fiber_dwi_bids_jobspec(studyRoot, 'MissingJson001', ...
    'Session', session, 'AnchorModality', 'T2w', 'RequireT1', true);
delete(missingJson.paths.rawJson);
assert_error(@() mh_fiber_dwi_validate_jobspec(missingJson, 'RequireT1', true), ...
    'mh_fiber_dwi_validate_jobspec:MissingInput');

create_subject(studyRoot, 'MissingT1001', session, 'acq-ax', [0 1000]);
missingT1 = mh_fiber_dwi_bids_jobspec(studyRoot, 'MissingT1001', ...
    'Session', session, 'AnchorModality', 'T2w', 'RequireT1', false);
delete(missingT1.t1Anat);
missingT1.t1Anat = '';
assert_error(@() mh_fiber_dwi_validate_jobspec(missingT1, 'RequireT1', true), ...
    'mh_fiber_dwi_validate_jobspec:MissingT1');

fprintf('BIDS DWI subject and job resolution test passed.\n');

function create_subject(studyRoot, subjectId, session, entity, bvals)
create_dwi_four_file_set(studyRoot, subjectId, session, entity, bvals);
patientName = ['sub-', subjectId];
sessionLabel = ['ses-', session];
anatDir = fullfile(studyRoot, 'derivatives', 'leaddbs', patientName, ...
    'coregistration', 'anat');
mh_util_make_dir(anatDir);
anatData = single(ones(2, 2, 2));
t1 = fullfile(anatDir, [patientName, '_', sessionLabel, ...
    '_space-anchorNative_desc-preproc_acq-iso_T1w.nii']);
t2 = fullfile(anatDir, [patientName, '_', sessionLabel, ...
    '_space-anchorNative_desc-preproc_acq-iso_T2w.nii']);
niftiwrite(anatData, t1, 'Compressed', false);
niftiwrite(anatData, t2, 'Compressed', false);
end

function create_dwi_four_file_set(studyRoot, subjectId, session, entity, bvals)
patientName = ['sub-', subjectId];
sessionLabel = ['ses-', session];
rawDir = fullfile(studyRoot, 'rawdata', patientName, sessionLabel, 'dwi');
mh_util_make_dir(rawDir);
base = [patientName, '_', sessionLabel, '_', entity, '_dwi'];
dwi = reshape(single(1:(2 * 2 * 2 * 2)), [2 2 2 2]);
niftiwrite(dwi, fullfile(rawDir, [base, '.nii']), 'Compressed', false);
write_text(fullfile(rawDir, [base, '.json']), ...
    '{"PhaseEncodingDirection":"j","TotalReadoutTime":0.05}');
writematrix(bvals, fullfile(rawDir, [base, '.bval']), ...
    'FileType', 'text', 'Delimiter', ' ');
writematrix([0 1; 0 0; 0 0], fullfile(rawDir, [base, '.bvec']), ...
    'FileType', 'text', 'Delimiter', ' ');
end

function assert_error(fn, expectedId)
try
    fn();
    error('test_bids_dwi_job_resolution:ExpectedError', ...
        'Expected error %s.', expectedId);
catch ME
    assert(strcmp(ME.identifier, expectedId), ...
        'Expected %s, received %s: %s', expectedId, ME.identifier, ME.message);
end
end

function write_text(path, content)
fid = fopen(path, 'w');
assert(fid >= 0, 'Could not create test file: %s', path);
cleanupObj = onCleanup(@() fclose(fid));
fprintf(fid, '%s', content);
end
