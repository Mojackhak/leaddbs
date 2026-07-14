function published = mh_vta_publish_atomic(outputPath, producer, varargin)
% Publish one missing output through a temporary file in its destination.

parser = inputParser;
parser.FunctionName = mfilename;
parser.addParameter('EventEmitter', [], ...
    @(value) isempty(value) || isa(value, 'function_handle'));
parser.addParameter('TaskId', '', ...
    @(value) ischar(value) || (isstring(value) && isscalar(value)));
parser.parse(varargin{:});
emit = parser.Results.EventEmitter;
taskId = char(string(parser.Results.TaskId));

outputPath = char(string(outputPath));
if isfile(outputPath)
    published = false;
    return;
end
if ~isa(producer, 'function_handle')
    error('mh_vta_publish_atomic:InvalidProducer', ...
        'producer must be a function handle.');
end
outputDir = fileparts(outputPath);
if ~isfolder(outputDir)
    mkdir(outputDir);
end
temporaryPath = [tempname(outputDir), nifti_suffix(outputPath)];
cleanup = onCleanup(@() delete_if_present(temporaryPath));
producer(temporaryPath);
if ~isfile(temporaryPath)
    error('mh_vta_publish_atomic:MissingTemporaryOutput', ...
        'Producer did not create its temporary output: %s', temporaryPath);
end
if isfile(outputPath)
    published = false;
    return;
end
stageTimer = tic;
[ok, message] = movefile(temporaryPath, outputPath);
if ~ok
    error('mh_vta_publish_atomic:PublishFailed', ...
        'Could not publish %s: %s', outputPath, message);
end
mh_vta_emit_stage_timing(emit, 'task', taskId, ...
    'artifact_publication', 'executed', toc(stageTimer), '');
published = true;
clear cleanup;
end

function suffix = nifti_suffix(path)
if endsWith(path, '.nii.gz', 'IgnoreCase', true)
    suffix = '.nii.gz';
elseif endsWith(path, '.nii', 'IgnoreCase', true)
    suffix = '.nii';
else
    suffix = '.nii.gz';
end
end

function delete_if_present(path)
if isfile(path)
    delete(path);
end
end
