function out = mh_util_sanitize_label(value, varargin)
% Convert free text into a filesystem-safe analysis label.

parser = inputParser;
parser.FunctionName = 'mh_util_sanitize_label';
parser.addParameter('PreservePlus', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('ErrorId', '', @(x) ischar(x) || isstring(x));
parser.parse(varargin{:});
opts = parser.Results;

out = char(string(value));
if ~logical(opts.PreservePlus)
    out = regexprep(out, '\+', 'plus');
end
out = regexprep(out, '[^A-Za-z0-9_+-]+', '_');
out = regexprep(out, '_+', '_');
out = regexprep(out, '^_|_$', '');
if isempty(out) && strlength(string(opts.ErrorId)) > 0
    error(char(string(opts.ErrorId)), 'Label is empty after sanitization.');
end
end
