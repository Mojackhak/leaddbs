function result = mh_fiber_dwi_distortion_correction(paths, t1Image, varargin)
% Run optional Synb0-DISCO and eddy distortion correction for one DWI.

p = inputParser;
p.addRequired('paths', @isstruct);
p.addRequired('t1Image', @(x) ischar(x) || isstring(x));
p.addParameter('Force', false, @(x) islogical(x) || isnumeric(x));
p.addParameter('PhaseEncodingVector', [0 1 0], @(x) isnumeric(x) && numel(x) == 3);
p.addParameter('TotalReadoutTime', NaN, @(x) isnumeric(x) && isscalar(x));
p.addParameter('DefaultTotalReadoutTime', 0.05, @(x) isnumeric(x) && isscalar(x) && x >= 0);
p.addParameter('Synb0Image', 'leonyichencai/synb0-disco:v3.1', @(x) ischar(x) || isstring(x));
p.addParameter('Synb0ContainerEngine', 'auto', @(x) ischar(x) || isstring(x));
p.addParameter('FreeSurferLicense', '', @(x) ischar(x) || isstring(x));
p.addParameter('Synb0MinDockerMemoryGB', 12, @(x) isnumeric(x) && isscalar(x) && x >= 0);
p.parse(paths, t1Image, varargin{:});
opts = p.Results;

