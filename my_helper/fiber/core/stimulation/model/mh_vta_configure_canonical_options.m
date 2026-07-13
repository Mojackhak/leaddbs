function options = mh_vta_configure_canonical_options(options, task)
% Apply fixed tissue and atlas settings for canonical VTA execution.

atlasSet = char(string(task.model.atlas_set));
options.atlasset = atlasSet;
options.prefs.vat.gm = 'mask';
options.prefs.machine.vatsettings.horn_cgm = ...
    double(task.model.gray_matter_s_per_m);
options.prefs.machine.vatsettings.horn_cwm = ...
    double(task.model.white_matter_s_per_m);
options.prefs.machine.vatsettings.horn_useatlas = 1;
options.prefs.machine.vatsettings.horn_atlasset = atlasSet;
options.prefs.machine.vatsettings.horn_removeElectrode = 1;
end
