function settings = mh_vta_settings(varargin)
% Build Lead-DBS Horn vatsettings from explicit project/model inputs.

parser = inputParser;
parser.FunctionName = 'mh_vta_settings';
parser.addParameter('GrayMatterConductivity', 0.33, @(x) isnumeric(x) && isscalar(x));
parser.addParameter('WhiteMatterConductivity', 0.14, @(x) isnumeric(x) && isscalar(x));
parser.addParameter('EThresholdVPerMm', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
parser.addParameter('UseAtlas', true, @(x) islogical(x) || isnumeric(x));
parser.addParameter('AtlasSet', '', @(x) ischar(x) || isstring(x));
parser.addParameter('RemoveElectrode', true, @(x) islogical(x) || isnumeric(x));
parser.parse(varargin{:});
opts = parser.Results;

settings = struct();
settings.horn_cgm = double(opts.GrayMatterConductivity);
settings.horn_cwm = double(opts.WhiteMatterConductivity);
if ~isempty(opts.EThresholdVPerMm)
    settings.horn_ethresh = double(opts.EThresholdVPerMm);
end
settings.horn_useatlas = double(logical(opts.UseAtlas));
if strlength(string(opts.AtlasSet)) > 0
    settings.horn_atlasset = char(string(opts.AtlasSet));
end
settings.horn_removeElectrode = double(logical(opts.RemoveElectrode));
end
