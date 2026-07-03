function [S, options, stimFolders] = mh_fiber_build_stimulation(cfg)
% Build and save the Lead-DBS stimulation structure for cfg.stimSpec.

if ~isfield(cfg, 'stimSpec') || ~isfield(cfg.stimSpec, 'sources') || isempty(cfg.stimSpec.sources)
    error('mh_fiber_build_stimulation:MissingStimSpec', 'cfg.stimSpec is missing. Call mh_fiber_set_stimulation first.');
end

options = struct();
options = ea_getptopts(cfg.subjectDir, options);
options.root = [fileparts(cfg.subjectDir), filesep];
[~, options.patientname] = fileparts(cfg.subjectDir);
options.leadprod = 'dbs';
options.native = 1;
options.orignative = 1;
options.atlasset = cfg.vta.gmAtlas;

S = ea_initializeS(cfg.stimLabel, options);
S.model = cfg.vta.model;
S.sources = 1:cfg.maxSourcesPerSide;
S.frequency = max([cfg.stimSpec.sources.frequency]);

sideCodes = {'R', 'L'};
sideCounts = struct('R', 0, 'L', 0);
unit = cfg.stimSpec.sources(1).unit;
vaMode = unit_to_va(unit);

for sideIdx = 1:numel(sideCodes)
    sideCode = sideCodes{sideIdx};
    S.amplitude{sideIdx} = zeros(1, cfg.maxSourcesPerSide);
    for sourceIdx = 1:cfg.maxSourcesPerSide
        sourceField = [sideCode, 's', num2str(sourceIdx)];
        S.(sourceField).amp = 0;
        S.(sourceField).va = vaMode;
        S.(sourceField).pulseWidth = 0;
        S.(sourceField).frequency = S.frequency;
        S.(sourceField).case.perc = 0;
        S.(sourceField).case.pol = 0;
        for contactIdx = 1:S.numContacts
            contactField = ['k', num2str(contactIdx)];
            S.(sourceField).(contactField).perc = 0;
            S.(sourceField).(contactField).pol = 0;
        end
    end
end

for i = 1:numel(cfg.stimSpec.sources)
    src = cfg.stimSpec.sources(i);
    sideCode = upper(char(src.side));
    sideIdx = side_to_index(sideCode);
    sideCounts.(sideCode) = sideCounts.(sideCode) + 1;
    sourceIdx = sideCounts.(sideCode);
    sourceField = [sideCode, 's', num2str(sourceIdx)];

    if src.contact > S.numContacts
        error('mh_fiber_build_stimulation:ContactOutOfRange', ...
            'Contact %d is outside electrode contact count %d.', src.contact, S.numContacts);
    end

    S.amplitude{sideIdx}(sourceIdx) = src.amp;
    S.(sourceField).amp = src.amp;
    S.(sourceField).va = unit_to_va(src.unit);
    S.(sourceField).pulseWidth = src.pulseWidth;
    S.(sourceField).frequency = src.frequency;
    S.(sourceField).case.perc = 100;
    S.(sourceField).case.pol = 2;
    S.(sourceField).(['k', num2str(src.contact)]).perc = 100;
    S.(sourceField).(['k', num2str(src.contact)]).pol = 1;
end

S = ea_activecontacts(S);

stimFolders = struct();
stimFolders.native = fullfile(cfg.subjectDir, 'stimulations', ea_nt(1), cfg.stimLabel);
stimFolders.mni = fullfile(cfg.subjectDir, 'stimulations', ea_nt(0), cfg.stimLabel);
mh_util_make_dir(stimFolders.native);
mh_util_make_dir(stimFolders.mni);

save(fullfile(stimFolders.native, [cfg.patientName, '_desc-stimparameters.mat']), 'S');
save(fullfile(stimFolders.mni, [cfg.patientName, '_desc-stimparameters.mat']), 'S');

end

function sideIdx = side_to_index(sideCode)
switch upper(sideCode)
    case 'R'
        sideIdx = 1;
    case 'L'
        sideIdx = 2;
    otherwise
        error('mh_fiber_build_stimulation:InvalidSide', 'Invalid side: %s', sideCode);
end
end

function vaMode = unit_to_va(unit)
switch lower(char(string(unit)))
    case 'v'
        vaMode = 1;
    case 'ma'
        vaMode = 2;
    otherwise
        error('mh_fiber_build_stimulation:InvalidUnit', 'Unsupported stimulation unit: %s', unit);
end
end
