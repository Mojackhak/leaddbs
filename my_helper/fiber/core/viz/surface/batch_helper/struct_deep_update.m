function out = struct_deep_update(base, override)
%STRUCT_DEEP_UPDATE Recursively update a struct using another struct.
%
% Rules:
% - If a field exists in override:
%     - If both base.(f) and override.(f) are structs -> recurse
%     - Else -> replace base.(f) with override.(f)
% - Fields that exist only in override are added to the output.

    out = base;

    if isempty(override)
        return;
    end

    fns = fieldnames(override);
    for i = 1:numel(fns)
        fn = fns{i};
        ov = override.(fn);

        if isfield(out, fn)
            bv = out.(fn);
            if isstruct(bv) && isstruct(ov)
                out.(fn) = struct_deep_update(bv, ov);
            else
                out.(fn) = ov;
            end
        else
            % allow new fields (useful for adding extra Lead-DBS name-value options)
            out.(fn) = ov;
        end
    end
end