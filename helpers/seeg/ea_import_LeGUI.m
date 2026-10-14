function ea_import_LeGUI(dataset, subjId, LeGUIdir, space)
% Import coordinates into an existing subject without replacing its images.
arguments
    dataset {mustBeTextScalar}
    subjId {mustBeTextScalar}
    LeGUIdir {mustBeTextScalar}
    space {mustBeMember(space, {'native', 'mni'})} = 'mni'
end
subject = erase(subjId, textBoundary('start') + 'sub-');
options = ea_getptopts(fullfile(dataset, 'derivatives', 'leaddbs', ['sub-', char(subject)]));
options.hybridsave = 1;
legui2reco(options, fullfile(LeGUIdir, 'Registered', 'Electrodes.mat'), space);
end
