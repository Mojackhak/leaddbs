function region_key = canonical_region_key(region)
%DBSLFP_CANONICAL_REGION_KEY Normalize region strings to consistent struct keys.
%
% This helper keeps your historical naming:
%   - STN
%   - SNr
%
% Unknown regions are returned unchanged.

    r = lower(strtrim(string(region)));

    switch r
        case "stn"
            region_key = "STN";
        case "snr"
            region_key = "SNr";
        otherwise
            region_key = strtrim(string(region));
    end
end
