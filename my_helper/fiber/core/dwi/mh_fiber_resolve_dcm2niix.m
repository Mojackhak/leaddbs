function [dcm2niixPath, info] = mh_fiber_resolve_dcm2niix(varargin)
% Resolve a usable dcm2niix executable from Lead-DBS, Slicer, or PATH.

parser = inputParser;
parser.FunctionName = 'mh_fiber_resolve_dcm2niix';
parser.addParameter('RepoDir', '', @(x) ischar(x) || isstring(x));
parser.parse(varargin{:});
repoDir = char(string(parser.Results.RepoDir));
if isempty(repoDir)
    repoDir = mh_util_resolve_repo_dir(mfilename('fullpath'));
    if ~isfile(fullfile(repoDir, 'ea_normalize.m'))
        error('mh_fiber_resolve_dcm2niix:RepoDirNotFound', ...
            'Could not resolve Lead-DBS repository root. Provide RepoDir explicitly.');
    end
end

candidates = dcm2niix_candidates(repoDir);
for i = 1:numel(candidates)
    candidate = candidates{i};
    if isfile(candidate) && executable_works(candidate)
        dcm2niixPath = candidate;
        info = struct('Path', candidate, 'Source', candidate_source(candidate, repoDir));
        return;
    end
end

[status, out] = system('command -v dcm2niix');
if status == 0
    candidate = strtrim(out);
    if isfile(candidate) && executable_works(candidate)
        dcm2niixPath = candidate;
        info = struct('Path', candidate, 'Source', 'PATH');
        return;
    end
end

error('mh_fiber_resolve_dcm2niix:NotFound', ...
    'Could not locate a working dcm2niix executable.');
end

function candidates = dcm2niix_candidates(repoDir)
bundleDir = fullfile(repoDir, 'ext_libs', 'dcm2nii');
candidates = {};
switch computer
    case 'MACA64'
        candidates{end + 1} = fullfile(bundleDir, 'dcm2niix.maca64');
        candidates{end + 1} = fullfile(bundleDir, 'dcm2niix.maci64');
    case 'MACI64'
        candidates{end + 1} = fullfile(bundleDir, 'dcm2niix.maci64');
        candidates{end + 1} = fullfile(bundleDir, 'dcm2niix.maca64');
    case 'GLNXA64'
        candidates{end + 1} = fullfile(bundleDir, 'dcm2niix.glnxa64');
    case 'PCWIN64'
        candidates{end + 1} = fullfile(bundleDir, 'dcm2niix.exe');
end
candidates{end + 1} = '/Applications/Slicer.app/Contents/Extensions-34045/SlicerDcm2nii/lib/Slicer-5.10/qt-scripted-modules/Resources/bin/dcm2niix';
end

function tf = executable_works(path)
[status, ~] = system(sprintf('%s -h', mh_fiber_shell_quote(path)));
tf = status == 0;
end

function source = candidate_source(path, repoDir)
if startsWith(path, fullfile(repoDir, 'ext_libs', 'dcm2nii'))
    source = 'Lead-DBS bundled dcm2niix';
elseif startsWith(path, '/Applications/Slicer.app')
    source = 'Slicer dcm2niix';
else
    source = 'custom';
end
end
