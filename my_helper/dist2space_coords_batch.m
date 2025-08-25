% EXAMPLE CALL
% ────────────
%   projectFolder = 'A:\STNSNr\derivatives\leaddbs';
%   dist       = {linspace(1,13,7), linspace(1,13,7)};
%   offset     = {0, 0};
%   fileName   = 'contact_space_coords.mat';
%   dist2space_coords_batch(projectFolder, dist, offset, fileName);
%
% Written by Mojack, 2025-08-06
%----------------------------------


function dist2space_coords_batch(projectFolder, dist, offset, fileName)

subjFolders = dir(projectFolder);
subjFolders = subjFolders([subjFolders.isdir]);  % Keep only directories
subjFolders = subjFolders(~ismember({subjFolders.name}, {'.', '..'}));  % Remove . and ..

% Loop through each subject folder
for i = 1:length(subjFolders) % Fixed variable name
    % Get the full path to the current subject folder
    currentSubjFolder = fullfile(projectFolder, subjFolders(i).name);
    
    fprintf('Processing subject: %s\n', subjFolders(i).name);
    coords = dist2space_coords(currentSubjFolder, dist, offset, fileName);
    fprintf('Successfully processed %s\n', subjFolders(i).name);

end

