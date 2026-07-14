function key = mh_vta_runtime_cache_key(kind, parts)
% Encode a deterministic runtime-cache key from an explicit tuple.

if ~(ischar(kind) || isstring(kind) && isscalar(kind)) || ...
        ismissing(string(kind)) || strlength(string(kind)) == 0 || ...
        ~iscell(parts)
    error('mh_vta:InvalidSubjectRuntimeCacheKey', ...
        'Cache key kind and tuple parts are required.');
end
payload = struct('kind', char(string(kind)), 'parts', {parts});
key = jsonencode(payload);
end
