function [taskResults, taskArray, cfg] = mh_vta_run_built_stimulation_tasks(cfg, S, options, stimFolders, varargin)
% Run an already built stimulation structure through the VTA task harness.

parser = inputParser;
parser.FunctionName = 'mh_vta_run_built_stimulation_tasks';
parser.addParameter('Sides', {'R', 'L'}, @(x) isnumeric(x) || ischar(x) || isstring(x) || iscell(x));
parser.addParameter('ModelKey', default_model_key(cfg), @(x) ischar(x) || isstring(x));
parser.addParameter('Force', default_force(cfg), @(x) islogical(x) || isnumeric(x));
parser.addParameter('OutputSpaces', default_output_spaces(cfg), @(x) ischar(x) || isstring(x) || iscell(x));
parser.addParameter('ExportThresholdVPerMm', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
parser.addParameter('GmAtlas', default_gm_atlas(cfg), @(x) isempty(x) || ischar(x) || isstring(x));
parser.addParameter('UseAtlas', [], @(x) isempty(x) || islogical(x) || isnumeric(x));
parser.addParameter('RemoveElectrode', [], @(x) isempty(x) || islogical(x) || isnumeric(x));
parser.parse(varargin{:});
opts = parser.Results;

entry = mh_vta_model_registry(opts.ModelKey);
cfg.vta.modelKey = entry.key;
cfg.vta.model = entry.modelName;

request = struct();
request.modelKey = entry.key;
request.force = logical(opts.Force);
request.sides = mh_vta_normalize_sides(struct('sides', {opts.Sides}));
request.outputSpaces = normalize_output_spaces(opts.OutputSpaces);
if ~isempty(opts.ExportThresholdVPerMm)
    request.exportThresholdVPerMm = double(opts.ExportThresholdVPerMm);
end
if ~isempty(opts.GmAtlas)
    cfg.vta.gmAtlas = char(string(opts.GmAtlas));
    request.gmAtlas = cfg.vta.gmAtlas;
end
if ~isempty(opts.UseAtlas)
    request.useAtlas = logical(opts.UseAtlas);
end
if ~isempty(opts.RemoveElectrode)
    request.removeElectrode = logical(opts.RemoveElectrode);
end

taskCells = cell(numel(request.sides), 1);
for i = 1:numel(request.sides)
    taskCells{i} = mh_vta_make_compute_task(cfg, stimFolders, request.sides{i}, request);
end
taskArray = vertcat(taskCells{:});
taskResults = mh_vta_run_compute_tasks(cfg, S, options, taskArray);
end

function modelKey = default_model_key(cfg)
if isfield(cfg, 'vta') && isfield(cfg.vta, 'modelKey') && strlength(string(cfg.vta.modelKey)) > 0
    modelKey = cfg.vta.modelKey;
else
    modelKey = 'simbio';
end
end

function force = default_force(cfg)
if isfield(cfg, 'forceRecomputeVTA')
    force = logical(cfg.forceRecomputeVTA);
else
    force = false;
end
end

function spaces = default_output_spaces(cfg)
if isfield(cfg, 'vta') && isfield(cfg.vta, 'space') && strcmp(char(string(cfg.vta.space)), 'native_and_mni')
    spaces = {'native', 'mni'};
else
    spaces = {'mni'};
end
end

function atlas = default_gm_atlas(cfg)
if isfield(cfg, 'vta') && isfield(cfg.vta, 'gmAtlas')
    atlas = cfg.vta.gmAtlas;
else
    atlas = '';
end
end

function spaces = normalize_output_spaces(value)
spaces = cellstr(string(value));
spaces = reshape(spaces, 1, []);
end