t1Image = char(string(t1Image));
opts.Force = logical(opts.Force);
opts.PhaseEncodingVector = double(opts.PhaseEncodingVector(:)');
opts.TotalReadoutTime = double(opts.TotalReadoutTime);
opts.DefaultTotalReadoutTime = double(opts.DefaultTotalReadoutTime);
opts.Synb0Image = char(string(opts.Synb0Image));
opts.Synb0ContainerEngine = char(string(opts.Synb0ContainerEngine));
opts.FreeSurferLicense = char(string(opts.FreeSurferLicense));
opts.Synb0MinDockerMemoryGB = double(opts.Synb0MinDockerMemoryGB);
must_be_file(paths.dwi, 'staged DWI');
must_be_file(paths.bval, 'bval');
must_be_file(paths.bvec, 'bvec');
must_be_file(paths.json, 'DWI JSON');
must_be_file(t1Image, 'anchorNative T1w');

workDir = fullfile(paths.dwiDir, 'work', 'synb0_eddy');
ensure_dir(workDir);

rawBase = [paths.patientName, '_ses-preop'];
distortedB0 = fullfile(workDir, [rawBase, '_desc-distorted_b0.nii']);
correctedPrefix = fullfile(workDir, [rawBase, '_desc-eddy']);
formalDwi = fullfile(paths.dwiDir, [rawBase, '_desc-preproc_dwi.nii']);
formalBval = fullfile(paths.dwiDir, [rawBase, '_desc-preproc_dwi.bval']);
formalBvec = fullfile(paths.dwiDir, [rawBase, '_desc-preproc_dwi.bvec']);
formalB0 = fullfile(paths.dwiDir, [rawBase, '_desc-preproc_b0.nii']);
synb0Acqparams = fullfile(workDir, 'synb0_acqparams.txt');

bvals = load_numeric_vector(paths.bval);
extract_mean_b0(paths.dwi, distortedB0, bvals, opts.Force);

[totalReadoutTime, readoutSource] = resolve_total_readout_time(paths.json, ...
    opts.TotalReadoutTime, opts.DefaultTotalReadoutTime);
write_synb0_acqparams(synb0Acqparams, opts.PhaseEncodingVector, totalReadoutTime);

synb0RunDir = resolve_synb0_run_dir(workDir, opts.Force);
synb0Result = ea_synb0(distortedB0, t1Image, synb0Acqparams, synb0RunDir, ...
    'ContainerEngine', opts.Synb0ContainerEngine, ...
    'Synb0Image', opts.Synb0Image, ...
    'FreeSurferLicense', opts.FreeSurferLicense, ...
    'MinDockerMemoryGB', opts.Synb0MinDockerMemoryGB, ...
    'Force', opts.Force);

maskImage = fullfile(workDir, [rawBase, '_desc-synb0_brain.nii']);
maskBase = strip_nii_ext(maskImage);
maskPath = [maskBase, '_mask.nii'];
if opts.Force || ~isfile(maskPath)
    ea_bet(synb0Result.syntheticB0, 1, maskImage, 0.5);
end
if ~isfile(maskPath) && isfile([maskPath, '.gz'])
    gunzip([maskPath, '.gz'], fileparts(maskPath));
end
must_be_file(maskPath, 'eddy brain mask');

eddyResult = ea_eddy(paths.dwi, maskPath, paths.bval, paths.bvec, synb0Result.topupPrefix, correctedPrefix, ...
    'PhaseEncodingVector', opts.PhaseEncodingVector, ...
    'TotalReadoutTime', totalReadoutTime, ...
    'Force', opts.Force, ...
    'UseDataIsShelled', true);

copy_or_gunzip(eddyResult.correctedDwi, formalDwi, opts.Force);
copyfile(paths.bval, formalBval, 'f');
copyfile(eddyResult.rotatedBvec, formalBvec, 'f');
extract_mean_b0(formalDwi, formalB0, bvals, opts.Force);
validate_bvec_count(formalBvec, count_dwi_volumes(formalDwi));

result = struct();
result.dwi = formalDwi;
result.bval = formalBval;
result.bvec = formalBvec;
result.b0 = formalB0;
result.distortedB0 = distortedB0;
result.syntheticB0 = synb0Result.syntheticB0;
result.topupPrefix = synb0Result.topupPrefix;
result.topupFieldcoef = synb0Result.topupFieldcoef;
result.topupMovpar = synb0Result.topupMovpar;
result.eddyCorrectedDwi = eddyResult.correctedDwi;
result.rotatedBvec = eddyResult.rotatedBvec;
result.eddyAcqparams = eddyResult.acqparams;
result.eddyIndex = eddyResult.index;
result.eddyLog = eddyResult.log;
result.mask = maskPath;
result.workDir = workDir;
result.totalReadoutTime = totalReadoutTime;
result.totalReadoutTimeSource = readoutSource;
result.phaseEncodingVector = opts.PhaseEncodingVector;
result.synb0Status = 'ok';
result.eddyStatus = 'ok';
end

function [totalReadoutTime, source] = resolve_total_readout_time(jsonPath, requestedValue, defaultValue)
if ~isnan(requestedValue)
    totalReadoutTime = requestedValue;
    source = 'parameter';
    return;
end
source = 'default';
totalReadoutTime = defaultValue;
try
    metadata = jsondecode(fileread(jsonPath));
    if isfield(metadata, 'TotalReadoutTime') && isnumeric(metadata.TotalReadoutTime) && metadata.TotalReadoutTime > 0
        totalReadoutTime = metadata.TotalReadoutTime;
        source = 'json';
    end
catch
end
end

function write_synb0_acqparams(path, peVector, totalReadoutTime)
fid = fopen(path, 'w');
if fid < 0
    error('Could not write Synb0 acqparams: %s', path);
end
cleanupObj = onCleanup(@() fclose(fid));
fprintf(fid, '%.12g %.12g %.12g %.12g\n', peVector(1), peVector(2), peVector(3), totalReadoutTime);
fprintf(fid, '%.12g %.12g %.12g 0\n', peVector(1), peVector(2), peVector(3));
end

function synb0RunDir = resolve_synb0_run_dir(workDir, force)
if force
    timestamp = char(datetime('now', 'Format', 'yyyyMMdd_HHmmss'));
    synb0RunDir = fullfile(workDir, ['synb0_', timestamp]);
else
    synb0RunDir = fullfile(workDir, 'synb0');
end
end

function extract_mean_b0(dwiPath, b0Path, bvals, force)
if isfile(b0Path) && ~force
    return;
end
idx = find(bvals < 10);
if isempty(idx)
    error('Cannot extract b0 because no bval < 10 was found.');
end
V = spm_vol(dwiPath);
if numel(V) ~= numel(bvals)
    error('DWI volume count does not match bval count for b0 extraction.');
end
b0 = zeros(V(1).dim, 'double');
for i = 1:numel(idx)
    b0 = b0 + double(spm_read_vols(V(idx(i))));
end
b0 = b0 ./ numel(idx);
Vo = V(idx(1));
Vo.fname = b0Path;
Vo.n = [1, 1];
Vo.dt = [16, 0];
Vo.descrip = sprintf('Mean b0 extracted from %s', get_file_name(dwiPath));
spm_write_vol(Vo, b0);
end

function copy_or_gunzip(source, target, force)
if isfile(target) && ~force
    return;
end
ensure_dir(fileparts(target));
if endsWith(source, '.nii.gz')
    tempDir = tempname;
    mkdir(tempDir);
    cleanupObj = onCleanup(@() cleanup_temp_dir(tempDir));
    gunzip(source, tempDir);
    [~, base] = fileparts(source);
    copyfile(fullfile(tempDir, base), target, 'f');
else
    copyfile(source, target, 'f');
end
end

function nVolumes = count_dwi_volumes(dwiPath)
V = spm_vol(dwiPath);
nVolumes = numel(V);
end

function validate_bvec_count(path, nVolumes)
bvec = load(path);
if size(bvec, 1) == 3
    count = size(bvec, 2);
elseif size(bvec, 2) == 3
    count = size(bvec, 1);
else
    error('bvec file must be 3 x N or N x 3: %s', path);
end
if count ~= nVolumes
    error('bvec count (%d) does not match DWI volume count (%d).', count, nVolumes);
end
end

function vals = load_numeric_vector(path)
vals = load(path);
vals = vals(:)';
if isempty(vals) || ~isnumeric(vals)
    error('Could not read numeric values from %s', path);
end
end

function must_be_file(path, label)
if ~isfile(path)
    error('Missing %s: %s', label, path);
end
end

function ensure_dir(path)
if ~isfolder(path)
    mkdir(path);
end
end

function name = get_file_name(path)
[~, name, ext] = fileparts(path);
name = [name, ext];
end

function stem = strip_nii_ext(path)
stem = regexprep(path, '\.nii(\.gz)?$', '');
end

function cleanup_temp_dir(path)
if isfolder(path)
    try
        rmdir(path, 's');
    catch
    end
end
end
