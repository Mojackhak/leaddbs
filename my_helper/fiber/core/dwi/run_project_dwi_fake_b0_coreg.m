function result = run_project_dwi_fake_b0_coreg(varargin)
% Run project-agnostic Synb0/eddy preprocessing and fake B0 UI-coreg staging.

p = inputParser;
p.FunctionName = 'run_project_dwi_fake_b0_coreg';
p.addParameter('StudyRoot', '', @(x) ischar(x) || isstring(x));
p.addParameter('RepoDir', '', @(x) ischar(x) || isstring(x));
p.addParameter('ImportLog', '', @(x) ischar(x) || isstring(x));
p.addParameter('SubjectIds', {}, @(x) iscell(x) || isstring(x) || ischar(x));
p.addParameter('PilotSubject', '', @(x) ischar(x) || isstring(x));
p.addParameter('AnchorModality', 'T2w', @(x) ischar(x) || isstring(x));
p.addParameter('PhaseEncodingVector', [0 1 0], @(x) isnumeric(x) && numel(x) == 3);
p.addParameter('DefaultTotalReadoutTime', 0.05, @(x) isnumeric(x) && isscalar(x) && x >= 0);
p.addParameter('FreeSurferLicense', '', @(x) ischar(x) || isstring(x));
p.addParameter('Synb0MinDockerMemoryGB', 12, @(x) isnumeric(x) && isscalar(x) && x >= 0);
p.addParameter('Force', false, @(x) islogical(x) || isnumeric(x));
p.parse(varargin{:});
opts = p.Results;

repoDir = resolve_repo_dir_from_option(opts.RepoDir);
addpath(genpath(repoDir));

subjectIds = opts.SubjectIds;
pilotSubject = char(string(opts.PilotSubject));
if ~isempty(pilotSubject)
    subjectIds = {pilotSubject};
end

result = mh_fiber_register_imported_dwi_batch( ...
    'StudyRoot', char(string(opts.StudyRoot)), ...
    'RepoDir', repoDir, ...
    'ImportLog', char(string(opts.ImportLog)), ...
    'SubjectIds', subjectIds, ...
    'AnchorModality', char(string(opts.AnchorModality)), ...
    'CoregistrationTag', 'dwi_synb0_fakeb0', ...
    'CoregistrationMethod', 'ANTs', ...
    'DistortionCorrection', 'synb0', ...
    'PhaseEncodingVector', double(opts.PhaseEncodingVector(:)'), ...
    'DefaultTotalReadoutTime', double(opts.DefaultTotalReadoutTime), ...
    'FreeSurferLicense', char(string(opts.FreeSurferLicense)), ...
    'Synb0MinDockerMemoryGB', double(opts.Synb0MinDockerMemoryGB), ...
    'AllowT1Fallback', false, ...
    'RunCoregistration', false, ...
    'GenerateOptionalDwiQc', true, ...
    'Force', logical(opts.Force));
end

function repoDir = resolve_repo_dir_from_option(repoDir)
repoDir = char(string(repoDir));
if ~isempty(repoDir)
    return;
end

repoDir = mh_util_resolve_repo_dir(mfilename('fullpath'));
if ~isfile(fullfile(repoDir, 'ea_normalize.m'))
    error('run_project_dwi_fake_b0_coreg:RepoRootNotFound', ...
        'Could not resolve Lead-DBS repository root. Provide RepoDir explicitly.');
end
end
