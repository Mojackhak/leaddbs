function key = mh_fiber_stnsnr_condition_key(phase, protocol, varargin)
% Build a stable STN/SNr condition or target directory key.

parser = inputParser;
parser.FunctionName = 'mh_fiber_stnsnr_condition_key';
parser.addParameter('Target', '', @(x) ischar(x) || isstring(x));
parser.parse(varargin{:});
opts = parser.Results;

conditionKey = mh_util_sanitize_label(sprintf('%s_%s', ...
    char(string(phase)), char(string(protocol))));
if strlength(string(opts.Target)) == 0
    key = conditionKey;
else
    key = mh_util_sanitize_label(sprintf('%s_%s', ...
        conditionKey, char(string(opts.Target))));
end
end
