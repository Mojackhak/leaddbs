function signature = mh_vta_file_signature(path)
% Return path, size, and available timestamp precision for a cache key.

canonical = mh_vta_canonical_path(path);
entry = dir(canonical);
if isempty(entry)
    signature = {canonical, -1, -1};
    return;
end
entry = entry(1);
signature = {canonical, double(entry.bytes), double(entry.datenum)};
end
