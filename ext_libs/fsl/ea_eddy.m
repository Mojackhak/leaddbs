function result = ea_eddy(dwiPath, maskPath, bvalPath, bvecPath, topupPrefix, outputPrefix, varargin)
% Run FSL eddy using an existing topup prefix.

p = inputParser;
p.addParameter('PhaseEncodingVector', [0 1 0], @(x) isnumeric(x) && numel(x) == 3);
p.addParameter('TotalReadoutTime', 0.05, @(x) isnumeric(x) && isscalar(x) && x >= 0);
p.addParameter('Force', false, @(x) islogical(x) || isnumeric(x));
p.addParameter('UseDataIsShelled', true, @(x) islogical(x) || isnumeric(x));
p.parse(varargin{:});
opts = p.Results;

opts.PhaseEncodingVector = double(opts.PhaseEncodingVector(:)');
opts.TotalReadoutTime = double(opts.TotalReadoutTime);
opts.Force = logical(opts.Force);
opts.UseDataIsShelled = logical(opts.UseDataIsShelled);

must_be_file(dwiPath, 'DWI image');
must_be_file(maskPath, 'brain mask');
must_be_file(bvalPath, 'bval file');
must_be_file(bvecPath, 'bvec file');
must_be_file([topupPrefix, '_fieldcoef.nii.gz'], 'topup field coefficient');
must_be_file([topupPrefix, '_movpar.txt'], 'topup movement parameters');

outputDir = fileparts(outputPrefix);
ensure_dir(outputDir);
acqparamsPath = fullfile(outputDir, 'eddy_acqparams.txt');
indexPath = fullfile(outputDir, 'eddy_index.txt');
logPath = [outputPrefix, '.log'];
correctedDwi = [outputPrefix, '.nii.gz'];
rotatedBvec = [outputPrefix, '.eddy_rotated_bvecs'];

nVolumes = count_dwi_volumes(dwiPath);
write_acqparams(acqparamsPath, opts.PhaseEncodingVector, opts.TotalReadoutTime);
write_index(indexPath, nVolumes);

if opts.Force || ~isfile(correctedDwi) || ~isfile(rotatedBvec)
    eddyExec = resolve_eddy_exec();
    cmd = [eddyExec, ...
        ' --imain=', ea_path_helper(dwiPath), ...
        ' --mask=', ea_path_helper(maskPath), ...
        ' --acqp=', ea_path_helper(acqparamsPath), ...
        ' --index=', ea_path_helper(indexPath), ...
        ' --bvecs=', ea_path_helper(bvecPath), ...
        ' --bvals=', ea_path_helper(bvalPath), ...
        ' --topup=', ea_path_helper(topupPrefix), ...
        ' --out=', ea_path_helper(outputPrefix)];
    if opts.UseDataIsShelled
        cmd = [cmd, ' --data_is_shelled'];
    end
    fprintf('\nRunning eddy:\n%s\n\n', cmd);
    [status, cmdout] = ea_runcmd(cmd);
    fid = fopen(logPath, 'w');
    if fid >= 0
        cleanupObj = onCleanup(@() fclose(fid));
        fprintf(fid, '%s\n', cmd);
        fprintf(fid, '%s\n', cmdout);
    end
    if status ~= 0
        error('ea_eddy:RunFailed', 'eddy failed with status %d:\n%s', status, cmdout);
    end
end

validate_rotated_bvec(rotatedBvec, nVolumes);

result = struct();
result.correctedDwi = correctedDwi;
result.rotatedBvec = rotatedBvec;
result.acqparams = acqparamsPath;
result.index = indexPath;
result.log = logPath;
result.nVolumes = nVolumes;
result.phaseEncodingVector = opts.PhaseEncodingVector;
result.totalReadoutTime = opts.TotalReadoutTime;
end

function eddyExec = resolve_eddy_exec()
pluginDir = fullfile(ea_getearoot, 'ext_libs', 'dsi_studio', 'plugin');
candidate = fullfile(pluginDir, 'eddy');
eddyExec = ea_getExec(candidate, escapePath = 1);
end

function nVolumes = count_dwi_volumes(dwiPath)
infoPath = dwiPath;
tempDir = '';
if endsWith(dwiPath, '.gz')
    tempDir = tempname;
    mkdir(tempDir);
    gunzip(dwiPath, tempDir);
    [~, base] = fileparts(dwiPath);
    infoPath = fullfile(tempDir, base);
end
cleanupObj = onCleanup(@() cleanup_temp_dir(tempDir));
V = spm_vol(infoPath);
nVolumes = numel(V);
end

function write_acqparams(path, peVector, totalReadoutTime)
fid = fopen(path, 'w');
if fid < 0
    error('ea_eddy:WriteFailed', 'Could not write acqparams: %s', path);
end
cleanupObj = onCleanup(@() fclose(fid));
fprintf(fid, '%.12g %.12g %.12g %.12g\n', peVector(1), peVector(2), peVector(3), totalReadoutTime);
fprintf(fid, '%.12g %.12g %.12g 0\n', peVector(1), peVector(2), peVector(3));
end

function write_index(path, nVolumes)
fid = fopen(path, 'w');
if fid < 0
    error('ea_eddy:WriteFailed', 'Could not write index file: %s', path);
end
cleanupObj = onCleanup(@() fclose(fid));
fprintf(fid, '%d ', ones(1, nVolumes));
fprintf(fid, '\n');
end

function validate_rotated_bvec(path, nVolumes)
must_be_file(path, 'rotated bvec file');
bvec = load(path);
if size(bvec, 1) == 3
    count = size(bvec, 2);
elseif size(bvec, 2) == 3
    count = size(bvec, 1);
else
    error('ea_eddy:InvalidRotatedBvec', ...
        'Rotated bvec file must be 3 x N or N x 3: %s', path);
end
if count ~= nVolumes
    error('ea_eddy:InvalidRotatedBvec', ...
        'Rotated bvec count (%d) does not match DWI volume count (%d).', count, nVolumes);
end
end

function must_be_file(path, label)
if ~isfile(path)
    error('ea_eddy:MissingInput', 'Missing %s: %s', label, path);
end
end

function ensure_dir(path)
if ~isfolder(path)
    mkdir(path);
end
end

function cleanup_temp_dir(path)
if strlength(string(path)) > 0 && isfolder(path)
    try
        rmdir(path, 's');
    catch
    end
end
end
