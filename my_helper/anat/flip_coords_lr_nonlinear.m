function newData = flip_coords_lr_nonlinear(csv_file, direction, out_csv, newcol)
%FLIP_COORDS_LR_NONLINEAR Nonlinear L-R flipping of MNI coordinates stored in a CSV.
% USAGE:
%   newData = flip_coords_lr_nonlinear('input.csv','L2R');
%   newData = flip_coords_lr_nonlinear('input.csv','R2L','out.csv');
%   newData = flip_coords_lr_nonlinear('input.csv','L2R','out.csv',true);
%
% INPUTS:
%   csv_file : path to input CSV file containing columns: MNI_x, MNI_y, MNI_z (case-insensitive)
%   direction: 'L2R' (flip from left to right; mask: MNI_x<=0)
%              'R2L' (flip from right to left; mask: MNI_x>0)
%   out_csv  : (optional) path to write the updated table
%   newcol   : (optional) logical flag. If true, results are saved into
%              MNI_x_flip/MNI_y_flip/MNI_z_flip and original columns are untouched.
%              Default = false.
%
% OUTPUTS:
%   newData  : table with updated coordinates d
%
% DEPENDENCY:
%   Requires Lead-DBS function 'ea_flip_lr_nonlinear' on MATLAB path.
%
% Author: Mojack
% Date: 2025/09/26

    arguments
        csv_file (1,:) char
        direction (1,:) char
        out_csv (1,:) char = ''
        newcol (1,1) logical = false
    end

    % --- Validate direction manually ---
    if ~ismember(upper(direction), {'L2R','R2L'})
        error('direction must be "L2R" or "R2L".');
    end

    % --- Check dependency ---
    if exist('ea_flip_lr_nonlinear','file') ~= 2
        error(['Lead-DBS function "ea_flip_lr_nonlinear" not found on path. ', ...
               'Please add Lead-DBS to MATLAB path before running.']);
    end

    % --- Read input table ---
    T = readtable(csv_file, 'VariableNamingRule','preserve');

    % --- Locate coordinate columns (case-insensitive) ---
    varNames = T.Properties.VariableNames;
    ix = find(strcmpi(varNames,'MNI_x'), 1);
    iy = find(strcmpi(varNames,'MNI_y'), 1);
    iz = find(strcmpi(varNames,'MNI_z'), 1);

    if isempty(ix) || isempty(iy) || isempty(iz)
        error('Could not find columns "MNI_x", "MNI_y", "MNI_z".');
    end

    % --- Ensure numeric ---
    T.(varNames{ix}) = ensureNumericColumn(T.(varNames{ix}));
    T.(varNames{iy}) = ensureNumericColumn(T.(varNames{iy}));
    T.(varNames{iz}) = ensureNumericColumn(T.(varNames{iz}));

    % --- Build coords matrix Nx3 ---
    coords = [T.(varNames{ix}), T.(varNames{iy}), T.(varNames{iz})];

    % --- Build mask according to direction ---
    switch upper(direction)
        case 'L2R'
            mask = coords(:,1) <= 0;   % flip only left hemisphere
        case 'R2L'
            mask = coords(:,1) > 0;    % flip only right hemisphere
    end

    % --- Apply nonlinear flip ---
    XYZ = coords;
    if any(mask)
        flipped = ea_flip_lr_nonlinear(coords(mask,:), [], 4);
        XYZ(mask, :) = flipped;
    else
        warning('Mask is empty; no coordinates flipped.');
    end

    % --- Write back results ---
    if newcol
        % Add new columns without touching originals
        T.MNI_x_flip = XYZ(:,1);
        T.MNI_y_flip = XYZ(:,2);
        T.MNI_z_flip = XYZ(:,3);
    else
        % Overwrite existing columns
        T.(varNames{ix}) = XYZ(:,1);
        T.(varNames{iy}) = XYZ(:,2);
        T.(varNames{iz}) = XYZ(:,3);
    end

    newData = T;

    % --- Optional write to CSV ---
    if ~isempty(out_csv)
        % Ensure UTF-8 encoding; quote strings to be safe with commas
        writetable(newData, out_csv, ...
            'FileType','text', ...
            'Encoding','UTF-8', ...
            'WriteVariableNames', true, ...
            'QuoteStrings', true);
    end
end

function v = ensureNumericColumn(v)
% Ensure a vector is numeric; convert if needed
    if isnumeric(v)
        return;
    end
    try
        v = str2double(string(v));
    catch
        error('Failed to convert coordinate column to numeric.');
    end
end