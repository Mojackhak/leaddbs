function contacts = mh_fiber_write_contacts_report(cfg, dirs)
% Write contact coordinates and active stimulation settings to CSV/Markdown.

stimParamPath = fullfile(cfg.paths.stimNative, [cfg.patientName, '_desc-stimparameters.mat']);
if ~isfile(stimParamPath)
    error('mh_fiber_write_contacts_report:MissingStimParameters', ...
        'Stimulation parameter file is missing: %s', stimParamPath);
end

stimData = load(stimParamPath, 'S');
S = stimData.S;

options = struct();
options = ea_getptopts(cfg.subjectDir, options);
options.root = [fileparts(cfg.subjectDir), filesep];
[~, options.patientname] = fileparts(cfg.subjectDir);
options.leadprod = 'dbs';
[coords_mm] = ea_load_reconstruction(options);

recoData = load(cfg.paths.reconstruction, 'reco');
reco = recoData.reco;

rows = {};
sideSpecs = {1, 'R'; 2, 'L'};
for s = 1:size(sideSpecs, 1)
    sideIndex = sideSpecs{s, 1};
    side = sideSpecs{s, 2};
    electrodeModel = '';
    if isfield(reco, 'props') && numel(reco.props) >= sideIndex && isfield(reco.props(sideIndex), 'elmodel')
        electrodeModel = reco.props(sideIndex).elmodel;
    end

    coords = coords_mm{sideIndex};
    for contact = 1:size(coords, 1)
        activeRows = source_rows_for_contact(S, side, contact);
        if isempty(activeRows)
            rows(end+1, :) = {side, sideIndex, contact, coords(contact, 1), coords(contact, 2), coords(contact, 3), ...
                electrodeModel, false, '', NaN, '', NaN, NaN, '', ''}; %#ok<AGROW>
        else
            for r = 1:size(activeRows, 1)
                rows(end+1, :) = {side, sideIndex, contact, coords(contact, 1), coords(contact, 2), coords(contact, 3), ...
                    electrodeModel, true, activeRows{r, 1}, activeRows{r, 2}, activeRows{r, 3}, ...
                    activeRows{r, 4}, activeRows{r, 5}, activeRows{r, 6}, activeRows{r, 7}}; %#ok<AGROW>
            end
        end
    end
end

contactsTable = cell2table(rows, 'VariableNames', { ...
    'side', 'lead_dbs_side_index', 'contact', 'x_mm', 'y_mm', 'z_mm', ...
    'electrode_model', 'active', 'source', 'amplitude', 'unit', ...
    'frequency_hz', 'pulse_width_us', 'contact_polarity', 'anode'});

contacts = struct();
contacts.table = contactsTable;
contacts.csv = fullfile(dirs.reports, 'contacts_report.csv');
contacts.md = fullfile(dirs.reports, 'contacts_report.md');
writetable(contactsTable, contacts.csv);
write_contacts_markdown(contacts.md, cfg, contactsTable);

end

function rows = source_rows_for_contact(S, side, contact)
rows = {};
for source = 1:4
    sourceField = [side, 's', num2str(source)];
    contactField = ['k', num2str(contact)];
    if ~isfield(S, sourceField) || ~isfield(S.(sourceField), contactField)
        continue;
    end
    stimSource = S.(sourceField);
    contactStim = stimSource.(contactField);
    if contactStim.perc <= 0 || stimSource.amp <= 0
        continue;
    end
    if contactStim.pol == 1
        contactPolarity = 'cathode';
    elseif contactStim.pol == 2
        contactPolarity = 'anode';
    else
        contactPolarity = 'off';
    end
    if stimSource.va == 1
        unit = 'V';
    else
        unit = 'mA';
    end
    anode = '';
    if isfield(stimSource, 'case') && stimSource.case.perc > 0 && stimSource.case.pol == 2
        anode = 'case';
    end
    rows(end+1, :) = {sourceField, stimSource.amp, unit, stimSource.frequency, ...
        stimSource.pulseWidth, contactPolarity, anode}; %#ok<AGROW>
end
end

function write_contacts_markdown(path, cfg, contacts)
fid = fopen(path, 'w');
if fid < 0
    error('mh_fiber_write_contacts_report:ReportOpenFailed', 'Cannot write contacts report: %s', path);
end
cleanup = onCleanup(@() fclose(fid));

fprintf(fid, '# Contacts Report\n\n');
fprintf(fid, '- Subject: `%s`\n', cfg.patientName);
fprintf(fid, '- Stimulation label: `%s`\n', cfg.stimLabel);
fprintf(fid, '- Lead-DBS side convention: `side 1 = R`, `side 2 = L`\n\n');
fprintf(fid, '| Side | Contact | X | Y | Z | Model | Active | Source | Amplitude | Frequency | Pulse width | Polarity | Anode |\n');
fprintf(fid, '|---|---:|---:|---:|---:|---|---|---|---:|---:|---:|---|---|\n');
for i = 1:height(contacts)
    fprintf(fid, '| %s | %d | %.3f | %.3f | %.3f | %s | %d | %s | %.3f %s | %.3f | %.3f | %s | %s |\n', ...
        contacts.side{i}, contacts.contact(i), contacts.x_mm(i), contacts.y_mm(i), contacts.z_mm(i), ...
        contacts.electrode_model{i}, contacts.active(i), contacts.source{i}, contacts.amplitude(i), ...
        contacts.unit{i}, contacts.frequency_hz(i), contacts.pulse_width_us(i), ...
        contacts.contact_polarity{i}, contacts.anode{i});
end
end
