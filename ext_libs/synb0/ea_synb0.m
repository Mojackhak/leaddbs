function result = ea_synb0(distortedB0, t1Image, acqparamsPath, outputDir, varargin)
% Run Synb0-DISCO and return the synthetic b0 and topup prefix.

p = inputParser;
p.addParameter('ContainerEngine', 'auto', @(x) ischar(x) || isstring(x));
p.addParameter('Synb0Image', 'leonyichencai/synb0-disco:v3.1', @(x) ischar(x) || isstring(x));
p.addParameter('FreeSurferLicense', '', @(x) ischar(x) || isstring(x));
p.addParameter('MinDockerMemoryGB', 12, @(x) isnumeric(x) && isscalar(x) && x >= 0);
p.addParameter('Force', false, @(x) islogical(x) || isnumeric(x));
p.parse(varargin{:});
opts = p.Results;

opts.ContainerEngine = char(string(opts.ContainerEngine));
opts.Synb0Image = char(string(opts.Synb0Image));
opts.FreeSurferLicense = char(string(opts.FreeSurferLicense));
opts.MinDockerMemoryGB = double(opts.MinDockerMemoryGB);
opts.Force = logical(opts.Force);

must_be_file(distortedB0, 'distorted b0');
must_be_file(t1Image, 'T1 image');
must_be_file(acqparamsPath, 'acqparams');
if isempty(opts.Synb0Image)
    error('ea_synb0:MissingImage', 'Synb0Image must not be empty.');
end

ensure_dir(outputDir);
inputsDir = fullfile(outputDir, 'INPUTS');
outputsDir = fullfile(outputDir, 'OUTPUTS');
logPath = fullfile(outputDir, 'synb0.log');
ensure_dir(inputsDir);
ensure_dir(outputsDir);

inputB0 = fullfile(inputsDir, 'b0.nii.gz');
inputT1 = fullfile(inputsDir, 'T1.nii.gz');
inputAcq = fullfile(inputsDir, 'acqparams.txt');
copy_to_niigz(distortedB0, inputB0, opts.Force);
copy_to_niigz(t1Image, inputT1, opts.Force);
copyfile(acqparamsPath, inputAcq, 'f');

syntheticB0 = first_existing({ ...
    fullfile(outputsDir, 'b0_u.nii.gz'), ...
    fullfile(outputsDir, 'b0_u.nii')});
topupPrefix = fullfile(outputsDir, 'topup');
topupField = [topupPrefix, '_fieldcoef.nii.gz'];
topupMovpar = [topupPrefix, '_movpar.txt'];

if opts.Force || isempty(syntheticB0) || ~isfile(topupField) || ~isfile(topupMovpar)
    engine = resolve_container_engine(opts.ContainerEngine);
    assert_container_ready(engine, opts.Synb0Image, opts.MinDockerMemoryGB);
    licensePath = resolve_freesurfer_license(opts.FreeSurferLicense);
    licenseMountPath = stage_freesurfer_license(licensePath, outputDir);
    cmd = build_synb0_command(engine, opts.Synb0Image, inputsDir, outputsDir, licenseMountPath);
    fprintf('\nRunning Synb0-DISCO:\n%s\n\n', cmd);
    [status, cmdout] = system(cmd);
    write_text_file(logPath, sprintf('%s\n\n%s\n', cmd, cmdout));
    if synb0_inference_was_killed(cmdout)
        error('ea_synb0:InferenceKilled', ...
            ['Synb0-DISCO inference was killed before producing b0_u. ', ...
            'Increase Docker/Singularity memory and rerun. See log: %s'], logPath);
    end
    if status ~= 0
        error('ea_synb0:RunFailed', 'Synb0-DISCO failed with status %d:\n%s', status, cmdout);
    end
    syntheticB0 = first_existing({ ...
        fullfile(outputsDir, 'b0_u.nii.gz'), ...
        fullfile(outputsDir, 'b0_u.nii')});
end

if isempty(syntheticB0) || ~isfile(syntheticB0)
    error('ea_synb0:MissingOutput', ...
        'Synb0-DISCO did not produce b0_u in %s. See log: %s', outputsDir, logPath);
