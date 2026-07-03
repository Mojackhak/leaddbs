function tableOut = mh_fiber_stnsnr_normalize_contact_table(tableOut)
% Normalize STN/SNr contact mapping tables to shared snake_case columns.

oldNames = {'ID', 'NameEn', 'NameZh', 'Phase', 'Protocol', 'Contact', 'Target', ...
    'Side', 'Voltage', 'PulseWidth', 'Frequency', 'ParameterSource', ...
    'StimulationPattern', 'AlternatingGroup', 'Notes', 'SubjectDir', ...
    'NumContactsPerSide', 'RawContact', 'LeadContact', 'ContactSideRuleOk'};
newNames = {'subject_id', 'name_en', 'name_zh', 'phase', 'protocol', 'contact', ...
    'target', 'side', 'voltage', 'pulse_width', 'frequency', 'parameter_source', ...
    'stimulation_pattern', 'alternating_group', 'notes', 'subject_dir', ...
    'num_contacts_per_side', 'raw_contact', 'lead_contact', 'contact_side_rule_ok'};
tableOut = rename_table_vars(tableOut, oldNames, newNames);

stringVars = {'subject_id', 'patient_name', 'workbook_id', 'name_en', 'name_zh', ...
    'phase', 'protocol', 'target', 'side', 'parameter_source', ...
    'stimulation_pattern', 'alternating_group', 'notes', 'subject_dir'};
tableOut = force_string_vars(tableOut, stringVars);

if ismember('contact_side_rule_ok', tableOut.Properties.VariableNames)
    tableOut.contact_side_rule_ok = force_logical_values(tableOut.contact_side_rule_ok);
end

numericVars = {'contact', 'voltage', 'pulse_width', 'frequency', ...
    'num_contacts_per_side', 'raw_contact', 'lead_contact'};
for i = 1:numel(numericVars)
    if ismember(numericVars{i}, tableOut.Properties.VariableNames)
        tableOut.(numericVars{i}) = force_numeric_values(tableOut.(numericVars{i}), numericVars{i});
    end
end
end

function tableOut = rename_table_vars(tableOut, oldNames, newNames)
for i = 1:numel(oldNames)
    if ismember(oldNames{i}, tableOut.Properties.VariableNames) && ...
            ~ismember(newNames{i}, tableOut.Properties.VariableNames)
        tableOut = renamevars(tableOut, oldNames{i}, newNames{i});
    end
end
end

function tableOut = force_string_vars(tableOut, stringVars)
for i = 1:numel(stringVars)
    if ismember(stringVars{i}, tableOut.Properties.VariableNames)
        tableOut.(stringVars{i}) = string(tableOut.(stringVars{i}));
    end
end
end

function values = force_logical_values(values)
if islogical(values)
    return;
end
if isnumeric(values)
    values = logical(values);
    return;
end
textValues = lower(strtrim(string(values)));
values = ismember(textValues, ["1", "true", "yes"]);
if any(~ismember(textValues, ["0", "false", "no", "1", "true", "yes"]))
    error('mh_fiber_stnsnr_normalize_contact_table:InvalidLogicalColumn', ...
        'Could not parse logical values in contact_side_rule_ok.');
end
end

function values = force_numeric_values(values, variableName)
if isnumeric(values)
    values = double(values);
    return;
end
values = str2double(string(values));
if any(isnan(values))
    error('mh_fiber_stnsnr_normalize_contact_table:InvalidNumericColumn', ...
        'Could not parse numeric values in %s.', variableName);
end
end
