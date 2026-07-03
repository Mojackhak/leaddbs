function stimSpec = mh_fiber_stimspec_from_table(rows, anode, varargin)
% Build a stimulation specification from rows: side, contact, amp, pulseWidth, frequency.

if nargin < 2 || strlength(string(anode)) == 0
    anode = "case";
end

parser = inputParser;
parser.FunctionName = 'mh_fiber_stimspec_from_table';
addParameter(parser, 'Label', '', @(x) ischar(x) || isstring(x));
addParameter(parser, 'Model', mh_vta_default_model_key(), ...
    @(x) ischar(x) || isstring(x));
addParameter(parser, 'Space', 'native_and_mni', @(x) ischar(x) || isstring(x));
addParameter(parser, 'Unit', 'V', @(x) ischar(x) || isstring(x));
parse(parser, varargin{:});
opts = parser.Results;

data = normalize_rows(rows);
if size(data, 2) < 5
    error('mh_fiber_stimspec_from_table:InvalidRows', ...
        'Rows must contain side, contact, amplitude, pulseWidth, and frequency columns.');
end

stimSpec = struct();
stimSpec.label = char(string(opts.Label));
stimSpec.model = char(string(opts.Model));
stimSpec.space = char(string(opts.Space));
stimSpec.sources = repmat(empty_source(), size(data, 1), 1);

for i = 1:size(data, 1)
    source = empty_source();
    source.side = upper(char(data(i, 1)));
    source.contact = parse_number(data(i, 2), 'contact');
    source.amp = parse_number(data(i, 3), 'amp');
    source.unit = char(string(opts.Unit));
    source.pulseWidth = parse_number(data(i, 4), 'pulseWidth');
    source.frequency = parse_number(data(i, 5), 'frequency');
    source.cathode = true;
    source.anode = char(string(anode));
    stimSpec.sources(i) = source;
end

end

function source = empty_source()
source = struct( ...
    'side', '', ...
    'contact', NaN, ...
    'amp', NaN, ...
    'unit', 'V', ...
    'pulseWidth', NaN, ...
    'frequency', NaN, ...
    'cathode', true, ...
    'anode', 'case');
end

function data = normalize_rows(rows)
if istable(rows)
    data = strings(height(rows), width(rows));
    for c = 1:width(rows)
        data(:, c) = string(rows{:, c});
    end
elseif iscell(rows)
    data = string(rows);
else
    data = string(rows);
end

if isvector(data) && numel(data) == 5
    data = reshape(data, 1, 5);
end
end

function value = parse_number(textValue, fieldName)
value = str2double(string(textValue));
if isnan(value)
    error('mh_fiber_stimspec_from_table:InvalidNumber', ...
        'Invalid numeric value for %s: %s', fieldName, string(textValue));
end
end
