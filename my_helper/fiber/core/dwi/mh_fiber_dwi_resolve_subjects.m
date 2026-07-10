function subjects = mh_fiber_dwi_resolve_subjects(config)
% Resolve configured or automatically discovered standard BIDS DWI subjects.

if ~isstruct(config) || ~isfield(config, 'project') || ~isfield(config, 'subjects')
    error('mh_fiber_dwi_resolve_subjects:InvalidConfig', ...
        'Config must contain project and subjects mappings.');
end
studyRoot = char(string(config.project.study_root));
session = char(string(config.project.session));
mode = lower(char(string(config.subjects.mode)));

if strcmp(mode, 'explicit')
    subjects = cellstr(string(config.subjects.ids));
    subjects = reshape(subjects, 1, []);
elseif strcmp(mode, 'auto')
    subjects = discover_subjects(studyRoot, session);
else
    error('mh_fiber_dwi_resolve_subjects:InvalidMode', ...
        'subjects.mode must be auto or explicit.');
end

if isempty(subjects)
    error('mh_fiber_dwi_resolve_subjects:NoSubjects', ...
        'No DWI subjects were selected or discovered for ses-%s under %s.', ...
        session, studyRoot);
end
end

function subjects = discover_subjects(studyRoot, session)
rawRoot = fullfile(studyRoot, 'rawdata');
subjectDirs = dir(fullfile(rawRoot, 'sub-*'));
subjectDirs = subjectDirs([subjectDirs.isdir]);
subjectDirs = subjectDirs(~startsWith({subjectDirs.name}, '._'));
subjects = {};
for i = 1:numel(subjectDirs)
    dwiDir = fullfile(subjectDirs(i).folder, subjectDirs(i).name, ...
        ['ses-', session], 'dwi');
    nii = dir(fullfile(dwiDir, '*_dwi.nii'));
    niiGz = dir(fullfile(dwiDir, '*_dwi.nii.gz'));
    candidates = [nii(:); niiGz(:)];
    candidates = candidates(~startsWith({candidates.name}, '._'));
    if ~isempty(candidates)
        subjects{end + 1} = char(extractAfter(subjectDirs(i).name, 'sub-')); %#ok<AGROW>
    end
end
subjects = sort(unique(subjects, 'stable'));
end
