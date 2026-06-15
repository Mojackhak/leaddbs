% ProjectPath = '/Volumes/Data/STNSNr/summary/r_coords';
% targetCoordsCsv = '/Volumes/Data/atlas/TargetCoords.csv';

function report = add_relative_coords_to_csvs(ProjectPath, targetCoordsCsv)
% ADD_RELATIVE_COORDS_TO_CSVS
% For each CSV in filePaths:
%   1) Flip coords L->R nonlinearly (adds MNI_*_flip columns).
%   2) Read TargetCoords (with columns: Side, SNr_x/y/z, STN_x/y/z).
%   3) Compute relative coords to STN and SNr RIGHT-hemisphere centers:
%        STN_rel_{x,y,z} = MNI_{x,y,z}_flip - STN_{x,y,z}_Right
%        SNr_rel_{x,y,z} = MNI_{x,y,z}_flip - SNr_{x,y,z}_Right
%   4) Overwrite the CSV file in place.
%
% Inputs:
%   filePaths      - cellstr of CSV filepaths
%   targetCoordsCsv- path to TargetCoords.csv (columns:
%                    Side, SNr_x, SNr_y, SNr_z, STN_x, STN_y, STN_z)
%
% Output:
%   report - struct array with fields: file, ok (logical), message (string)
%
% REQUIREMENTS:
%   - flip_coords_lr_nonlinear (your helper) on path.
%   - Lead-DBS 'ea_flip_lr_nonlinear' reachable (used by your helper).
%
% Author: (Mojack)
    
    filePaths = list_csv_level3_filtered(ProjectPath);

    % ---- Load target centers (expects Left/Right rows) ----
    TT = readtable(targetCoordsCsv, 'VariableNamingRule','preserve');
    % Find RIGHT row; be strict and explicit
    sideVar = find(strcmpi(TT.Properties.VariableNames, 'Side'), 1);
    if isempty(sideVar)
        error('TargetCoords must contain a ''Side'' column with ''Right'' and ''Left'' rows.');
    end
    sideVals = TT.(TT.Properties.VariableNames{sideVar});
    rightMask = strcmpi(string(sideVals), "Right");
    if nnz(rightMask) ~= 1
        error('TargetCoords must contain exactly one ''Right'' row.');
    end

    % Extract RIGHT centers (case-insensitive field lookup)
    STN_x = getNumericCol(TT, 'STN_x', rightMask);
    STN_y = getNumericCol(TT, 'STN_y', rightMask);
    STN_z = getNumericCol(TT, 'STN_z', rightMask);
    SNr_x = getNumericCol(TT, 'SNr_x', rightMask);
    SNr_y = getNumericCol(TT, 'SNr_y', rightMask);
    SNr_z = getNumericCol(TT, 'SNr_z', rightMask);
    STN_R = [STN_x, STN_y, STN_z];
    SNr_R = [SNr_x, SNr_y, SNr_z];

    % ---- Iterate over files ----
    report = repmat(struct('file','', 'ok',false, 'message',''), numel(filePaths), 1);

    for i = 1:numel(filePaths)
        fp = filePaths{i};
        report(i).file = fp;

        try
            if ~exist(fp, 'file')
                error('File not found.');
            end

            % 1) Flip L->R (adds MNI_x_flip/y_flip/z_flip, keeps originals)
            T = flip_coords_lr_nonlinear(fp, 'L2R', '', true);

            % 2) Decide which coordinate columns to use (prefer *_flip)
            useFlip = hasVar(T, 'MNI_x_flip') && hasVar(T, 'MNI_y_flip') && hasVar(T, 'MNI_z_flip');
            if useFlip
                xname = getVarName(T, 'MNI_x_flip');
                yname = getVarName(T, 'MNI_y_flip');
                zname = getVarName(T, 'MNI_z_flip');

            end
            if any(cellfun(@isempty, {xname,yname,zname}))
                error('Could not find MNI coordinate columns.');
            end

            % Ensure numeric
            x = ensureNumeric(T.(xname));
            y = ensureNumeric(T.(yname));
            z = ensureNumeric(T.(zname));

            % 3) Compute relative coords to RIGHT-hemisphere centers
            T.STN_rel_x = x - STN_R(1);
            T.STN_rel_y = y - STN_R(2);
            T.STN_rel_z = z - STN_R(3);

            T.SNr_rel_x = x - SNr_R(1);
            T.SNr_rel_y = y - SNr_R(2);
            T.SNr_rel_z = z - SNr_R(3);

            % 4) Overwrite CSV
            writetable(T, fp, ...
                'FileType','text', 'Encoding','UTF-8', ...
                'WriteVariableNames', true, 'QuoteStrings', true);

            report(i).ok = true;
            report(i).message = 'OK';

        catch ME
            report(i).ok = false;
            report(i).message = ME.message;
            % Continue to next file
        end
    end
