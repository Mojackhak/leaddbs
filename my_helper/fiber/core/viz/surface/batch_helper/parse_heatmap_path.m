function info = parse_heatmap_path(nifti_path, section_dir)
%DBSLFP_PARSE_HEATMAP_PATH Infer parameters from a heatmap NIfTI path.
%
% Expected folder structure (somewhere under section_dir) is:
%   {param_type}/<band>/<region>/<var>/<file>.nii[.gz]
%
% Where:
%   - var is the folder that directly contains the NIfTI file.
%
% Example:
%   .../tfr/period/period-mean/Delta/STN/some_var/map.nii.gz
%
% Inputs:
%   nifti_path (char/string): path to the NIfTI file.
%   section_dir (char/string): root folder used to derive a relative path.
%
% Returns:
%   info: struct with fields:
%     - nifti_path (string)
%     - rel_path (string)
%     - param_type (string)
%     - band (string)
%     - region (string)
%     - region_key (string)
%     - var (string)
%     - file (string)          % filename (with extension)

    nifti_path  = string(nifti_path);
    section_dir = string(section_dir);

    if ~isfile(nifti_path)
        error('NIfTI file not found: %s', nifti_path);
    end
    if ~isfolder(section_dir)
        error('section_dir not found: %s', section_dir);
    end

    % ---- Best-effort relative path (for readability/debugging) ----
    rel = nifti_path;
    prefix = section_dir;

    if startsWith(rel, prefix)
        rel = extractAfter(rel, strlength(prefix));
        if startsWith(rel, filesep)
            rel = extractAfter(rel, 1);
        end
    end

    % Split into parts
    parts = split(rel, filesep);
    parts = parts(parts ~= "");

    % Need at least: param_type / band / region / var / file
    if numel(parts) < 5
        error(['Could not infer param_type/band/region/var: expected ', ...
               '"{param_type}/<band>/<region>/<var>/<file>.nii[.gz]". path=%s'], nifti_path);
    end

    % Anchor on file location:
    %   var is the folder that directly contains the file
    file = parts(end);
    var = parts(end - 1);
    region = parts(end - 2);
    band = parts(end - 3);
    param_type = parts(end - 4);

    region_key = canonical_region_key(region);

    info = struct();
    info.nifti_path = nifti_path;
    info.rel_path = rel;
    info.param_type = param_type;
    info.band = band;
    info.region = region;
    info.region_key = region_key;
    info.var = var;
    info.file = file;
end
