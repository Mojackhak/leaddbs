function label = mh_fiber_stnsnr_stimulation_pattern_label(values, varargin)
% Build an STN/SNr stimulation-pattern report label.

parser = inputParser;
parser.FunctionName = 'mh_fiber_stnsnr_stimulation_pattern_label';
parser.addParameter('Column', '', @(x) ischar(x) || isstring(x));
parser.addParameter('Mode', 'list', @(x) ischar(x) || isstring(x));
parser.parse(varargin{:});
opts = parser.Results;

patterns = unique(string(pattern_values(values, opts.Column)), 'stable');
mode = lower(char(string(opts.Mode)));

switch mode
    case 'list'
        label = mh_util_join_values(patterns);
    case 'condition_union'
        if isscalar(patterns) && patterns == "continuous"
            label = "continuous";
        elseif isscalar(patterns) && patterns == "alternating"
            label = "alternating_union";
        else
            label = "mixed_union";
        end
    otherwise
        error('mh_fiber_stnsnr_stimulation_pattern_label:InvalidMode', ...
            'Unsupported stimulation pattern label mode: %s', mode);
end
end

function values = pattern_values(inputValues, columnName)
if istable(inputValues)
    if strlength(string(columnName)) == 0
        error('mh_fiber_stnsnr_stimulation_pattern_label:MissingColumn', ...
            'Column is required when stimulation patterns are provided as a table.');
    end
    columnName = char(string(columnName));
    if ~ismember(columnName, inputValues.Properties.VariableNames)
        error('mh_fiber_stnsnr_stimulation_pattern_label:MissingColumn', ...
            'Stimulation pattern column is missing: %s', columnName);
    end
    values = inputValues.(columnName);
else
    values = inputValues;
end
end
