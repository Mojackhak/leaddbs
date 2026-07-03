function [taskResults, taskArray, cfg, S, options, stimFolders] = mh_vta_run_stim_spec_tasks(cfg, stimSpec, sides, varargin)
% Build stimulation inputs, atomic VTA tasks, and run them through the harness.

parser = inputParser;
parser.FunctionName = 'mh_vta_run_stim_spec_tasks';
parser.addParameter('ModelKey', default_model_key(cfg, stimSpec), @(x) ischar(x) || isstring(x));
parser.addParameter('Force', default_force(cfg), @(x) islogical(x) || isnumeric(x));
parser.addParameter('OutputSpaces', default_output_spaces(cfg), @(x) ischar(x) || isstring(x) || iscell(x));
parser.addParameter('ExportThresholdVPerMm', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
parser.addParameter('GmAtlas', default_gm_atlas(cfg), @(x) isempty(x) || ischar(x) || isstring(x));
parser.addParameter('UseAtlas', [], @(x) isempty(x) || islogical(x) || isnumeric(x));
parser.addParameter('RemoveElectrode', [], @(x) isempty(x) || islogical(x) || isnumeric(x));
parser.parse(varargin{:});
opts = parser.Results;

modelKey = char(string(opts.ModelKey));
stimSpec.model = modelKey;
cfg = mh_fiber_set_stimulation(cfg, stimSpec);
[S, options, stimFolders] = mh_fiber_build_stimulation(cfg);
[taskResults, taskArray, cfg] = mh_vta_run_built_stimulation_tasks( ...
    cfg, S, options, stimFolders, ...
    'Sides', sides, ...
    'ModelKey', modelKey, ...
    'Force', opts.Force, ...
    'OutputSpaces', opts.OutputSpaces, ...
    'ExportThresholdVPerMm', opts.ExportThresholdVPerMm, ...
    'GmAtlas', opts.GmAtlas, ...
    'UseAtlas', opts.UseAtlas, ...
    'RemoveElectrode', opts.RemoveElectrode);
end

function modelKey = default_model_key(cfg, stimSpec)
if isfield(stimSpec, 'model') && strlength(string(stimSpec.model)) > 0
    modelKey = stimSpec.model;
elseif isfield(cfg, 'vta') && isfield(cfg.vta, 'modelKey') && strlength(string(cfg.vta.modelKey)) > 0
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
