function mh_vta_runtime_cache_store(runtime, cacheName, key, value)
% Store one exact-key value in an explicit subject runtime cache.

mh_vta_runtime_cache_lookup(runtime, cacheName, key);
cache = runtime.caches.(char(string(cacheName)));
cache(char(string(key))) = value; %#ok<NASGU>
end