end
if ~isfile(topupField) || ~isfile(topupMovpar)
    error('ea_synb0:MissingTopupOutput', ...
        'Synb0-DISCO did not produce expected topup outputs with prefix %s.', topupPrefix);
end

result = struct();
result.syntheticB0 = syntheticB0;
result.topupPrefix = topupPrefix;
result.topupFieldcoef = topupField;
result.topupMovpar = topupMovpar;
result.inputsDir = inputsDir;
result.outputsDir = outputsDir;
result.log = logPath;
end

function engine = resolve_container_engine(engine)
engine = char(string(engine));
if strcmpi(engine, 'auto')
    if command_exists('docker')
        engine = 'docker';
    elseif command_exists('singularity')
        engine = 'singularity';
    else
        error('ea_synb0:MissingContainerEngine', ...
            'Docker or Singularity is required for Synb0-DISCO, but neither was found on PATH.');
    end
elseif ~command_exists(engine)
    error('ea_synb0:MissingContainerEngine', ...
        'Requested container engine is not available on PATH: %s', engine);
end
end

function assert_container_ready(engine, imageName, minDockerMemoryGB)
switch lower(engine)
    case 'docker'
        [status, cmdout] = system('docker info');
        if status ~= 0
            error('ea_synb0:DockerUnavailable', ...
                'Docker is installed but the daemon is not reachable. Start Docker before running Synb0-DISCO. Details: %s', ...
                compact_message(cmdout));
        end
        assert_docker_memory(minDockerMemoryGB);
        [status, cmdout] = system(sprintf('docker image inspect %s', q(imageName)));
        if status ~= 0
            error('ea_synb0:MissingDockerImage', ...
                'Synb0-DISCO Docker image is not available locally: %s. Pull it before running. Details: %s', ...
                imageName, compact_message(cmdout));
        end
    case 'singularity'
        if startsWith(imageName, {'docker://', 'library://', 'shub://'})
            return;
        end
        if ~isfile(imageName)
            error('ea_synb0:MissingSingularityImage', ...
                'Synb0-DISCO Singularity image does not exist: %s', imageName);
        end
    otherwise
        error('ea_synb0:UnsupportedEngine', 'Unsupported container engine: %s', engine);
end
end

function assert_docker_memory(minDockerMemoryGB)
if minDockerMemoryGB <= 0
    return;
end
[status, cmdout] = system('docker info --format "{{.MemTotal}}"');
if status ~= 0
    warning('ea_synb0:DockerMemoryUnknown', ...
        'Could not read Docker memory limit before running Synb0-DISCO: %s', compact_message(cmdout));
    return;
end
memBytes = str2double(strtrim(cmdout));
if isnan(memBytes) || memBytes <= 0
    warning('ea_synb0:DockerMemoryUnknown', ...
        'Could not parse Docker memory limit before running Synb0-DISCO: %s', compact_message(cmdout));
    return;
end
memGB = memBytes / 1024 ^ 3;
if memGB < minDockerMemoryGB
    error('ea_synb0:InsufficientDockerMemory', ...
        ['Docker reports %.1f GB memory, below the %.1f GB preflight threshold for Synb0-DISCO. ', ...
        'Increase Docker Desktop memory and rerun, or set MinDockerMemoryGB to 0 to bypass this preflight.'], ...
        memGB, minDockerMemoryGB);
end
end

function licensePath = resolve_freesurfer_license(licensePath)
licensePath = char(string(licensePath));
if isempty(licensePath)
    candidates = { ...
        getenv('FS_LICENSE'), ...
        fullfile(getenv('FREESURFER_HOME'), 'license.txt'), ...
        latest_file('/Applications/freesurfer/*/license.txt'), ...
        fullfile(getenv('HOME'), 'license.txt')};
    for i = 1:numel(candidates)
        if ~isempty(candidates{i}) && isfile(candidates{i})
            licensePath = candidates{i};
            break;
        end
    end
end
if isempty(licensePath) || ~isfile(licensePath)
    error('ea_synb0:MissingFreeSurferLicense', ...
        'FreeSurfer license not found. Set FreeSurferLicense or FS_LICENSE before running Synb0-DISCO.');
