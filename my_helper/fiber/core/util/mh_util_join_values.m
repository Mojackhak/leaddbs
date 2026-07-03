function value = mh_util_join_values(values, varargin)
% Join values into one string scalar with a stable delimiter.

parser = inputParser;
parser.FunctionName = 'mh_util_join_values';
parser.addParameter('Delimiter', ';', @(x) ischar(x) || isstring(x));
parser.parse(varargin{:});
opts = parser.Results;

value = strjoin(string(values(:))', char(string(opts.Delimiter)));
end
