function repoDir = mh_util_resolve_repo_dir(startPath)
% Resolve the Lead-DBS repository root from a path inside the repository.

repoDir = fileparts(startPath);
while ~isempty(repoDir)
    hasLeadDbsShape = isfolder(fullfile(repoDir, 'templates')) && ...
        isfolder(fullfile(repoDir, 'ea_modules')) && ...
        isfolder(fullfile(repoDir, 'my_helper'));
    if hasLeadDbsShape || isfolder(fullfile(repoDir, '.git'))
        return;
    end
    parent = fileparts(repoDir);
    if strcmp(parent, repoDir)
        break;
    end
    repoDir = parent;
end

fallback = '/Users/mojackhu/Github/leaddbs';
if isfolder(fallback)
    repoDir = fallback;
else
    repoDir = pwd;
end
end
