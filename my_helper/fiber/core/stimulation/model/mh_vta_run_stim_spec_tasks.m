function [taskResults, taskArray, cfg, S, options, stimFolders] = mh_vta_run_stim_spec_tasks(cfg, stimSpec, sides, varargin)
% Build stimulation inputs, atomic VTA tasks, and run them through the harness.

parser = inputParser;
parser.FunctionName = 'mh_vta_run_stim_spec_tasks';
defaults = mh_vta_task_request_defaults(cfg, stimSpec);
parser.addParameter('ModelKey', defaults.modelKey, @(x) ischar(x) || isstring(x));
parser.addParameter('Force', defaults.force, @(x) islogical(x) || isnumeric(x));
parser.addParameter('OutputSpaces', defaults.outputSpaces, @(x) ischar(x) || isstring(x) || iscell(x));
parser.addParameter('ExportThresholdVPerMm', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
parser.addParameter('GmAtlas', defaults.gmAtlas, @(x) isempty(x) || ischar(x) || isstring(x));
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
