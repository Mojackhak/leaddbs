function out = mh_util_sanitize_label(value)
% Convert free text into a filesystem-safe analysis label.

out = char(string(value));
out = regexprep(out, '\+', 'plus');
out = regexprep(out, '[^A-Za-z0-9_+-]+', '_');
out = regexprep(out, '_+', '_');
out = regexprep(out, '^_|_$', '');
end