end
end

function cmd = build_synb0_command(engine, imageName, inputsDir, outputsDir, licensePath)
switch lower(engine)
    case 'docker'
        cmd = sprintf(['docker run --rm ', ...
            '--platform linux/amd64 ', ...
            '--user %s:%s ', ...
            '-v %s:/INPUTS:ro ', ...
            '-v %s:/OUTPUTS ', ...
            '-v %s:/extra/freesurfer/license.txt:ro ', ...
            '%s'], current_user_id(), current_group_id(), q(inputsDir), q(outputsDir), q(licensePath), imageName);
    case 'singularity'
        cmd = sprintf(['singularity run --cleanenv ', ...
            '--bind %s:/INPUTS,%s:/OUTPUTS,%s:/extra/freesurfer/license.txt ', ...
            '%s'], q(inputsDir), q(outputsDir), q(licensePath), imageName);
    otherwise
        error('ea_synb0:UnsupportedEngine', 'Unsupported container engine: %s', engine);
end
end

function licenseMountPath = stage_freesurfer_license(licensePath, outputDir)
licenseMountPath = fullfile(outputDir, 'freesurfer_license.txt');
copyfile(licensePath, licenseMountPath, 'f');
end

function copy_to_niigz(source, target, force)
if isfile(target) && ~force
    return;
end
ensure_dir(fileparts(target));
if endsWith(source, '.nii.gz')
    copyfile(source, target, 'f');
elseif endsWith(source, '.nii')
    tempDir = tempname;
    mkdir(tempDir);
    cleanupObj = onCleanup(@() cleanup_temp_dir(tempDir));
    copyfile(source, fullfile(tempDir, 'image.nii'), 'f');
    gzip(fullfile(tempDir, 'image.nii'), tempDir);
    copyfile(fullfile(tempDir, 'image.nii.gz'), target, 'f');
else
    error('ea_synb0:UnsupportedImage', 'Expected .nii or .nii.gz image: %s', source);
end
end

function path = first_existing(paths)
path = '';
for i = 1:numel(paths)
    if isfile(paths{i})
        path = paths{i};
        return;
    end
end
end

function path = latest_file(pattern)
d = dir(pattern);
if isempty(d)
    path = '';
    return;
end
[~, order] = sort([d.datenum]);
d = d(order);
path = fullfile(d(end).folder, d(end).name);
end

function must_be_file(path, label)
if ~isfile(path)
    error('ea_synb0:MissingInput', 'Missing %s: %s', label, path);
end
end

function ensure_dir(path)
if ~isfolder(path)
    mkdir(path);
end
end

function write_text_file(path, text)
fid = fopen(path, 'w');
if fid < 0
    warning('ea_synb0:LogWriteFailed', 'Could not write Synb0 log: %s', path);
    return;
end
cleanupObj = onCleanup(@() fclose(fid));
fprintf(fid, '%s', text);
end

function tf = synb0_inference_was_killed(cmdout)
tf = ~isempty(regexp(cmdout, 'Killed\s+python3(\.\d+)?\s+/extra/inference\.py', 'once'));
end

function tf = command_exists(commandName)
[status, ~] = system(sprintf('command -v %s', commandName));
tf = status == 0;
end

function qpath = q(path)
qpath = ['''', strrep(char(path), '''', '''"''"'''), ''''];
end

function uid = current_user_id()
[status, out] = system('id -u');
if status ~= 0
    error('ea_synb0:UserLookupFailed', 'Could not resolve current user id.');
end
uid = strtrim(out);
end

function gid = current_group_id()
[status, out] = system('id -g');
if status ~= 0
    error('ea_synb0:GroupLookupFailed', 'Could not resolve current group id.');
end
gid = strtrim(out);
end

function s = compact_message(s)
s = char(string(s));
s = regexprep(s, '\s+', ' ');
if numel(s) > 240
    s = [s(1:237), '...'];
end
end

function cleanup_temp_dir(path)
if isfolder(path)
    try
        rmdir(path, 's');
    catch
    end
end
end
