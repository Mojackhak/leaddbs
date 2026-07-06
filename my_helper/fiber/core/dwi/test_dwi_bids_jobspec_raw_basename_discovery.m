% Validate BIDS DWI job spec discovery for acquisition-labeled raw DWI files.

repoDir = fileparts(fileparts(fileparts(fileparts(fileparts(mfilename('fullpath'))))));
addpath(genpath(repoDir));

workDir = tempname;
mkdir(workDir);
cleanupObj = onCleanup(@() mh_fiber_cleanup_temp_dir(workDir));

studyRoot = fullfile(workDir, 'study');
subjectId = 'Meige001';
patientName = ['sub-', subjectId];
rawDwiDir = fullfile(studyRoot, 'rawdata', patientName, 'ses-preop', 'dwi');
anatDir = fullfile(studyRoot, 'derivatives', 'leaddbs', patientName, ...
    'coregistration', 'anat');
mh_util_make_dir(rawDwiDir);
mh_util_make_dir(anatDir);

sourceBase = [patientName, '_ses-preop_acq-ax_dwi'];
touch_file(fullfile(rawDwiDir, [sourceBase, '.nii.gz']));
touch_file(fullfile(rawDwiDir, [sourceBase, '.json']));
touch_file(fullfile(rawDwiDir, [sourceBase, '.bval']));
touch_file(fullfile(rawDwiDir, [sourceBase, '.bvec']));

anchorT2 = fullfile(anatDir, ...
    [patientName, '_ses-preop_space-anchorNative_desc-preproc_acq-iso_T2w.nii']);
touch_file(anchorT2);

jobSpec = mh_fiber_dwi_bids_jobspec(studyRoot, subjectId, ...
    'CoregistrationTag', 'dwi_synb0_fakeb0', ...
    'AnchorModality', 'T2w');

assert(strcmp(jobSpec.sourceBase, sourceBase), ...
    'jobSpec.sourceBase should record the discovered raw DWI basename.');
assert(strcmp(jobSpec.paths.rawDwiGz, fullfile(rawDwiDir, [sourceBase, '.nii.gz'])), ...
    'rawDwiGz did not resolve to the acquisition-labeled DWI.');
assert(strcmp(jobSpec.paths.rawJson, fullfile(rawDwiDir, [sourceBase, '.json'])), ...
    'rawJson did not follow the acquisition-labeled DWI basename.');
assert(strcmp(jobSpec.paths.rawBval, fullfile(rawDwiDir, [sourceBase, '.bval'])), ...
    'rawBval did not follow the acquisition-labeled DWI basename.');
assert(strcmp(jobSpec.paths.rawBvec, fullfile(rawDwiDir, [sourceBase, '.bvec'])), ...
    'rawBvec did not follow the acquisition-labeled DWI basename.');
assert(strcmp(jobSpec.paths.dwi, fullfile(studyRoot, 'derivatives', 'leaddbs', ...
    patientName, 'preprocessing', 'dwi', [patientName, '_ses-preop_dwi.nii'])), ...
    'Formal staged DWI output should remain acquisition-label-free.');

fprintf('DWI BIDS job spec raw basename discovery test passed.\n');

function touch_file(path)
fid = fopen(path, 'w');
assert(fid > 0, 'Could not create test file: %s', path);
fclose(fid);
end
