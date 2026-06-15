% EXAMPLE CALL
% ────────────
%   projectFolder = 'A:\STNSNr\derivatives\leaddbs';
%   dist_table = readtable('A:\STNSNr\summary\spike\MER_loc_contact_clean.csv');
%   result_table = dist2space_coords_batch_table(projectFolder, dist_table)
%
% Written by Mojack, 2025-08-22
%----------------------------------


function result_table = dist2space_coords_batch_table(projectFolder, dist_table)

subjFolders = dir(projectFolder);
subjFolders = subjFolders([subjFolders.isdir]);  % Keep only directories
subjFolders = subjFolders(~ismember({subjFolders.name}, {'.', '..'}));  % Remove . and ..

% Loop through each raw
result_table = dist_table;
result_table.mni = cell(height(dist_table),1);
for i = 1:height(dist_table) % Fixed variable name
    offset = dist_table{i,"offset_contact0"}{:};
    offset = str2num(offset);
    dist = dist_table{i,"depth"};
    side = dist_table{i, "side"}{:};
    if side == 'L'
        offset = {[0,0,0], offset};
        dist = {0,dist};
    elseif side == 'R'
        offset = {offset, [0,0,0]};
        dist = {dist, 0};
    end
    subj = dist_table{i,"subject"}{:};
    subj = ['sub-' subj];
    % Get the full path to the current subject folder
    currentSubjFolder = fullfile(projectFolder, subj);  
    if exist(currentSubjFolder, "dir") == 7 % folder exists
        coords = dist2space_coords(currentSubjFolder, dist, offset);
        if side == 'L'
            mni = coords.mni{1,2};
        elseif side == 'R'
            mni = coords.mni{1,1};
        end
        result_table{i,"mni"} = {mni};
    end
end
end

