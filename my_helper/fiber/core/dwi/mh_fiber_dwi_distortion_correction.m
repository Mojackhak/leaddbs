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
p.addParameter('Synb0WorkRoot', '', @(x) ischar(x) || isstring(x));
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
opts.Synb0WorkRoot = char(string(opts.Synb0WorkRoot));
mh_util_must_be_file(paths.dwi, 'staged DWI', ...
    'mh_fiber_dwi_distortion_correction:MissingFile');
mh_util_must_be_file(paths.bval, 'bval', ...
    'mh_fiber_dwi_distortion_correction:MissingFile');
mh_util_must_be_file(paths.bvec, 'bvec', ...
    'mh_fiber_dwi_distortion_correction:MissingFile');
mh_util_must_be_file(paths.json, 'DWI JSON', ...
    'mh_fiber_dwi_distortion_correction:MissingFile');
mh_util_must_be_file(t1Image, 'anchorNative T1w', ...
    'mh_fiber_dwi_distortion_correction:MissingFile');

workDir = fullfile(paths.dwiDir, 'work', 'synb0_eddy');
mh_util_make_dir(workDir);

rawBase = regexprep(paths.outputBase, '_dwi$', '');
distortedB0 = fullfile(workDir, [rawBase, '_desc-distorted_b0.nii']);
correctedPrefix = fullfile(workDir, [rawBase, '_desc-eddy']);
formalDwi = fullfile(paths.dwiDir, [rawBase, '_desc-preproc_dwi.nii']);
formalBval = fullfile(paths.dwiDir, [rawBase, '_desc-preproc_dwi.bval']);
formalBvec = fullfile(paths.dwiDir, [rawBase, '_desc-preproc_dwi.bvec']);
formalB0 = fullfile(paths.dwiDir, [rawBase, '_desc-preproc_b0.nii']);
synb0Acqparams = fullfile(workDir, 'synb0_acqparams.txt');

bvals = mh_fiber_load_bval(paths.bval);
mh_fiber_extract_mean_b0(paths.dwi, distortedB0, bvals, opts.Force);

[totalReadoutTime, readoutSource] = resolve_total_readout_time(paths.json, ...
    opts.TotalReadoutTime, opts.DefaultTotalReadoutTime);
write_synb0_acqparams(synb0Acqparams, opts.PhaseEncodingVector, totalReadoutTime);

projectSynb0RunDir = resolve_synb0_run_dir(workDir, opts.Force);
synb0RunDir = resolve_synb0_execution_dir(projectSynb0RunDir, opts.Synb0WorkRoot, paths.patientName);
synb0Result = ea_synb0(distortedB0, t1Image, synb0Acqparams, synb0RunDir, ...
    'ContainerEngine', opts.Synb0ContainerEngine, ...
    'Synb0Image', opts.Synb0Image, ...
    'FreeSurferLicense', opts.FreeSurferLicense, ...
    'MinDockerMemoryGB', opts.Synb0MinDockerMemoryGB, ...
    'Force', opts.Force);
synb0Result = archive_synb0_result(synb0Result, synb0RunDir, projectSynb0RunDir, opts.Force);

maskImage = fullfile(workDir, [rawBase, '_desc-synb0_brain.nii']);
maskBase = mh_fiber_strip_nii_ext(maskImage);
maskPath = [maskBase, '_mask.nii'];
if opts.Force || ~isfile(maskPath)
    ea_bet(synb0Result.syntheticB0, 1, maskImage, 0.5);
end
if ~isfile(maskPath) && isfile([maskPath, '.gz'])
    gunzip([maskPath, '.gz'], fileparts(maskPath));
end
mh_util_must_be_file(maskPath, 'eddy brain mask', ...
    'mh_fiber_dwi_distortion_correction:MissingFile');

eddyResult = ea_eddy(paths.dwi, maskPath, paths.bval, paths.bvec, synb0Result.topupPrefix, correctedPrefix, ...
    'PhaseEncodingVector', opts.PhaseEncodingVector, ...
    'TotalReadoutTime', totalReadoutTime, ...
    'Force', opts.Force, ...
    'UseDataIsShelled', true);

