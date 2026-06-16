function [cfg, S, options, stimFolders] = mh_fiber_build_l2_l5to8_stimulation(cfg, vtaMode)
% Build the current clinical L2/R2 plus L5-L8/R5-R8 stimulation setting.

if nargin < 2 || strlength(string(vtaMode)) == 0
    vtaMode = 'lead_dbs_twosource';
end

stimSpec = mh_fiber_stimspec_from_table([
    "L", 2, 3.0, 120, 130
    "R", 2, 3.0, 120, 130
    "L", 5, 5.0, 120, 130
    "R", 5, 5.0, 120, 130
], "case", ...
    'Label', cfg.stimLabel, ...
    'Model', cfg.vta.modelKey, ...
    'Space', cfg.vta.space, ...
    'Unit', 'V');

cfg = mh_fiber_set_stimulation(cfg, stimSpec);
[S, options, stimFolders] = mh_fiber_build_stimulation(cfg);

S = set_voltage_group(S, 'L', 2, 5:8, 5.0);
S = set_voltage_group(S, 'R', 2, 5:8, 5.0);
S = ea_activecontacts(S);

S.mh_fiber = struct();
S.mh_fiber.vta_mode = char(string(vtaMode));
S.mh_fiber.global_contact_convention = 'left 0-7, right 8-15';
S.mh_fiber.global_to_leaddbs = table( ...
    [1; 9; 4; 5; 6; 7; 12; 13; 14; 15], ...
    {'L'; 'R'; 'L'; 'L'; 'L'; 'L'; 'R'; 'R'; 'R'; 'R'}, ...
    [2; 2; 5; 6; 7; 8; 5; 6; 7; 8], ...
    [3; 3; 5; 5; 5; 5; 5; 5; 5; 5], ...
    'VariableNames', {'global_contact', 'side', 'lead_dbs_contact', 'amplitude_v'});

save(fullfile(stimFolders.native, [cfg.patientName, '_desc-stimparameters.mat']), 'S');
save(fullfile(stimFolders.mni, [cfg.patientName, '_desc-stimparameters.mat']), 'S');
end

function S = set_voltage_group(S, sideCode, sourceIdx, contacts, amplitude)
sourceField = [sideCode, 's', num2str(sourceIdx)];
if ~isfield(S, sourceField)
    error('mh_fiber_build_l2_l5to8_stimulation:MissingSource', ...
        'Missing stimulation source: %s', sourceField);
end

S.(sourceField).amp = amplitude;
S.(sourceField).va = 1;
S.(sourceField).pulseWidth = 120;
S.(sourceField).frequency = 130;
S.(sourceField).case.perc = 100;
S.(sourceField).case.pol = 2;

for contact = 1:S.numContacts
    contactField = ['k', num2str(contact)];
    S.(sourceField).(contactField).perc = 0;
    S.(sourceField).(contactField).pol = 0;
end

for contact = contacts
    contactField = ['k', num2str(contact)];
    S.(sourceField).(contactField).perc = 100;
    S.(sourceField).(contactField).pol = 1;
end
end
