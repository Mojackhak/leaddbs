% Register imported STN/SNr cohort DWI scans to Lead-DBS anchorNative T2.

repoDir = '/Users/mojackhu/Github/leaddbs';
cd(repoDir);
addpath(genpath(repoDir));

runMode = 'default';

switch runMode
    case 'default'
        subjectIds = {};
        coregistrationTag = 'dwi_t2';
        coregistrationMethod = 'ANTs';
        distortionCorrection = 'none';
        forceRun = false;
    case 'synb0_pilot'
        subjectIds = {'ChenMeiJu'};
        coregistrationTag = 'dwi_t2_synb0';
        coregistrationMethod = 'FLIRTBBR';
        distortionCorrection = 'synb0';
        forceRun = true;
    otherwise
        error('Unsupported runMode: %s', runMode);
end

args = { ...
    'StudyRoot', '/Volumes/VAL/STNSNr', ...
    'RepoDir', repoDir, ...
    'ImportLog', fullfile('/Volumes/VAL/STNSNr', 'derivatives', 'leaddbs', ...
        'import_logs', 'dwi_import_20260701_013240.csv'), ...
    'AnchorModality', 'T2w', ...
    'CoregistrationTag', coregistrationTag, ...
    'CoregistrationMethod', coregistrationMethod, ...
    'DistortionCorrection', distortionCorrection, ...
    'AllowT1Fallback', false, ...
    'RunCoregistration', true, ...
    'GenerateOptionalDwiQc', true, ...
    'Force', forceRun};

if ~isempty(subjectIds)
    args = [args, {'SubjectIds', subjectIds}];
end

result = mh_fiber_register_imported_dwi_batch(args{:});

fprintf('\nFinished STN/SNr DWI registration batch.\n');
fprintf('Status CSV: %s\n', result.statusCsv);
