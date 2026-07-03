function [options, settings] = mh_vta_apply_settings(options, cfg, request)
% Apply explicit Horn VTA settings to a Lead-DBS options struct.

if nargin < 3
    request = struct();
end

gmAtlas = '';
if isfield(request, 'gmAtlas') && strlength(string(request.gmAtlas)) > 0
    gmAtlas = char(string(request.gmAtlas));
elseif isfield(cfg, 'vta') && isfield(cfg.vta, 'gmAtlas')
    gmAtlas = char(string(cfg.vta.gmAtlas));
end

if strlength(string(gmAtlas)) > 0
    options.atlasset = gmAtlas;
end

exportThreshold = [];
if isfield(request, 'exportThresholdVPerMm')
    exportThreshold = request.exportThresholdVPerMm;
elseif isfield(request, 'EThresholdVPerMm')
    exportThreshold = request.EThresholdVPerMm;
end

useAtlas = true;
if isfield(request, 'useAtlas')
    useAtlas = logical(request.useAtlas);
end

removeElectrode = true;
if isfield(request, 'removeElectrode')
    removeElectrode = logical(request.removeElectrode);
end

settings = mh_vta_settings( ...
    'EThresholdVPerMm', exportThreshold, ...
    'UseAtlas', useAtlas, ...
    'AtlasSet', gmAtlas, ...
    'RemoveElectrode', removeElectrode);

fields = fieldnames(settings);
if ~isfield(options, 'prefs') || ~isfield(options.prefs, 'machine') || ...
        ~isfield(options.prefs.machine, 'vatsettings')
    options.prefs.machine.vatsettings = struct();
end
for i = 1:numel(fields)
    options.prefs.machine.vatsettings.(fields{i}) = settings.(fields{i});
end
end