copy_or_gunzip(eddyResult.correctedDwi, formalDwi, opts.Force);
copyfile(paths.bval, formalBval, 'f');
copyfile(eddyResult.rotatedBvec, formalBvec, 'f');
mh_fiber_extract_mean_b0(formalDwi, formalB0, bvals, opts.Force);
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
result.synb0ExecutionDir = synb0Result.executionDir;
result.synb0ArchiveDir = synb0Result.archiveDir;
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

function synb0RunDir = resolve_synb0_execution_dir(projectSynb0RunDir, synb0WorkRoot, patientName)
if isempty(synb0WorkRoot)
    synb0RunDir = projectSynb0RunDir;
    return;
end
[~, runName] = fileparts(projectSynb0RunDir);
safePatientName = regexprep(char(string(patientName)), '[^A-Za-z0-9_.-]', '_');
synb0RunDir = fullfile(synb0WorkRoot, safePatientName, runName);
end

function result = archive_synb0_result(result, executionDir, archiveDir, force)
result.executionDir = executionDir;
result.archiveDir = executionDir;
if strcmp(executionDir, archiveDir)
    return;
end

mh_util_make_dir(fileparts(archiveDir));
if isfolder(archiveDir) && ~force && existing_synb0_archive_complete(archiveDir)
    result = rewrite_synb0_result_paths(result, executionDir, archiveDir);
    result.executionDir = executionDir;
    result.archiveDir = archiveDir;
    return;
end
targetArchiveDir = resolve_archive_target(archiveDir, force);
[ok, message] = copyfile(executionDir, targetArchiveDir, 'f');
if ~ok
    error('mh_fiber_dwi_distortion_correction:Synb0ArchiveFailed', ...
        'Could not archive Synb0 run from %s to %s: %s', ...
        executionDir, targetArchiveDir, message);
end
result = rewrite_synb0_result_paths(result, executionDir, targetArchiveDir);
result.executionDir = executionDir;
result.archiveDir = targetArchiveDir;
end

function tf = existing_synb0_archive_complete(archiveDir)
outputsDir = fullfile(archiveDir, 'OUTPUTS');
syntheticB0 = first_existing({ ...
    fullfile(outputsDir, 'b0_u.nii.gz'), ...
    fullfile(outputsDir, 'b0_u.nii')});
tf = ~isempty(syntheticB0) && ...
    isfile(fullfile(outputsDir, 'topup_fieldcoef.nii.gz')) && ...
    isfile(fullfile(outputsDir, 'topup_movpar.txt'));
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

function archiveDir = resolve_archive_target(requestedDir, force)
archiveDir = requestedDir;
if ~isfolder(archiveDir)
    return;
end
if ~force
    error('mh_fiber_dwi_distortion_correction:Synb0ArchiveExists', ...
        'Synb0 archive already exists: %s', archiveDir);
end
suffix = 1;
while isfolder(archiveDir)
    archiveDir = sprintf('%s_retry%02d', requestedDir, suffix);
    suffix = suffix + 1;
end
end

function result = rewrite_synb0_result_paths(result, executionDir, archiveDir)
fields = fieldnames(result);
for i = 1:numel(fields)
    value = result.(fields{i});
    if ischar(value) && startsWith(value, executionDir)
        result.(fields{i}) = [archiveDir, value((length(executionDir) + 1):end)];
    end
end
end

function copy_or_gunzip(source, target, force)
if isfile(target) && ~force
    return;
end
mh_util_make_dir(fileparts(target));
if endsWith(source, '.nii.gz')
    tempDir = tempname;
    mkdir(tempDir);
    cleanupObj = onCleanup(@() mh_fiber_cleanup_temp_dir(tempDir));
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
count = mh_fiber_bvec_count(path);
if count ~= nVolumes
    error('bvec count (%d) does not match DWI volume count (%d).', count, nVolumes);
end
end
