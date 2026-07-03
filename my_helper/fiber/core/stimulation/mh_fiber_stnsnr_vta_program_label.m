function label = mh_fiber_stnsnr_vta_program_label(subjectId, phase, protocol, varargin)
% Build a stable STN/SNr observed VTA program label.

parser = inputParser;
parser.FunctionName = 'mh_fiber_stnsnr_vta_program_label';
parser.addParameter('Pattern', 'continuous', @(x) ischar(x) || isstring(x));
parser.addParameter('Side', '', @(x) ischar(x) || isstring(x));
parser.addParameter('Target', '', @(x) ischar(x) || isstring(x));
parser.addParameter('RawContact', [], @is_empty_or_numeric_scalar);
parser.addParameter('RowIndex', [], @is_empty_or_numeric_scalar);
parser.parse(varargin{:});
opts = parser.Results;

pattern = lower(char(string(opts.Pattern)));
switch pattern
    case 'continuous'
        rawLabel = sprintf('stnsnr_vta_%s_%s_%s_continuous', ...
            char(string(subjectId)), char(string(phase)), char(string(protocol)));
    case {'alternating', 'alternating_subprogram'}
        require_alternating_fields(opts);
        rawLabel = sprintf('stnsnr_vta_%s_%s_%s_alt_%s_%s_c%d_row%d', ...
            char(string(subjectId)), char(string(phase)), char(string(protocol)), ...
            char(string(opts.Side)), char(string(opts.Target)), ...
            opts.RawContact, opts.RowIndex);
    otherwise
        error('mh_fiber_stnsnr_vta_program_label:InvalidPattern', ...
            'Unsupported STN/SNr VTA program pattern: %s', pattern);
end

label = mh_util_sanitize_label(rawLabel);
end

function tf = is_empty_or_numeric_scalar(value)
tf = isempty(value) || (isnumeric(value) && isscalar(value));
end

function require_alternating_fields(opts)
if strlength(string(opts.Side)) == 0 || strlength(string(opts.Target)) == 0 || ...
        isempty(opts.RawContact) || isempty(opts.RowIndex)
    error('mh_fiber_stnsnr_vta_program_label:MissingAlternatingField', ...
        ['Side, Target, RawContact, and RowIndex are required for ', ...
        'alternating STN/SNr VTA program labels.']);
end
end
