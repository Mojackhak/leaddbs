function [b0Path, status] = ea_ensure_b0_from_dwi(options, varargin)
% Recreate a staged b0 image from a 4D DWI and BIDS gradient sidecars.

p = inputParser;
addParameter(p, 'Force', true, @(x) islogical(x) || isnumeric(x));
addParameter(p, 'B0Threshold', 50, @(x) isnumeric(x) && isscalar(x) && x >= 0);
addParameter(p, 'Verbose', true, @(x) islogical(x) || isnumeric(x));
parse(p, varargin{:});

force = logical(p.Results.Force);
verbose = logical(p.Results.Verbose);
b0Threshold = p.Results.B0Threshold;

b0Path = '';
status = struct( ...
    'ok', false, ...
    'created', false, ...
    'skipped', false, ...
    'message', '', ...
    'nVolumes', NaN, ...
    'nBvals', NaN, ...
    'nBvecs', NaN, ...
    'nB0', NaN);

try
    requiredPrefs = {'dti', 'bval', 'bvec', 'b0'};
    for i = 1:numel(requiredPrefs)
        if ~isfield(options, 'prefs') || ~isfield(options.prefs, requiredPrefs{i}) || isempty(options.prefs.(requiredPrefs{i}))
            [status, b0Path] = markSkipped(status, b0Path, sprintf('Missing options.prefs.%s.', requiredPrefs{i}), verbose);
            return;
        end
    end

    subjectDir = getSubjectDir(options);
    dwiPath = resolveSubjectPath(subjectDir, options.prefs.dti);
    bvalPath = resolveSubjectPath(subjectDir, options.prefs.bval);
    bvecPath = resolveSubjectPath(subjectDir, options.prefs.bvec);
    b0Path = resolveSubjectPath(subjectDir, options.prefs.b0);

    if ~isfile(dwiPath)
        [status, b0Path] = markSkipped(status, b0Path, ['Missing DWI file: ', dwiPath], verbose);
        return;
    end

    if ~isfile(bvalPath)
        [status, b0Path] = markSkipped(status, b0Path, ['Missing bval file: ', bvalPath], verbose);
        return;
    end

    if ~isfile(bvecPath)
        [status, b0Path] = markSkipped(status, b0Path, ['Missing bvec file: ', bvecPath], verbose);
        return;
    end

    if isfile(b0Path) && ~force
        status.ok = true;
        status.skipped = true;
        status.message = ['Existing b0 kept: ', b0Path];
        if verbose
            fprintf('%s\n', status.message);
        end
        return;
    end

    bvals = load(bvalPath);
    bvals = bvals(:);
    bvecs = load(bvecPath);

    dwiVolumes = spm_vol(dwiPath);
    nVolumes = numel(dwiVolumes);
    nBvals = numel(bvals);
    nBvecs = countBvecVolumes(bvecs);

    status.nVolumes = nVolumes;
    status.nBvals = nBvals;
    status.nBvecs = nBvecs;

    if nVolumes ~= nBvals
        [status, b0Path] = markSkipped(status, b0Path, sprintf('DWI volume count (%d) does not match bval count (%d).', nVolumes, nBvals), verbose);
        return;
    end

    if nVolumes ~= nBvecs
        [status, b0Path] = markSkipped(status, b0Path, sprintf('DWI volume count (%d) does not match bvec count (%d).', nVolumes, nBvecs), verbose);
        return;
    end

    b0Idx = find(bvals < b0Threshold);
    status.nB0 = numel(b0Idx);
    if isempty(b0Idx)
        [status, b0Path] = markSkipped(status, b0Path, sprintf('No b0 volumes found with bval < %.3g.', b0Threshold), verbose);
        return;
    end

    b0Dir = fileparts(b0Path);
    if ~isfolder(b0Dir)
        mkdir(b0Dir);
    end

    if isscalar(b0Idx)
        b0Image = spm_read_vols(dwiVolumes(b0Idx));
    else
        b0Image = mean(spm_read_vols(dwiVolumes(b0Idx)), 4);
    end

    outVolume = dwiVolumes(b0Idx(1));
    outVolume.fname = b0Path;
    outVolume.n = [1 1];
    outVolume.dt = [16 0];
    spm_write_vol(outVolume, single(b0Image));

    status.ok = true;
    status.created = true;
    status.skipped = false;
    status.message = sprintf('Wrote b0 from %d DWI volume(s): %s', numel(b0Idx), b0Path);
    if verbose
        fprintf('%s\n', status.message);
    end
catch ME
    status.ok = false;
    status.created = false;
    status.skipped = true;
    status.message = ['Failed to create b0 from DWI: ', ME.message];
    warnOnce(status.message);
end
end


function subjectDir = getSubjectDir(options)

if isfield(options, 'subj') && isfield(options.subj, 'subjDir') && ~isempty(options.subj.subjDir)
    subjectDir = options.subj.subjDir;
elseif isfield(options, 'root') && isfield(options, 'patientname')
    subjectDir = fullfile(options.root, options.patientname);
else
    error('Cannot resolve subject directory from options.');
end
end


function filePath = resolveSubjectPath(subjectDir, filePath)

if isAbsolutePath(filePath)
    return;
end

filePath = fullfile(subjectDir, filePath);
end


function tf = isAbsolutePath(filePath)

tf = startsWith(filePath, filesep) || ~isempty(regexp(filePath, '^[A-Za-z]:[\\/]', 'once')) || startsWith(filePath, '\\');
end


function nBvecs = countBvecVolumes(bvecs)

if isempty(bvecs)
    nBvecs = 0;
elseif isvector(bvecs)
    if mod(numel(bvecs), 3) == 0
        nBvecs = numel(bvecs) / 3;
    else
        nBvecs = numel(bvecs);
    end
elseif size(bvecs, 1) == 3
    nBvecs = size(bvecs, 2);
elseif size(bvecs, 2) == 3
    nBvecs = size(bvecs, 1);
else
    nBvecs = max(size(bvecs));
end
end


function [status, b0Path] = markSkipped(status, b0Path, message, verbose)

status.ok = false;
status.created = false;
status.skipped = true;
status.message = message;
if verbose
    warnOnce(message);
end
end


function warnOnce(message)

warning('ea_ensure_b0_from_dwi:Skipped', '%s', message);
end
