function nifti_files = find_heatmap_niftis(root_dir, varargin)
%DBSLFP_FIND_HEATMAP_NIFTIS Recursively find NIfTI files whose path contains a token.
%
% nifti_files = find_heatmap_niftis(root_dir, ...)
%
% Required:
%   root_dir: root folder to search.
%
% Name-value options:
%   'PathMustContain' (char/string): substring that must appear in the full path.
%   'Extensions'      (string array): extensions to include, e.g. [".nii", ".nii.gz"].
%   'IgnoreCase'      (logical): case-insensitive matching (default true).
%
% Returns:
%   nifti_files: sorted string array of absolute file paths.

    p = inputParser;
    p.addRequired('root_dir', @(x) ischar(x) || isstring(x));
    p.addParameter('PathMustContain', 'heatmap', @(x) ischar(x) || isstring(x));
    p.addParameter('Extensions', [".nii", ".nii.gz"], @(x) isstring(x) || iscellstr(x) || ischar(x));
    p.addParameter('IgnoreCase', true, @(x) islogical(x) && isscalar(x));
    p.parse(root_dir, varargin{:});

    root_dir = char(p.Results.root_dir);
    token = char(p.Results.PathMustContain);

    exts = p.Results.Extensions;
    if ischar(exts)
        exts = string({exts});
    elseif iscellstr(exts)
        exts = string(exts);
    else
        exts = string(exts);
    end

    ignore_case = p.Results.IgnoreCase;

    if ~exist(root_dir, 'dir')
        error('root_dir not found: %s', root_dir);
    end

    % Normalize matching behavior.
    if ignore_case
        token_cmp = lower(token);
        exts_cmp = lower(exts);
    else
        token_cmp = token;
        exts_cmp = exts;
    end

    files_cell = {};

    % Iterative DFS to avoid recursion depth issues.
    stack = {root_dir};
    while ~isempty(stack)
        cur_dir = stack{end};
        stack(end) = [];

        d = dir(cur_dir);
        for i = 1:numel(d)
            name = d(i).name;
            if strcmp(name, '.') || strcmp(name, '..')
                continue;
            end

            fp = fullfile(cur_dir, name);

            if d(i).isdir
                stack{end+1} = fp; %#ok<AGROW>
                continue;
            end

            % Extension check (supports .nii.gz).
            fp_cmp = fp;
            if ignore_case
                fp_cmp = lower(fp_cmp);
            end

            has_ext = false;
            for e = 1:numel(exts_cmp)
                if endsWith(fp_cmp, exts_cmp(e))
                    has_ext = true;
                    break;
                end
            end
            if ~has_ext
                continue;
            end

            % Path token filter.
            if ~contains(fp_cmp, token_cmp)
                continue;
            end

            files_cell{end+1} = fp; %#ok<AGROW>
        end
    end

    nifti_files = sort(string(files_cell(:)));
end
