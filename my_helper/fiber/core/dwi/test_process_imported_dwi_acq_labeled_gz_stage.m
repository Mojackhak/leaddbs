% Validate staging of acquisition-labeled gzipped raw DWI into formal basename.

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
rawNii = fullfile(rawDwiDir, [sourceBase, '.nii']);
rawData = reshape(single(1:(2 * 2 * 2 * 2)), [2 2 2 2]);
niftiwrite(rawData, rawNii, 'Compressed', false);
gzip(rawNii);
delete(rawNii);

fid = fopen(fullfile(rawDwiDir, [sourceBase, '.json']), 'w');
assert(fid > 0, 'Could not create raw JSON.');
fprintf(fid, '{"PhaseEncodingDirection":"j","TotalReadoutTime":0.05}');
fclose(fid);
writematrix([0 1000], fullfile(rawDwiDir, [sourceBase, '.bval']), ...
    'FileType', 'text', 'Delimiter', ' ');
writematrix([0 1; 0 0; 0 0], fullfile(rawDwiDir, [sourceBase, '.bvec']), ...
    'FileType', 'text', 'Delimiter', ' ');

anchorT2 = fullfile(anatDir, ...
    [patientName, '_ses-preop_space-anchorNative_desc-preproc_acq-iso_T2w.nii']);
touch_file(anchorT2);

jobSpec = mh_fiber_dwi_bids_jobspec(studyRoot, subjectId, ...
    'CoregistrationTag', 'dwi_synb0_fakeb0', ...
    'AnchorModality', 'T2w');

row = mh_fiber_process_imported_dwi(jobSpec, struct( ...
    'DistortionCorrection', 'none', ...
    'RunCoregistration', false, ...
    'GenerateOptionalDwiQc', false, ...
    'Force', true));

expectedDwi = fullfile(studyRoot, 'derivatives', 'leaddbs', patientName, ...
    'preprocessing', 'dwi', [patientName, '_ses-preop_dwi.nii']);
unexpectedDwi = fullfile(studyRoot, 'derivatives', 'leaddbs', patientName, ...
    'preprocessing', 'dwi', [sourceBase, '.nii']);

assert(strcmp(row.status, 'staged'), ...
    'Processing should stage the acquisition-labeled gzipped DWI.');
assert(isfile(expectedDwi), ...
    'Staged DWI was not written with the formal output basename.');
assert(~isfile(unexpectedDwi), ...
    'Staging should not leave an acquisition-labeled DWI derivative.');
assert(strcmp(row.staged_dwi, expectedDwi), ...
    'Status row should report the formal staged DWI path.');

fprintf('Acquisition-labeled gzipped DWI staging test passed.\n');

function touch_file(path)
fid = fopen(path, 'w');
assert(fid > 0, 'Could not create test file: %s', path);
fclose(fid);
end
