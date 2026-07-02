function values = mh_fiber_split_env_list(rawValue)
% Split comma- or semicolon-delimited environment variable values.

if isempty(rawValue)
    values = strings(0, 1);
    return;
end

parts = string(regexp(rawValue, '[,;]+', 'split'));
values = strtrim(parts(:));
values = values(values ~= "");
