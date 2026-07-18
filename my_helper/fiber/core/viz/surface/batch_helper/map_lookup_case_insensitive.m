function val = map_lookup_case_insensitive(m, key, default_val)
%DBSLFP_MAP_LOOKUP_CASE_INSENSITIVE Case-insensitive lookup for containers.Map.
%
% val = map_lookup_case_insensitive(m, key, default_val)
%
% Inputs:
%   m: containers.Map
%   key: lookup key (char/string)
%   default_val: returned when not found
%
% Returns:
%   val: mapped value or default_val

    val = default_val;
    if isempty(key)
        return;
    end

    key = char(string(key));
    if isKey(m, key)
        val = m(key);
        return;
    end

    klist = m.keys;
    for i = 1:numel(klist)
        if strcmpi(klist{i}, key)
            val = m(klist{i});
            return;
        end
    end
end