end

% --------- helpers ---------
function tf = hasVar(T, name)
    tf = any(strcmpi(T.Properties.VariableNames, name));
end

function vn = getVarName(T, name)
    ix = find(strcmpi(T.Properties.VariableNames, name), 1);
    if isempty(ix), vn = ''; else, vn = T.Properties.VariableNames{ix}; end
end

function v = getNumericCol(T, name, mask)
    vn = getVarName(T, name);
    if isempty(vn)
        error('TargetCoords is missing column: %s', name);
    end
    col = T.(vn);
    if istable(col) || isstruct(col)
        error('Unexpected non-vector column: %s', name);
    end
    col = ensureNumeric(col);
    v = col(mask);
end

function v = ensureNumeric(v)
    if isnumeric(v)
        return;
    end
    try
        v = str2double(string(v));
    catch
        error('Failed converting a column to numeric.');
    end
end

function filePaths = list_csv_level3_filtered(folderPath)
% LIST_CSV_LEVEL3_FILTERED
% Return full paths to .csv files under folderPath that:
%   1) are exactly in the 3rd-level subfolder (root/lev1/lev2/lev3/file.csv),
%   2) file name does NOT start with '.',
%   3) path does NOT contain 'trace',
%   4) path DOES contain 'bandpower' OR 'burst'.
% Matching for (3)–(4) is case-insensitive.
%
% Usage:
%   files = list_csv_level3_filtered('/root');

    if ~(ischar(folderPath) || isstring(folderPath))
        error('folderPath must be char or string.');
    end

    % Normalize root (remove trailing file separator)
    root = char(folderPath);
    if ~isempty(root) && root(end) == filesep
        root(end) = [];
    end
    if ~exist(root, 'dir')
        error('Folder does not exist: %s', root);
    end

    % Recursively find CSV files (cover .csv and .CSV)
    L = dir(fullfile(root, '**', '*.csv'));
    U = dir(fullfile(root, '**', '*.CSV'));
    files = [L(:); U(:)];

    % Keep only files (not directories)
    if isempty(files)
        filePaths = {};
        return;
    end
    files = files(~[files.isdir]);

    % Exclude dotfiles (filename starts with '.')
    isDot = arrayfun(@(f) startsWith(f.name, '.'), files);
    files = files(~isDot);

    % Build full paths
    allPaths = fullfile({files.folder}, {files.name});

    % Case-insensitive keyword filters on full path
    lowPaths = lower(allPaths);
    keep = (contains(lowPaths, 'bandpower') | contains(lowPaths, 'burst') | ...
            contains(lowPaths, 'params')) & ...
            ~contains(lowPaths, 'trace');

    allPaths = allPaths(keep);
    if isempty(allPaths)
        filePaths = {};
        return;
    end

    % Keep ONLY files exactly 3 subfolders under root:
    % root/lev1/lev2/lev3/file.csv  -> depth = 3
    maskLevel3 = false(size(allPaths));
    rootLen = length(root);

    for i = 1:numel(allPaths)
        % Folder containing the file
        fldr = fileparts(allPaths{i});

        % Must be under root and next char must be a separator (boundary-safe)
        if strncmp(fldr, root, rootLen)
            if length(fldr) == rootLen
                rel = '';  % directly at root
            elseif length(fldr) > rootLen && fldr(rootLen+1) == filesep
                rel = fldr(rootLen+2:end);  % skip separator
            else
                rel = '';  % not truly under root boundary
            end
        else
            rel = '';
        end

        % Count subfolder depth from root
        if isempty(rel)
            depth = 0;
        else
            % Number of segments = number of separators + 1
            depth = 1 + sum(rel == filesep);
        end

        maskLevel3(i) = (depth == 3);
    end

    filePaths = allPaths(maskLevel3);
end