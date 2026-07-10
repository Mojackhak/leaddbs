function summary = mh_fiber_dwi_validate_jobspec(jobSpec, varargin)
% Validate one resolved DWI job without writing derivatives.

p = inputParser;
p.addRequired('jobSpec', @isstruct);
p.addParameter('RequireT1', false, @(x) islogical(x) || isnumeric(x));
p.parse(jobSpec, varargin{:});
requireT1 = logical(p.Results.RequireT1);

required = {'subjectId', 'sourceBase', 'paths', 'anchorAnat', ...
    't1Anat', 'normalizationForward'};
for i = 1:numel(required)
    if ~isfield(jobSpec, required{i})
        error('mh_fiber_dwi_validate_jobspec:InvalidJobSpec', ...
            'Missing jobSpec field: %s', required{i});
    end
end
if ~isstruct(jobSpec.paths) || ~isscalar(jobSpec.paths)
    error('mh_fiber_dwi_validate_jobspec:InvalidJobSpec', ...
        'jobSpec.paths must be a scalar struct.');
end
paths = jobSpec.paths;
requiredPaths = {'subjectDir', 'rawDwiGz', 'rawDwiNii', 'rawJson', ...
    'rawBval', 'rawBvec'};
for i = 1:numel(requiredPaths)
    if ~isfield(paths, requiredPaths{i})
        error('mh_fiber_dwi_validate_jobspec:InvalidJobSpec', ...
            'Missing jobSpec.paths field: %s', requiredPaths{i});
    end
end

if ~isfolder(paths.subjectDir)
    error('mh_fiber_dwi_validate_jobspec:MissingInput', ...
        'Subject derivative directory does not exist: %s', paths.subjectDir);
end
rawDwi = first_existing({paths.rawDwiGz, paths.rawDwiNii});
if isempty(rawDwi)
    error('mh_fiber_dwi_validate_jobspec:MissingInput', ...
        'Raw DWI NIfTI does not exist for subject %s.', jobSpec.subjectId);
end
must_be_file(paths.rawJson, 'raw DWI JSON');
must_be_file(paths.rawBval, 'raw DWI bval');
must_be_file(paths.rawBvec, 'raw DWI bvec');
must_be_file(jobSpec.anchorAnat, 'coregistration anchor');
if requireT1
    if isempty(char(string(jobSpec.t1Anat))) || ~isfile(jobSpec.t1Anat)
        error('mh_fiber_dwi_validate_jobspec:MissingT1', ...
            'Synb0 requires an anchorNative T1w image for subject %s.', ...
            jobSpec.subjectId);
    end
end

bvals = mh_fiber_load_bval(paths.rawBval);
bvecCount = mh_fiber_bvec_count(paths.rawBvec);
[nVolumes, geometry] = inspect_dwi(rawDwi);
if numel(bvals) ~= nVolumes || bvecCount ~= nVolumes
    error('mh_fiber_dwi_validate_jobspec:GradientMismatch', ...
        ['DWI volume, bval, and bvec counts must match for subject %s ', ...
        '(volumes=%d, bval=%d, bvec=%d).'], ...
        jobSpec.subjectId, nVolumes, numel(bvals), bvecCount);
end
b0Count = sum(bvals < 10);
if b0Count < 1
    error('mh_fiber_dwi_validate_jobspec:MissingB0', ...
        'No b0 volume with bval < 10 exists for subject %s.', jobSpec.subjectId);
end

summary = struct();
summary.subject = char(string(jobSpec.subjectId));
summary.rawDwi = rawDwi;
summary.dwiVolumes = nVolumes;
summary.bvalCount = numel(bvals);
summary.bvecCount = bvecCount;
summary.b0Count = b0Count;
summary.dimensions = geometry.dimensions;
summary.voxelSize = geometry.voxelSize;
summary.bvals = bvals;
end

function path = first_existing(candidates)
path = '';
for i = 1:numel(candidates)
    if isfile(candidates{i})
        path = candidates{i};
        return;
    end
end
end

function must_be_file(path, label)
if isempty(char(string(path))) || ~isfile(path)
    error('mh_fiber_dwi_validate_jobspec:MissingInput', ...
        'Missing %s: %s', label, char(string(path)));
end
end

function [nVolumes, geometry] = inspect_dwi(dwiPath)
inspectPath = dwiPath;
tempDir = '';
if endsWith(dwiPath, '.gz')
    tempDir = tempname;
    mkdir(tempDir);
    extracted = gunzip(dwiPath, tempDir);
    if isempty(extracted) || ~isfile(extracted{1})
        error('mh_fiber_dwi_validate_jobspec:InvalidNifti', ...
            'Could not decompress DWI NIfTI: %s', dwiPath);
    end
    inspectPath = extracted{1};
end
cleanupObj = onCleanup(@() mh_fiber_cleanup_temp_dir(tempDir));
try
    V = spm_vol(inspectPath);
catch ME
    error('mh_fiber_dwi_validate_jobspec:InvalidNifti', ...
        'Could not read DWI NIfTI %s: %s', dwiPath, ME.message);
end
nVolumes = numel(V);
geometry = struct();
geometry.dimensions = double(V(1).dim(1:3));
geometry.voxelSize = sqrt(sum(V(1).mat(1:3, 1:3).^2, 1));
end
