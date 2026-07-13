function space=ea_getspace

override = strtrim(getenv('LEADDBS_SPACE_OVERRIDE'));
if ~isempty(override)
    if contains(override, {'/', '\\'}) || ...
            ~isfolder(fullfile(ea_getearoot, 'templates', 'space', override))
        error('ea_getspace:InvalidProcessOverride', ...
            'Invalid LEADDBS_SPACE_OVERRIDE value: %s', override);
    end
    space = override;
    return
end

prefsPath = ea_prefspath('mat');

if ~isfile(prefsPath)
    copyfile([ea_getearoot,'common',filesep,'ea_prefs_default.mat'], prefsPath, 'f');
end

load(prefsPath, 'machine');
space = machine.space;
