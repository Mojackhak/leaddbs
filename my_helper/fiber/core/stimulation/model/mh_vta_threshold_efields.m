function published = mh_vta_threshold_efields(efieldPath, thresholdsVPerM, ...
        outputPaths, varargin)
% Generate multiple thresholded VTAs from one E-field NIfTI load.

parser = inputParser;
parser.FunctionName = mfilename;
parser.addParameter('EventEmitter', [], ...
    @(value) isempty(value) || isa(value, 'function_handle'));
parser.addParameter('TaskId', '', ...
    @(value) ischar(value) || (isstring(value) && isscalar(value)));
parser.parse(varargin{:});
emit = parser.Results.EventEmitter;
taskId = char(string(parser.Results.TaskId));

efieldPath = char(string(efieldPath));
validateattributes(thresholdsVPerM, {'numeric'}, ...
    {'real', 'finite', 'nonnegative'}, mfilename, ...
    'thresholdsVPerM');
if ~isempty(thresholdsVPerM) && ~isvector(thresholdsVPerM)
    error('mh_vta_threshold_efields:InvalidThresholdShape', ...
        'thresholdsVPerM must be a vector.');
end
thresholdsVPerM = double(thresholdsVPerM(:));
if ischar(outputPaths)
    outputPaths = string({outputPaths});
else
    outputPaths = string(outputPaths(:));
end
if numel(thresholdsVPerM) ~= numel(outputPaths)
    error('mh_vta_threshold_efields:SizeMismatch', ...
        'thresholdsVPerM and outputPaths must have equal lengths.');
end
if any(ismissing(outputPaths) | strlength(outputPaths) == 0)
    error('mh_vta_threshold_efields:InvalidOutputPath', ...
        'Every output path must be a nonempty string.');
end

published = false(numel(outputPaths), 1);
missing = ~arrayfun(@(path) isfile(char(path)), outputPaths);
if ~any(missing)
    return;
end
if ~isfile(efieldPath)
    error('mh_vta_threshold_efields:MissingInput', ...
        'E-field NIfTI does not exist: %s', efieldPath);
end

firstTimer = tic;
source = ea_load_nii(efieldPath);
firstMissing = find(missing, 1, 'first');
for requestIndex = find(missing(:))'
    if requestIndex == firstMissing
        stageTimer = firstTimer;
    else
        stageTimer = tic;
    end
    threshold = thresholdsVPerM(requestIndex);
    outputPath = char(outputPaths(requestIndex));
    thresholded = source;
    thresholded.img = uint8(isfinite(source.img) & ...
        source.img >= threshold);
    thresholded.dt = [2, machine_endian_code()];
    thresholded.pinfo = [1; 0; 0];
    thresholded.descrip = sprintf( ...
        'VTA indicator E >= %.12g V/m', threshold);
    published(requestIndex) = mh_vta_publish_atomic(outputPath, ...
        @(temporaryPath) write_threshold(thresholded, temporaryPath, ...
            emit, taskId, stageTimer), ...
        'EventEmitter', emit, 'TaskId', taskId);
end
end

function write_threshold(nii, outputPath, emit, taskId, stageTimer)
nii.fname = outputPath;
ensure_parent_directory(outputPath);
ea_write_nii(nii);
mh_vta_emit_stage_timing(emit, 'task', taskId, ...
    'threshold_generation', 'executed', toc(stageTimer), '');
end

function code = machine_endian_code()
[~, ~, endian] = computer;
code = double(endian == 'B');
end

function ensure_parent_directory(path)
parent = fileparts(path);
if ~isempty(parent) && ~isfolder(parent)
    mkdir(parent);
end
end
