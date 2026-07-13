function path = mh_vta_resolve_native_anchor(defaultPath, overridePath)
% Resolve the production anchor or an explicit acceptance-only override.

path = char(string(defaultPath));
override = char(string(overridePath));
if isempty(override)
    return;
end
if ~isfile(override)
    error('mh_vta:MissingNativeAnchorOverride', ...
        'Native anchor override does not exist: %s', override);
end
path = override;
end
