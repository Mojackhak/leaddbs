function [value, hit] = mh_vta_runtime_cache_lookup(runtime, cacheName, key)
% Read one exact-key value from an explicit subject runtime cache.

cache = select_cache(runtime, cacheName);
key = validate_key(key);
hit = isKey(cache, key);
if hit
    value = cache(key);
else
    value = [];
end
end

function cache = select_cache(runtime, cacheName)
if ~isstruct(runtime) || ~isscalar(runtime) || ...
        ~isfield(runtime, 'schema_version') || ...
        ~strcmp(runtime.schema_version, 'vta_subject_runtime_v1') || ...
        ~isfield(runtime, 'caches') || ...
        ~(ischar(cacheName) || isstring(cacheName) && isscalar(cacheName))
    error('mh_vta:InvalidSubjectRuntime', ...
        'Runtime cache lookup requires a valid subject runtime.');
end
name = char(string(cacheName));
if ~isfield(runtime.caches, name) || ...
        ~isa(runtime.caches.(name), 'containers.Map')
    error('mh_vta:InvalidSubjectRuntimeCache', ...
        'Unknown subject runtime cache: %s', name);
end
cache = runtime.caches.(name);
end

function key = validate_key(key)
if ~(ischar(key) || isstring(key) && isscalar(key)) || ...
        ismissing(string(key)) || strlength(string(key)) == 0
    error('mh_vta:InvalidSubjectRuntimeCacheKey', ...
        'Runtime cache keys must be nonempty scalar text.');
end
key = char(string(key));
end
