function prepared = mh_viz_prepare_scene_example_input(runRoot, modelFamily, varargin)
% Prepare one final-model display input through the Conda leaddbs environment.

parser = inputParser;
parser.FunctionName = mfilename;
addRequired(parser, 'runRoot', @(value) ischar(value) || ...
    (isstring(value) && isscalar(value)));
addRequired(parser, 'modelFamily', @(value) ischar(value) || ...
    (isstring(value) && isscalar(value)));
addParameter(parser, 'ScaleId', 'pdq39_score', @(value) ischar(value) || ...
    (isstring(value) && isscalar(value)));
addParameter(parser, 'OutputRoot', fullfile(tempdir, ...
    'leaddbs_pdq39_scene_inputs'), @(value) ischar(value) || ...
    (isstring(value) && isscalar(value)));
parse(parser, runRoot, modelFamily, varargin{:});

runRoot = char(string(parser.Results.runRoot));
modelFamily = char(string(parser.Results.modelFamily));
scaleId = char(string(parser.Results.ScaleId));
outputRoot = char(string(parser.Results.OutputRoot));
validFamilies = {'reference_voxel', 'addon_voxel', ...
    'reference_fiber', 'addon_fiber'};
if ~ismember(modelFamily, validFamilies)
    error('mh_viz_prepare_scene_example_input:BadModelFamily', ...
        'Unsupported model family: %s', modelFamily);
end
if ~isfolder(runRoot)
    error('mh_viz_prepare_scene_example_input:MissingRun', ...
        'Run directory does not exist: %s', runRoot);
end

vizRoot = fileparts(mfilename('fullpath'));
repoRoot = fileparts(fileparts(fileparts(fileparts(vizRoot))));
condaExecutable = local_find_conda();
command = strjoin({ ...
    'cd', mh_fiber_shell_quote(repoRoot), '&&', ...
    mh_fiber_shell_quote(condaExecutable), 'run', '-n', 'leaddbs', ...
    'python', '-m', 'my_helper.fiber.core.viz.scene_example_inputs', ...
    '--run-root', mh_fiber_shell_quote(runRoot), ...
    '--output-root', mh_fiber_shell_quote(outputRoot), ...
    '--scale-id', mh_fiber_shell_quote(scaleId), ...
    '--model-family', mh_fiber_shell_quote(modelFamily)}, ' ');
[status, output] = system(command);
if status ~= 0
    error('mh_viz_prepare_scene_example_input:PreparationFailed', ...
        'Scene input preparation failed:\n%s', strtrim(output));
end
try
    prepared = jsondecode(strtrim(output));
catch exception
    error('mh_viz_prepare_scene_example_input:InvalidResponse', ...
        'Scene input preparation returned invalid JSON:\n%s\n%s', ...
        strtrim(output), exception.message);
end
if ~isstruct(prepared) || ~isfield(prepared, 'status') || ...
        ~strcmp(prepared.status, 'complete') || ...
        ~isfield(prepared, 'input_path') || ~isfile(prepared.input_path)
    error('mh_viz_prepare_scene_example_input:IncompleteResponse', ...
        'Scene input preparation did not return a completed input file.');
end
end

function condaExecutable = local_find_conda()
condaExecutable = strtrim(getenv('CONDA_EXE'));
if ~isempty(condaExecutable) && isfile(condaExecutable)
    return;
end
[status, output] = system('command -v conda');
candidate = strtrim(output);
if status == 0 && ~isempty(candidate) && isfile(candidate)
    condaExecutable = candidate;
    return;
end
candidates = { ...
    '/opt/anaconda3/condabin/conda', ...
    '/opt/homebrew/bin/conda', ...
    '/usr/local/bin/conda'};
for i = 1:numel(candidates)
    if isfile(candidates{i})
        condaExecutable = candidates{i};
        return;
    end
end
error('mh_viz_prepare_scene_example_input:MissingConda', ...
    'Conda was not found. The examples require the leaddbs environment.');
end
