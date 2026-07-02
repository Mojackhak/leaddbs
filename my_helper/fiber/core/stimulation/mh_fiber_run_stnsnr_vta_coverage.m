function result = mh_fiber_run_stnsnr_vta_coverage(varargin)
% Compute STN/SNr VTA coverage summaries for the STN/SNr cohort.

parser = inputParser;
parser.FunctionName = 'mh_fiber_run_stnsnr_vta_coverage';
parser.addParameter('RepoDir', '', @(x) ischar(x) || isstring(x));
parser.addParameter('SubjectRoot', '/Volumes/VAL/STNSNr/derivatives/leaddbs', @(x) ischar(x) || isstring(x));
parser.addParameter('Workbook', '/Users/mojackhu/Research/STNSNr/summary/cohort/subj/followup_stimulation.xlsx', @(x) ischar(x) || isstring(x));
parser.addParameter('Sheet', 'Contact Parameters', @(x) ischar(x) || isstring(x));
parser.addParameter('AtlasDir', '', @(x) ischar(x) || isstring(x));
parser.addParameter('CohortOutputDir', '/Volumes/VAL/STNSNr/summary/vta', @(x) ischar(x) || isstring(x));
parser.addParameter('ThresholdsVPerMm', [0.18, 0.20, 0.22], @(x) isnumeric(x) && isvector(x));
parser.addParameter('MainThresholdVPerMm', 0.20, @(x) isnumeric(x) && isscalar(x));
parser.addParameter('OutputVoxelSizeMm', 0.5, @(x) isnumeric(x) && isscalar(x) && x > 0);
parser.addParameter('ForceVta', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('ForceOutputs', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('StopOnSubjectError', true, @(x) islogical(x) || isnumeric(x));
parser.addParameter('SubjectIDs', strings(0, 1), @is_string_list);
parser.addParameter('SubjectNames', strings(0, 1), @is_string_list);
parser.addParameter('WriteCohortOutputs', true, @(x) islogical(x) || isnumeric(x));
parser.addParameter('CohortOnly', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('SkipCompletedSubjects', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('UseSubjectLocks', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('SkipLockedSubjects', false, @(x) islogical(x) || isnumeric(x));
parser.parse(varargin{:});
opts = parser.Results;

repoDir = char(string(opts.RepoDir));
if isempty(repoDir)
    repoDir = resolve_repo_dir(mfilename('fullpath'));
end
subjectRoot = char(string(opts.SubjectRoot));
workbook = char(string(opts.Workbook));
sheetName = char(string(opts.Sheet));
atlasDir = char(string(opts.AtlasDir));
if isempty(atlasDir)
    atlasDir = fullfile(repoDir, 'templates', 'space', 'MNI152NLin2009bAsym', ...
        'atlases', 'Custom_Ewert_Zhang_Middlebrooks0.05');
end
cohortOutputDir = char(string(opts.CohortOutputDir));

must_be_folder(repoDir, 'repository directory');
must_be_folder(subjectRoot, 'Lead-DBS subject root');
must_be_file(workbook, 'stimulation workbook');
must_be_folder(atlasDir, 'STN/SNr atlas directory');
verify_atlas_files(atlasDir);

thresholdsVPerMm = unique(double(opts.ThresholdsVPerMm(:))', 'stable');
thresholdsVPerM = thresholdsVPerMm .* 1000;
mainThreshold = double(opts.MainThresholdVPerMm);
exportThreshold = min(thresholdsVPerMm);

rows = read_stimulation_rows(workbook, sheetName);
validate_workbook_rows(rows);

subjects = unique(rows(:, {'ID', 'NameEn', 'NameZh'}), 'rows', 'stable');
if height(subjects) ~= 16
    error('mh_fiber_run_stnsnr_vta_coverage:UnexpectedSubjectCount', ...
        'Expected 16 subjects, found %d.', height(subjects));
end
subjects = filter_subjects(subjects, opts.SubjectIDs, opts.SubjectNames);
if height(subjects) == 0
    error('mh_fiber_run_stnsnr_vta_coverage:NoSelectedSubjects', ...
        'No subjects matched the requested subject filter.');
end

make_dir(cohortOutputDir);
make_dir(fullfile(cohortOutputDir, 'figures'));

coverageRows = {};
contactRows = {};
manifest = struct();
manifest.generated_at = char(datetime('now', 'TimeZone', 'local', 'Format', 'yyyy-MM-dd HH:mm:ss Z'));
manifest.repo_dir = repoDir;
manifest.subject_root = subjectRoot;
manifest.workbook = workbook;
manifest.sheet = sheetName;
manifest.atlas_dir = atlasDir;
manifest.thresholds_v_per_mm = thresholdsVPerMm;
manifest.thresholds_v_per_m = thresholdsVPerM;
manifest.main_threshold_v_per_mm = mainThreshold;
manifest.horn_export_threshold_v_per_mm = exportThreshold;
manifest.gray_matter_conductivity_s_per_m = 0.33;
manifest.white_matter_conductivity_s_per_m = 0.14;
manifest.selected_subject_count = height(subjects);
manifest.write_cohort_outputs = logical(opts.WriteCohortOutputs);
manifest.cohort_only = logical(opts.CohortOnly);
manifest.subjects = {};

if logical(opts.CohortOnly)
    [coverageTable, contactTable, collectedSubjects] = collect_subject_outputs(subjects, subjectRoot);
    manifest.subjects = collectedSubjects;
    write_cohort_outputs(cohortOutputDir, coverageTable, contactTable, manifest, mainThreshold);
    if height(subjects) == 16
        validate_cohort_outputs(coverageTable, contactTable, cohortOutputDir, thresholdsVPerMm);
    else
        validate_cohort_files_only(cohortOutputDir);
    end
    result = make_result(coverageTable, contactTable, manifest, cohortOutputDir);
    return;
end

for s = 1:height(subjects)
    subjectId = char(string(subjects.ID(s)));
    nameEn = char(string(subjects.NameEn(s)));
    nameZh = char(string(subjects.NameZh(s)));
    patientName = ['sub-', nameEn];
    subjectDir = fullfile(subjectRoot, patientName);
    subjectManifest = struct();
    subjectManifest.id = subjectId;
    subjectManifest.name_en = nameEn;
    subjectManifest.name_zh = nameZh;
    subjectManifest.subject_dir = subjectDir;

    try
        fprintf('\n[%d/%d] STN/SNr VTA coverage: %s (%s)\n', ...
            s, height(subjects), subjectId, patientName);
        must_be_folder(subjectDir, ['subject directory for ', subjectId]);

        subjectOutput = fullfile(subjectDir, 'connectomics', 'stnsnr_vta_coverage');
        if logical(opts.SkipCompletedSubjects) && subject_outputs_complete(subjectOutput, patientName)
            fprintf('Skipping completed subject: %s (%s)\n', subjectId, patientName);
            subjectManifest.status = 'skipped_complete';
            subjectManifest.output_dir = subjectOutput;
            manifest.subjects{end+1} = subjectManifest;
            continue;
        end
        lockCleanup = []; %#ok<NASGU>
        if logical(opts.UseSubjectLocks)
            make_dir(subjectOutput);
            [lockCleanup, lockAcquired] = acquire_subject_lock(subjectOutput, subjectId, patientName, opts);
            if ~lockAcquired
                fprintf('Skipping locked subject: %s (%s)\n', subjectId, patientName);
                subjectManifest.status = 'skipped_locked';
                subjectManifest.output_dir = subjectOutput;
                manifest.subjects{end+1} = subjectManifest;
                continue;
            end
            if isempty(lockCleanup)
                error('mh_fiber_run_stnsnr_vta_coverage:MissingLockCleanup', ...
                    'Subject lock was acquired without a cleanup handle for %s.', patientName);
            end
        end
        dirs = prepare_subject_dirs(subjectOutput);
        subjectRows = rows(string(rows.ID) == string(subjectId), :);
        [numContacts, probeOptions] = resolve_subject_num_contacts(subjectDir);
        subjectManifest.num_contacts_per_side = numContacts;
        subjectManifest.electrode_model = safe_get_field(probeOptions, 'elmodel', '');

        mappedRows = map_contacts(subjectRows, numContacts, subjectDir);
        contactRows = append_table_rows(contactRows, mappedRows, subjectId, patientName);
        writetable(mappedRows, fullfile(dirs.reports, [patientName, '_contact_mapping_qc.csv']));

        subjectCoverageRows = {};
        conditionManifests = {};
        phases = ["immediate", "3m"];
        protocols = ["STN", "STN+SNr"];
        for p = 1:numel(phases)
            for q = 1:numel(protocols)
                conditionRows = mappedRows(string(mappedRows.Phase) == phases(p) & ...
                    string(mappedRows.Protocol) == protocols(q), :);
                if isempty(conditionRows)
                    error('mh_fiber_run_stnsnr_vta_coverage:MissingConditionRows', ...
                        'No rows for %s %s %s.', subjectId, phases(p), protocols(q));
                end

                conditionKey = make_condition_key(phases(p), protocols(q));
                conditionDirs = prepare_condition_dirs(dirs, conditionKey);
                programs = build_condition_programs(conditionRows, subjectId, phases(p), protocols(q));
                programs = ensure_program_efields(programs, subjectDir, exportThreshold, opts);
                [conditionRowsOut, conditionManifest] = analyze_condition_coverage( ...
                    programs, conditionRows, subjectId, patientName, phases(p), protocols(q), ...
                    conditionKey, conditionDirs, atlasDir, thresholdsVPerMm, thresholdsVPerM, ...
                    mainThreshold, opts.OutputVoxelSizeMm, logical(opts.ForceOutputs));

                subjectCoverageRows = [subjectCoverageRows; conditionRowsOut]; %#ok<AGROW>
                conditionManifests{end+1} = conditionManifest; %#ok<AGROW>
            end
        end

        subjectCoverageTable = rows_to_coverage_table(subjectCoverageRows);
        subjectCoverageCsv = fullfile(dirs.reports, [patientName, '_vta_coverage_long.csv']);
        writetable(subjectCoverageTable, subjectCoverageCsv);
        write_subject_summary(fullfile(dirs.reports, [patientName, '_vta_coverage_summary.md']), ...
            subjectId, patientName, subjectCoverageTable, mainThreshold);

        subjectManifest.output_dir = subjectOutput;
        subjectManifest.coverage_csv = subjectCoverageCsv;
        subjectManifest.contact_mapping_qc = fullfile(dirs.reports, [patientName, '_contact_mapping_qc.csv']);
        subjectManifest.conditions = conditionManifests;
        subjectManifest.status = 'ok';
        write_json(fullfile(dirs.manifest, [patientName, '_vta_coverage_manifest.json']), subjectManifest);

        coverageRows = [coverageRows; subjectCoverageRows];
        clear lockCleanup;
    catch ME
        clear lockCleanup;
        subjectManifest.status = 'error';
        subjectManifest.error_identifier = ME.identifier;
        subjectManifest.error_message = ME.message;
        manifest.subjects{end+1} = subjectManifest;
        if logical(opts.StopOnSubjectError)
            rethrow(ME);
        else
            warning('mh_fiber_run_stnsnr_vta_coverage:SubjectFailed', ...
                '%s failed: %s', subjectId, ME.message);
            continue;
        end
    end

    manifest.subjects{end+1} = subjectManifest;
end

if logical(opts.WriteCohortOutputs)
    [coverageTable, contactTable, collectedSubjects] = collect_subject_outputs(subjects, subjectRoot);
    manifest.collected_subject_outputs = collectedSubjects;
    write_cohort_outputs(cohortOutputDir, coverageTable, contactTable, manifest, mainThreshold);
    if height(subjects) == 16
        validate_cohort_outputs(coverageTable, contactTable, cohortOutputDir, thresholdsVPerMm);
    else
        validate_cohort_files_only(cohortOutputDir);
    end
else
    coverageTable = rows_to_coverage_table(coverageRows);
    contactTable = rows_to_contact_table(contactRows);
end

result = make_result(coverageTable, contactTable, manifest, cohortOutputDir);
end

function rows = read_stimulation_rows(workbook, sheetName)
rows = readtable(workbook, 'Sheet', sheetName, 'VariableNamingRule', 'preserve');
required = {'ID', 'NameEn', 'NameZh', 'Phase', 'Protocol', 'Contact', 'Target', ...
    'Side', 'Voltage', 'PulseWidth', 'Frequency', 'ParameterSource', ...
    'StimulationPattern', 'AlternatingGroup', 'Notes'};
for i = 1:numel(required)
    if ~ismember(required{i}, rows.Properties.VariableNames)
        error('mh_fiber_run_stnsnr_vta_coverage:MissingWorkbookColumn', ...
            'Missing workbook column: %s', required{i});
    end
end
rows.ID = string(rows.ID);
rows.NameEn = string(rows.NameEn);
rows.NameZh = string(rows.NameZh);
rows.Phase = string(rows.Phase);
rows.Protocol = string(rows.Protocol);
rows.Target = string(rows.Target);
rows.Side = upper(string(rows.Side));
rows.ParameterSource = string(rows.ParameterSource);
rows.StimulationPattern = lower(string(rows.StimulationPattern));
rows.AlternatingGroup = string(rows.AlternatingGroup);
rows.Notes = string(rows.Notes);
rows.Contact = double(rows.Contact);
rows.Voltage = double(rows.Voltage);
rows.PulseWidth = double(rows.PulseWidth);
rows.Frequency = double(rows.Frequency);
end

function validate_workbook_rows(rows)
if height(rows) ~= 194
    error('mh_fiber_run_stnsnr_vta_coverage:UnexpectedRowCount', ...
        'Expected 194 contact rows, found %d.', height(rows));
end
if numel(unique(rows.ID)) ~= 16
    error('mh_fiber_run_stnsnr_vta_coverage:UnexpectedSubjectCount', ...
        'Expected 16 subjects in workbook, found %d.', numel(unique(rows.ID)));
end
if any(ismissing(rows.Voltage)) || any(ismissing(rows.PulseWidth)) || any(ismissing(rows.Frequency))
    error('mh_fiber_run_stnsnr_vta_coverage:MissingProgrammingValues', ...
        'Voltage, pulse width, or frequency contains missing values.');
end
validPhases = ["immediate", "3m"];
validProtocols = ["STN", "STN+SNr"];
validSides = ["L", "R"];
validPatterns = ["continuous", "alternating"];
assert_members(rows.Phase, validPhases, 'Phase');
assert_members(rows.Protocol, validProtocols, 'Protocol');
assert_members(rows.Side, validSides, 'Side');
assert_members(rows.StimulationPattern, validPatterns, 'StimulationPattern');
end

function assert_members(values, allowed, fieldName)
bad = ~ismember(string(values), allowed);
if any(bad)
    error('mh_fiber_run_stnsnr_vta_coverage:InvalidWorkbookValue', ...
        'Invalid %s value: %s', fieldName, strjoin(unique(string(values(bad))), ', '));
end
end

function tf = is_string_list(value)
tf = isempty(value) || ischar(value) || isstring(value) || ...
    (iscell(value) && all(cellfun(@ischar, value)));
end

function values = normalize_string_list(value)
if isempty(value)
    values = strings(0, 1);
    return;
end
if iscell(value) && all(cellfun(@ischar, value))
    value = string(value);
end
if ischar(value)
    value = string(value);
end
value = string(value(:));
parts = strings(0, 1);
for i = 1:numel(value)
    splitValue = string(regexp(char(value(i)), '[,;]+', 'split'));
    parts = [parts; splitValue(:)]; %#ok<AGROW>
end
values = strtrim(parts);
values = values(values ~= "");
values = unique(values, 'stable');
end

function subjects = filter_subjects(subjects, subjectIds, subjectNames)
subjectIds = normalize_string_list(subjectIds);
subjectNames = normalize_string_list(subjectNames);
if isempty(subjectIds) && isempty(subjectNames)
    return;
end

keep = false(height(subjects), 1);
if ~isempty(subjectIds)
    keep = keep | ismember(string(subjects.ID), subjectIds);
end
if ~isempty(subjectNames)
    nameCandidates = [string(subjects.NameEn), string(subjects.NameZh), "sub-" + string(subjects.NameEn)];
    for i = 1:numel(subjectNames)
        keep = keep | any(strcmpi(nameCandidates, subjectNames(i)), 2);
    end
end
subjects = subjects(keep, :);
end

function [numContacts, options] = resolve_subject_num_contacts(subjectDir)
options = struct();
options = ea_getptopts(subjectDir, options);
options.root = [fileparts(subjectDir), filesep];
[~, options.patientname] = fileparts(subjectDir);
options.leadprod = 'dbs';
S = ea_initializeS('stnsnr_contact_probe', options);
numContacts = S.numContacts;
end

function mapped = map_contacts(rows, numContacts, subjectDir)
mapped = rows;
leadContact = nan(height(rows), 1);
sideRuleOk = false(height(rows), 1);
for i = 1:height(rows)
    rawContact = double(rows.Contact(i));
    if rawContact ~= fix(rawContact) || rawContact < 0
        error('mh_fiber_run_stnsnr_vta_coverage:InvalidRawContact', ...
            'Invalid raw contact %.6g in %s.', rawContact, subjectDir);
    end
    switch char(rows.Side(i))
        case 'L'
            sideRuleOk(i) = rawContact >= 0 && rawContact <= numContacts - 1;
            leadContact(i) = rawContact + 1;
        case 'R'
            sideRuleOk(i) = rawContact >= numContacts && rawContact <= 2 * numContacts - 1;
            leadContact(i) = rawContact - numContacts + 1;
        otherwise
            error('mh_fiber_run_stnsnr_vta_coverage:InvalidSide', ...
                'Invalid side: %s', rows.Side(i));
    end
    if ~sideRuleOk(i)
        error('mh_fiber_run_stnsnr_vta_coverage:ContactSideMismatch', ...
            ['Raw contact %d with side %s does not match left-first numbering ', ...
            'for S.numContacts=%d in %s.'], rawContact, rows.Side(i), numContacts, subjectDir);
    end
    if leadContact(i) < 1 || leadContact(i) > numContacts
        error('mh_fiber_run_stnsnr_vta_coverage:MappedContactOutOfRange', ...
            'Mapped contact %.6g is outside 1:%d.', leadContact(i), numContacts);
    end
end
mapped.SubjectDir = repmat(string(subjectDir), height(mapped), 1);
mapped.NumContactsPerSide = repmat(numContacts, height(mapped), 1);
mapped.RawContact = mapped.Contact;
mapped.LeadContact = leadContact;
mapped.ContactSideRuleOk = sideRuleOk;
end

function programs = build_condition_programs(rows, subjectId, phase, protocol)
programs = struct([]);
programIdx = 0;

continuousRows = rows(rows.StimulationPattern == "continuous", :);
if ~isempty(continuousRows)
    programIdx = programIdx + 1;
    programs(programIdx).rows = continuousRows;
    programs(programIdx).pattern = 'continuous';
    programs(programIdx).alternating_group = '';
    programs(programIdx).label = sanitize_label(sprintf('stnsnr_vta_%s_%s_%s_continuous', ...
        subjectId, phase, protocol));
end

alternatingRows = rows(rows.StimulationPattern == "alternating", :);
for i = 1:height(alternatingRows)
    oneRow = alternatingRows(i, :);
    programIdx = programIdx + 1;
    programs(programIdx).rows = oneRow;
    programs(programIdx).pattern = 'alternating_subprogram';
    programs(programIdx).alternating_group = char(string(oneRow.AlternatingGroup(1)));
    programs(programIdx).label = sanitize_label(sprintf('stnsnr_vta_%s_%s_%s_alt_%s_%s_c%d_row%d', ...
        subjectId, phase, protocol, oneRow.Side(1), oneRow.Target(1), oneRow.RawContact(1), i));
end
end

function programs = ensure_program_efields(programs, subjectDir, exportThresholdVPerMm, opts)
for i = 1:numel(programs)
    rows = programs(i).rows;
    cfg = mh_fiber_default_config(subjectDir, programs(i).label);
    cfg.forceRecomputeVTA = logical(opts.ForceVta);
    cfg.vta.modelKey = 'simbio';
    cfg.vta.model = mh_fiber_model_name('simbio');
    cfg.vta.gmAtlas = 'DISTAL Minimal (Ewert 2017)';
    stimSpec = rows_to_stim_spec(rows, programs(i).label);
    cfg = mh_fiber_set_stimulation(cfg, stimSpec);
    [S, options, stimFolders] = mh_fiber_build_stimulation(cfg);
    options.prefs.machine.vatsettings.horn_cgm = 0.33;
    options.prefs.machine.vatsettings.horn_cwm = 0.14;
    options.prefs.machine.vatsettings.horn_ethresh = exportThresholdVPerMm;
    options.prefs.machine.vatsettings.horn_useatlas = 1;
    options.prefs.machine.vatsettings.horn_atlasset = 'DISTAL Minimal (Ewert 2017)';
    options.prefs.machine.vatsettings.horn_removeElectrode = 1;

    vta = mh_fiber_vta_paths(cfg, stimFolders);
    activeSides = unique(string(rows.Side), 'stable');
    efield = struct();
    for s = 1:numel(activeSides)
        sideCode = char(activeSides(s));
        sideIdx = side_to_index(sideCode);
        efieldPath = vta.mni.(sideCode).efieldNii;
        binaryPath = vta.mni.(sideCode).binaryNii;
        if logical(opts.ForceVta) || ~isfile(efieldPath)
            fprintf('Generating e-field: %s side %s\n', cfg.stimLabel, sideCode);
            run_horn_with_retry(S, sideIdx, options, cfg.stimLabel, efieldPath);
        else
            fprintf('Reusing e-field: %s side %s\n', cfg.stimLabel, sideCode);
        end
        must_be_file(efieldPath, sprintf('MNI e-field for %s side %s', cfg.stimLabel, sideCode));
        efield.(sideCode) = efieldPath;
        if isfile(binaryPath)
            programs(i).binary_mni.(sideCode) = binaryPath;
        end
    end
    programs(i).stim_label = cfg.stimLabel;
    programs(i).efield_mni = efield;
    programs(i).stim_folder_mni = stimFolders.mni;
    programs(i).stim_folder_native = stimFolders.native;
end
end

function run_horn_with_retry(S, sideIdx, options, stimLabel, efieldPath)
maxAttempts = 4;
for attempt = 1:maxAttempts
    try
        rng(stable_retry_seed(stimLabel, sideIdx, attempt), 'twister');
        ea_genvat_horn([], S, sideIdx, options, stimLabel);
        return;
    catch ME
        if isfile(efieldPath)
            warning('mh_fiber_run_stnsnr_vta_coverage:HornPostWriteFailure', ...
                ['Lead-DBS Horn raised an error after writing the expected e-field ', ...
                'for %s side %d: %s'], stimLabel, sideIdx, ME.message);
            return;
        end
        if ~is_horn_index_error(ME) || attempt == maxAttempts
            rethrow(ME);
        end
        warning('mh_fiber_run_stnsnr_vta_coverage:HornIndexRetry', ...
            'Retrying Lead-DBS Horn e-field generation for %s side %d after index error (%d/%d).', ...
            stimLabel, sideIdx, attempt, maxAttempts);
    end
end
end

function seed = stable_retry_seed(stimLabel, sideIdx, attempt)
labelValues = double(char(string(stimLabel)));
seed = 42 + 1009 * double(attempt) + 101 * double(sideIdx) + sum(labelValues);
seed = mod(seed, 2^32 - 1);
if seed == 0
    seed = 42;
end
end

function tf = is_horn_index_error(ME)
stackNames = string({ME.stack.name});
tf = contains(ME.message, 'Array indices must be positive integers') && ...
    any(stackNames == "ea_write_vta_nii");
end

function stimSpec = rows_to_stim_spec(rows, label)
stimSpec = struct();
stimSpec.label = char(string(label));
stimSpec.model = 'simbio';
stimSpec.space = 'native_and_mni';
stimSpec.sources = repmat(empty_source(), height(rows), 1);
for i = 1:height(rows)
    source = empty_source();
    source.side = char(rows.Side(i));
    source.contact = double(rows.LeadContact(i));
    source.amp = double(rows.Voltage(i));
    source.unit = 'V';
    source.pulseWidth = double(rows.PulseWidth(i));
    source.frequency = double(rows.Frequency(i));
    source.cathode = true;
    source.anode = 'case';
    stimSpec.sources(i) = source;
end
end

function source = empty_source()
source = struct('side', '', 'contact', NaN, 'amp', NaN, 'unit', 'V', ...
    'pulseWidth', NaN, 'frequency', NaN, 'cathode', true, 'anode', 'case');
end

function [coverageRows, conditionManifest] = analyze_condition_coverage(programs, conditionRows, ...
    subjectId, patientName, phase, protocol, conditionKey, conditionDirs, atlasDir, ...
    thresholdsVPerMm, thresholdsVPerM, mainThreshold, outputVoxelSize, forceOutputs)

coverageRows = {};
conditionManifest = struct();
conditionManifest.phase = char(phase);
conditionManifest.protocol = char(protocol);
conditionManifest.condition_key = conditionKey;
conditionManifest.programs = rmfield_safe(programs, {'rows'});
conditionManifest.sides = {};

sides = ["L", "R"];
for s = 1:numel(sides)
    sideCode = char(sides(s));
    efieldPaths = {};
    programLabels = {};
    for p = 1:numel(programs)
        if isfield(programs(p).efield_mni, sideCode)
            efieldPaths{end+1} = programs(p).efield_mni.(sideCode); %#ok<AGROW>
            programLabels{end+1} = programs(p).stim_label; %#ok<AGROW>
        end
    end
    if isempty(efieldPaths)
        continue;
    end

    sideManifest = struct();
    sideManifest.side = sideCode;
    sideManifest.efield_paths = efieldPaths;
    sideManifest.program_labels = programLabels;
    sideManifest.thresholds = struct([]);

    for t = 1:numel(thresholdsVPerM)
        thresholdVPerMm = thresholdsVPerMm(t);
        thresholdVPerM = thresholdsVPerM(t);
        thresholdLabel = threshold_label(thresholdVPerMm);
        ref = build_condition_reference_grid(efieldPaths, outputVoxelSize);
        hitCount = zeros(ref.dim, 'uint16');
        for e = 1:numel(efieldPaths)
            hitCount = hitCount + uint16(sample_threshold_to_grid(efieldPaths{e}, ref, thresholdVPerM));
        end
        vtaMask = hitCount > 0;
        overlapMask = hitCount > 1;

        stnMask = sample_mask_to_grid(atlas_path(atlasDir, sideCode, 'STN'), ref);
        snrMask = sample_mask_to_grid(atlas_path(atlasDir, sideCode, 'SNr'), ref);
        if ~any(stnMask(:)) || ~any(snrMask(:))
            error('mh_fiber_run_stnsnr_vta_coverage:EmptyReslicedAtlasMask', ...
                'Empty STN/SNr mask after reslicing for %s %s %s side %s.', ...
                subjectId, phase, protocol, sideCode);
        end

        categories = classify_vta(vtaMask, stnMask, snrMask);
        categorySum = nnz(categories.STN_only) + nnz(categories.SNr_only) + ...
            nnz(categories.STN_SNr) + nnz(categories.Outside);
        totalVoxels = nnz(vtaMask);
        if categorySum ~= totalVoxels
            error('mh_fiber_run_stnsnr_vta_coverage:CategorySumMismatch', ...
                'Category voxel sum does not equal total VTA voxel count.');
        end

        paths = write_condition_masks(ref, vtaMask, categories, overlapMask, conditionDirs, ...
            patientName, phase, protocol, sideCode, thresholdLabel, forceOutputs);
        categoryRows = category_summary_rows(categories, vtaMask, stnMask, snrMask, ref.voxel_volume_mm3);
        pattern = condition_pattern(conditionRows);
        rawContacts = strjoin(string(conditionRows.RawContact(conditionRows.Side == string(sideCode)))', ';');
        leadContacts = strjoin(string(conditionRows.LeadContact(conditionRows.Side == string(sideCode)))', ';');
        targets = strjoin(unique(string(conditionRows.Target(conditionRows.Side == string(sideCode))), 'stable')', ';');

        for r = 1:size(categoryRows, 1)
            coverageRows(end+1, :) = { ...
                subjectId, patientName, char(phase), char(protocol), conditionKey, sideCode, ...
                thresholdVPerMm, thresholdVPerM, categoryRows{r, 1}, ...
                categoryRows{r, 2}, categoryRows{r, 3}, categoryRows{r, 4}, ...
                categoryRows{r, 5}, totalVoxels, totalVoxels * ref.voxel_volume_mm3, ...
                nnz(overlapMask), nnz(overlapMask) * ref.voxel_volume_mm3, ...
                pattern, numel(efieldPaths), rawContacts, leadContacts, targets, ...
                paths.vta, paths.category, paths.overlap};
        end

        if abs(thresholdVPerMm - mainThreshold) < 1e-9
            write_condition_figure(conditionDirs, patientName, phase, protocol, sideCode, ...
                thresholdLabel, categoryRows);
        end

        sideManifest.thresholds(end+1).threshold_v_per_mm = thresholdVPerMm;
        sideManifest.thresholds(end).threshold_v_per_m = thresholdVPerM;
        sideManifest.thresholds(end).vta_voxels = totalVoxels;
        sideManifest.thresholds(end).vta_volume_mm3 = totalVoxels * ref.voxel_volume_mm3;
        sideManifest.thresholds(end).overlap_voxels = nnz(overlapMask);
        sideManifest.thresholds(end).vta_mask = paths.vta;
        sideManifest.thresholds(end).category_mask = paths.category;
    end
    conditionManifest.sides{end+1} = sideManifest;
end
end

function ref = build_condition_reference_grid(efieldPaths, voxelSize)
allCorners = [];
template = ea_load_nii(efieldPaths{1});
for i = 1:numel(efieldPaths)
    nii = ea_load_nii(efieldPaths{i});
    dim = size(nii.img);
    corners = [ ...
        1, 1, 1; dim(1), 1, 1; 1, dim(2), 1; 1, 1, dim(3); ...
        dim(1), dim(2), 1; dim(1), 1, dim(3); 1, dim(2), dim(3); dim(1), dim(2), dim(3)];
    allCorners = [allCorners; ea_vox2mm(corners, nii.mat)]; %#ok<AGROW>
end
minMm = floor(min(allCorners, [], 1) ./ voxelSize) .* voxelSize - voxelSize;
maxMm = ceil(max(allCorners, [], 1) ./ voxelSize) .* voxelSize + voxelSize;
dim = max(1, ceil((maxMm - minMm) ./ voxelSize) + 1);
if prod(dim) > 12000000
    error('mh_fiber_run_stnsnr_vta_coverage:ReferenceGridTooLarge', ...
        'Condition reference grid is too large: %s voxels.', mat2str(dim));
end
mat = [voxelSize, 0, 0, minMm(1); 0, voxelSize, 0, minMm(2); ...
    0, 0, voxelSize, minMm(3); 0, 0, 0, 1];
ref = struct();
ref.dim = dim;
ref.mat = mat;
ref.template = template;
ref.voxel_size_mm = voxelSize;
ref.voxel_volume_mm3 = abs(det(mat(1:3, 1:3)));
end

function mask = sample_threshold_to_grid(sourcePath, ref, threshold)
source = ea_load_nii(sourcePath);
mask = sample_image_to_grid(source, ref, threshold, 'threshold');
end

function mask = sample_mask_to_grid(sourcePath, ref)
source = ea_load_nii(sourcePath);
mask = sample_image_to_grid(source, ref, 0, 'binary');
end

function mask = sample_image_to_grid(source, ref, threshold, mode)
mask = false(ref.dim);
sourceImg = double(source.img);
sourceSize = size(sourceImg);
total = prod(ref.dim);
chunkSize = 250000;
for startIdx = 1:chunkSize:total
    stopIdx = min(total, startIdx + chunkSize - 1);
    idx = (startIdx:stopIdx)';
    [x, y, z] = ind2sub(ref.dim, idx);
    xyzMm = ea_vox2mm([x, y, z], ref.mat);
    srcVox = round(ea_mm2vox(xyzMm, source.mat));
    inside = srcVox(:, 1) >= 1 & srcVox(:, 1) <= sourceSize(1) & ...
        srcVox(:, 2) >= 1 & srcVox(:, 2) <= sourceSize(2) & ...
        srcVox(:, 3) >= 1 & srcVox(:, 3) <= sourceSize(3);
    if any(inside)
        lin = sub2ind(sourceSize, srcVox(inside, 1), srcVox(inside, 2), srcVox(inside, 3));
        vals = sourceImg(lin);
        switch mode
            case 'threshold'
                hit = vals >= threshold;
            case 'binary'
                hit = vals > threshold;
            otherwise
                error('mh_fiber_run_stnsnr_vta_coverage:InvalidSampleMode', ...
                    'Invalid sample mode: %s', mode);
        end
        idxInside = idx(inside);
        mask(idxInside(hit)) = true;
    end
end
end

function categories = classify_vta(vtaMask, stnMask, snrMask)
categories = struct();
categories.STN_only = vtaMask & stnMask & ~snrMask;
categories.SNr_only = vtaMask & snrMask & ~stnMask;
categories.STN_SNr = vtaMask & stnMask & snrMask;
categories.Outside = vtaMask & ~(stnMask | snrMask);
end

function rows = category_summary_rows(categories, vtaMask, stnMask, snrMask, voxelVolume)
names = {'STN_only', 'SNr_only', 'STN_SNr', 'Outside'};
denominators = [nnz(stnMask & ~snrMask), nnz(snrMask & ~stnMask), nnz(stnMask & snrMask), NaN];
totalVoxels = nnz(vtaMask);
rows = cell(numel(names), 5);
for i = 1:numel(names)
    count = nnz(categories.(names{i}));
    volume = count * voxelVolume;
    percentTotal = 100 * count / max(1, totalVoxels);
    if isnan(denominators(i)) || denominators(i) == 0
        percentAnatomical = NaN;
    else
        percentAnatomical = 100 * count / denominators(i);
    end
    rows(i, :) = {names{i}, count, volume, percentTotal, percentAnatomical};
end
end

function paths = write_condition_masks(ref, vtaMask, categories, overlapMask, conditionDirs, ...
    patientName, phase, protocol, sideCode, thresholdLabel, forceOutputs)
base = sanitize_label(sprintf('%s_phase-%s_protocol-%s_hemi-%s_thr-%s', ...
    patientName, phase, protocol, sideCode, thresholdLabel));
paths = struct();
paths.vta = fullfile(conditionDirs.masks, [base, '_desc-vta.nii']);
paths.category = fullfile(conditionDirs.masks, [base, '_desc-vtaCategory.nii']);
paths.overlap = fullfile(conditionDirs.masks, [base, '_desc-vtaProgramOverlap.nii']);
if forceOutputs || ~isfile(paths.vta)
    write_ref_nii(ref, double(vtaMask), paths.vta, 2, 'stnsnr thresholded vta');
end
if forceOutputs || ~isfile(paths.category)
    categoryImg = zeros(ref.dim, 'uint8');
    categoryImg(categories.STN_only) = 1;
    categoryImg(categories.SNr_only) = 2;
    categoryImg(categories.STN_SNr) = 3;
    categoryImg(categories.Outside) = 4;
    write_ref_nii(ref, categoryImg, paths.category, 2, 'stnsnr vta category');
end
if forceOutputs || ~isfile(paths.overlap)
    write_ref_nii(ref, double(overlapMask), paths.overlap, 2, 'stnsnr alternating overlap');
end
end

function write_ref_nii(ref, img, outputPath, datatype, description)
nii = ref.template;
nii.img = img;
nii.dim = ref.dim;
nii.mat = ref.mat;
nii.dt = [datatype, 0];
nii.n = [1, 1];
nii.descrip = description;
nii.fname = outputPath;
ea_write_nii(nii);
end

function write_condition_figure(conditionDirs, patientName, phase, protocol, sideCode, thresholdLabel, categoryRows)
figPath = fullfile(conditionDirs.figures, [sanitize_label(sprintf('%s_phase-%s_protocol-%s_hemi-%s_thr-%s', ...
    patientName, phase, protocol, sideCode, thresholdLabel)), '_desc-vtaCoverage.png']);
fig = figure('Visible', 'off', 'Color', 'w', 'Position', [100, 100, 760, 420]);
cleanup = onCleanup(@() close(fig));
names = string(categoryRows(:, 1));
volumes = cell2mat(categoryRows(:, 3));
bar(categorical(names), volumes);
ylabel('Volume (mm3)');
title(sprintf('%s %s %s %s %s', patientName, phase, protocol, sideCode, thresholdLabel), ...
    'Interpreter', 'none');
grid on;
exportgraphics(fig, figPath, 'Resolution', 220, 'BackgroundColor', 'white');
end

function write_subject_summary(path, subjectId, patientName, coverageTable, mainThreshold)
fid = fopen(path, 'w');
if fid < 0
    error('mh_fiber_run_stnsnr_vta_coverage:CannotWriteSummary', ...
        'Cannot write subject summary: %s', path);
end
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '# STN/SNr VTA Coverage Summary\n\n');
fprintf(fid, '- Subject ID: `%s`\n', subjectId);
fprintf(fid, '- Lead-DBS subject: `%s`\n', patientName);
fprintf(fid, '- Main threshold: `%.2f V/mm`\n\n', mainThreshold);
mainRows = coverageTable(abs(coverageTable.threshold_v_per_mm - mainThreshold) < 1e-9, :);
summary = summarize_total_vta(mainRows);
fprintf(fid, '| Phase | Protocol | Side | Total VTA volume mm3 |\n');
fprintf(fid, '|---|---|---:|---:|\n');
for i = 1:height(summary)
    fprintf(fid, '| %s | %s | %s | %.3f |\n', summary.phase(i), ...
        summary.protocol(i), summary.side(i), summary.total_vta_volume_mm3(i));
end
end

function [coverageTable, contactTable, collectedSubjects] = collect_subject_outputs(subjects, subjectRoot)
coverageTables = cell(height(subjects), 1);
contactTables = cell(height(subjects), 1);
collectedSubjects = cell(height(subjects), 1);
for s = 1:height(subjects)
    subjectId = char(string(subjects.ID(s)));
    patientName = ['sub-', char(string(subjects.NameEn(s)))];
    subjectOutput = fullfile(subjectRoot, patientName, 'connectomics', 'stnsnr_vta_coverage');
    coverageCsv = fullfile(subjectOutput, 'reports', [patientName, '_vta_coverage_long.csv']);
    contactCsv = fullfile(subjectOutput, 'reports', [patientName, '_contact_mapping_qc.csv']);
    manifestJson = fullfile(subjectOutput, 'manifest', [patientName, '_vta_coverage_manifest.json']);
    summaryMd = fullfile(subjectOutput, 'reports', [patientName, '_vta_coverage_summary.md']);
    must_be_file(coverageCsv, sprintf('per-subject coverage CSV for %s', subjectId));
    must_be_file(contactCsv, sprintf('per-subject contact QC CSV for %s', subjectId));
    must_be_file(manifestJson, sprintf('per-subject manifest JSON for %s', subjectId));
    must_be_file(summaryMd, sprintf('per-subject summary Markdown for %s', subjectId));
    coverageTables{s} = normalize_coverage_table(readtable(coverageCsv, 'TextType', 'string'));
    contactTables{s} = normalize_contact_table(readtable(contactCsv, 'TextType', 'string'));
    collectedSubjects{s} = struct('id', subjectId, 'patient_name', patientName, ...
        'coverage_csv', coverageCsv, 'contact_mapping_qc', contactCsv, ...
        'manifest_json', manifestJson, 'summary_md', summaryMd, 'status', 'collected');
end
coverageTable = vertcat(coverageTables{:});
contactTable = vertcat(contactTables{:});
end

function tableOut = normalize_coverage_table(tableOut)
stringVars = {'subject_id', 'patient_name', 'phase', 'protocol', 'condition_key', ...
    'side', 'category', 'stimulation_pattern', 'raw_contacts', 'lead_contacts', ...
    'targets', 'vta_mask_path', 'category_mask_path', 'program_overlap_mask_path'};
tableOut = force_string_vars(tableOut, stringVars);
end

function tableOut = normalize_contact_table(tableOut)
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
    error('mh_fiber_run_stnsnr_vta_coverage:InvalidLogicalColumn', ...
        'Could not parse logical values in contact_side_rule_ok.');
end
end

function write_cohort_outputs(outputDir, coverageTable, contactTable, manifest, mainThreshold)
writetable(coverageTable, fullfile(outputDir, 'cohort_vta_coverage_long.csv'));
wide = unstack(coverageTable, 'volume_mm3', 'category');
writetable(wide, fullfile(outputDir, 'cohort_vta_coverage_wide.csv'));

byCondition = summarize_by_condition(coverageTable);
writetable(byCondition, fullfile(outputDir, 'cohort_vta_coverage_by_condition.csv'));

sensitivity = summarize_threshold_sensitivity(coverageTable);
writetable(sensitivity, fullfile(outputDir, 'cohort_vta_threshold_sensitivity.csv'));

writetable(contactTable, fullfile(outputDir, 'cohort_contact_mapping_qc.csv'));
write_json(fullfile(outputDir, 'cohort_vta_generation_manifest.json'), manifest);
write_cohort_figures(outputDir, coverageTable, mainThreshold);
end

function summary = summarize_total_vta(tableIn)
[G, phase, protocol, side] = findgroups(tableIn.phase, tableIn.protocol, tableIn.side);
total = splitapply(@(x) max(x), tableIn.total_vta_volume_mm3, G);
summary = table(phase, protocol, side, total, 'VariableNames', ...
    {'phase', 'protocol', 'side', 'total_vta_volume_mm3'});
end

function byCondition = summarize_by_condition(coverageTable)
[G, phase, protocol, threshold, category] = findgroups(coverageTable.phase, ...
    coverageTable.protocol, coverageTable.threshold_v_per_mm, coverageTable.category);
meanVolume = splitapply(@(x) mean(x, 'omitnan'), coverageTable.volume_mm3, G);
medianVolume = splitapply(@(x) median(x, 'omitnan'), coverageTable.volume_mm3, G);
sdVolume = splitapply(@(x) std(x, 'omitnan'), coverageTable.volume_mm3, G);
meanPercent = splitapply(@(x) mean(x, 'omitnan'), coverageTable.percent_total_vta, G);
byCondition = table(phase, protocol, threshold, category, meanVolume, medianVolume, ...
    sdVolume, meanPercent, 'VariableNames', {'phase', 'protocol', ...
    'threshold_v_per_mm', 'category', 'mean_volume_mm3', 'median_volume_mm3', ...
    'sd_volume_mm3', 'mean_percent_total_vta'});
end

function sensitivity = summarize_threshold_sensitivity(coverageTable)
totalRows = unique(coverageTable(:, {'subject_id', 'patient_name', 'phase', 'protocol', ...
    'condition_key', 'side', 'threshold_v_per_mm', 'total_vta_volume_mm3'}), 'rows');
sensitivity = sortrows(totalRows, {'subject_id', 'phase', 'protocol', 'side', 'threshold_v_per_mm'});
end

function write_cohort_figures(outputDir, coverageTable, mainThreshold)
figureDir = fullfile(outputDir, 'figures');
make_dir(figureDir);
mainRows = coverageTable(abs(coverageTable.threshold_v_per_mm - mainThreshold) < 1e-9, :);
byCondition = summarize_by_condition(mainRows);

fig = figure('Visible', 'off', 'Color', 'w', 'Position', [100, 100, 900, 450]);
cleanup = onCleanup(@() close(fig));
groups = categorical(strcat(byCondition.phase, " / ", byCondition.protocol, " / ", byCondition.category));
bar(groups, byCondition.mean_volume_mm3);
ylabel('Mean volume (mm3)');
title('Mean VTA compartment volume at 0.20 V/mm');
grid on;
exportgraphics(fig, fullfile(figureDir, 'coverage_stacked_bar_thr0p20.png'), ...
    'Resolution', 220, 'BackgroundColor', 'white');
clear cleanup;

fig = figure('Visible', 'off', 'Color', 'w', 'Position', [100, 100, 900, 450]);
cleanup = onCleanup(@() close(fig));
boxchart(categorical(strcat(mainRows.phase, " / ", mainRows.protocol, " / ", mainRows.category)), ...
    mainRows.volume_mm3);
ylabel('Volume (mm3)');
title('VTA compartment volume distribution at 0.20 V/mm');
grid on;
exportgraphics(fig, fullfile(figureDir, 'coverage_boxplot_by_condition_thr0p20.png'), ...
    'Resolution', 220, 'BackgroundColor', 'white');
clear cleanup;

totalRows = unique(coverageTable(:, {'phase', 'protocol', 'side', 'threshold_v_per_mm', ...
    'subject_id', 'total_vta_volume_mm3'}), 'rows');
[G, threshold] = findgroups(totalRows.threshold_v_per_mm);
meanTotal = splitapply(@(x) mean(x, 'omitnan'), totalRows.total_vta_volume_mm3, G);
fig = figure('Visible', 'off', 'Color', 'w', 'Position', [100, 100, 620, 420]);
plot(threshold, meanTotal, '-o', 'LineWidth', 1.5);
xlabel('Threshold (V/mm)');
ylabel('Mean total VTA volume (mm3)');
title('Threshold sensitivity');
grid on;
exportgraphics(fig, fullfile(figureDir, 'coverage_threshold_sensitivity.png'), ...
    'Resolution', 220, 'BackgroundColor', 'white');
end

function validate_cohort_outputs(coverageTable, contactTable, outputDir, thresholdsVPerMm)
if numel(unique(contactTable.subject_id)) ~= 16
    error('mh_fiber_run_stnsnr_vta_coverage:ContactQcSubjectCount', ...
        'Contact QC does not contain 16 subjects.');
end
if height(contactTable) ~= 194
    error('mh_fiber_run_stnsnr_vta_coverage:ContactQcRowCount', ...
        'Contact QC does not contain 194 rows.');
end
if any(~contactTable.contact_side_rule_ok)
    error('mh_fiber_run_stnsnr_vta_coverage:ContactRuleQcFailed', ...
        'At least one contact failed the side rule.');
end

totalRows = unique(coverageTable(:, {'subject_id', 'phase', 'protocol', 'side', ...
    'threshold_v_per_mm', 'total_vta_volume_mm3'}), 'rows');
[G, subject, phase, protocol, side] = findgroups(totalRows.subject_id, totalRows.phase, ...
    totalRows.protocol, totalRows.side);
for g = 1:max(G)
    one = sortrows(totalRows(G == g, :), 'threshold_v_per_mm');
    if height(one) ~= numel(thresholdsVPerMm)
        error('mh_fiber_run_stnsnr_vta_coverage:MissingThresholdRows', ...
            'Missing threshold rows for %s %s %s %s.', subject(g), phase(g), protocol(g), side(g));
    end
    vols = one.total_vta_volume_mm3;
    if any(diff(vols) > 1e-6)
        error('mh_fiber_run_stnsnr_vta_coverage:ThresholdMonotonicityFailed', ...
            'VTA volume is not monotonic for %s %s %s %s.', subject(g), phase(g), protocol(g), side(g));
    end
end

required = {'cohort_vta_coverage_long.csv', 'cohort_vta_coverage_wide.csv', ...
    'cohort_vta_coverage_by_condition.csv', 'cohort_vta_threshold_sensitivity.csv', ...
    'cohort_contact_mapping_qc.csv', 'cohort_vta_generation_manifest.json'};
for i = 1:numel(required)
    must_be_file(fullfile(outputDir, required{i}), required{i});
end
end

function validate_cohort_files_only(outputDir)
required = {'cohort_vta_coverage_long.csv', 'cohort_vta_coverage_wide.csv', ...
    'cohort_vta_coverage_by_condition.csv', 'cohort_vta_threshold_sensitivity.csv', ...
    'cohort_contact_mapping_qc.csv', 'cohort_vta_generation_manifest.json'};
for i = 1:numel(required)
    must_be_file(fullfile(outputDir, required{i}), required{i});
end
end

function result = make_result(coverageTable, contactTable, manifest, cohortOutputDir)
result = struct();
result.coverageTable = coverageTable;
result.contactTable = contactTable;
result.manifest = manifest;
result.cohortOutputDir = cohortOutputDir;
result.coverageLongCsv = fullfile(cohortOutputDir, 'cohort_vta_coverage_long.csv');
result.contactQcCsv = fullfile(cohortOutputDir, 'cohort_contact_mapping_qc.csv');
end

function tableOut = rows_to_coverage_table(rows)
if isempty(rows)
    tableOut = table();
    return;
end
tableOut = cell2table(rows, 'VariableNames', { ...
    'subject_id', 'patient_name', 'phase', 'protocol', 'condition_key', 'side', ...
    'threshold_v_per_mm', 'threshold_v_per_m', 'category', 'voxel_count', ...
    'volume_mm3', 'percent_total_vta', 'percent_anatomical_compartment', ...
    'total_vta_voxels', 'total_vta_volume_mm3', 'program_overlap_voxels', ...
    'program_overlap_volume_mm3', 'stimulation_pattern', 'program_count', ...
    'raw_contacts', 'lead_contacts', 'targets', 'vta_mask_path', ...
    'category_mask_path', 'program_overlap_mask_path'});
tableOut.subject_id = string(tableOut.subject_id);
tableOut.patient_name = string(tableOut.patient_name);
tableOut.phase = string(tableOut.phase);
tableOut.protocol = string(tableOut.protocol);
tableOut.condition_key = string(tableOut.condition_key);
tableOut.side = string(tableOut.side);
tableOut.category = string(tableOut.category);
tableOut.stimulation_pattern = string(tableOut.stimulation_pattern);
tableOut.raw_contacts = string(tableOut.raw_contacts);
tableOut.lead_contacts = string(tableOut.lead_contacts);
tableOut.targets = string(tableOut.targets);
tableOut.vta_mask_path = string(tableOut.vta_mask_path);
tableOut.category_mask_path = string(tableOut.category_mask_path);
tableOut.program_overlap_mask_path = string(tableOut.program_overlap_mask_path);
end

function rowsOut = append_table_rows(rowsOut, tableIn, subjectId, patientName)
for i = 1:height(tableIn)
    rowsOut(end+1, :) = { ...
        subjectId, patientName, char(tableIn.ID(i)), char(tableIn.NameEn(i)), ...
        char(tableIn.NameZh(i)), char(tableIn.Phase(i)), char(tableIn.Protocol(i)), ...
        char(tableIn.Target(i)), char(tableIn.Side(i)), tableIn.RawContact(i), ...
        tableIn.LeadContact(i), tableIn.NumContactsPerSide(i), tableIn.Voltage(i), ...
        tableIn.PulseWidth(i), tableIn.Frequency(i), char(tableIn.ParameterSource(i)), ...
        char(tableIn.StimulationPattern(i)), char(tableIn.AlternatingGroup(i)), ...
        char(tableIn.SubjectDir(i)), logical(tableIn.ContactSideRuleOk(i))}; %#ok<AGROW>
end
end

function tableOut = rows_to_contact_table(rows)
if isempty(rows)
    tableOut = table();
    return;
end
tableOut = cell2table(rows, 'VariableNames', { ...
    'subject_id', 'patient_name', 'workbook_id', 'name_en', 'name_zh', ...
    'phase', 'protocol', 'target', 'side', 'raw_contact', 'lead_contact', ...
    'num_contacts_per_side', 'voltage', 'pulse_width', 'frequency', ...
    'parameter_source', 'stimulation_pattern', 'alternating_group', ...
    'subject_dir', 'contact_side_rule_ok'});
stringVars = {'subject_id', 'patient_name', 'workbook_id', 'name_en', 'name_zh', ...
    'phase', 'protocol', 'target', 'side', 'parameter_source', ...
    'stimulation_pattern', 'alternating_group', 'subject_dir'};
for i = 1:numel(stringVars)
    tableOut.(stringVars{i}) = string(tableOut.(stringVars{i}));
end
end

function path = atlas_path(atlasDir, sideCode, roi)
switch sideCode
    case 'L'
        hemi = 'lh';
    case 'R'
        hemi = 'rh';
    otherwise
        error('mh_fiber_run_stnsnr_vta_coverage:InvalidSide', 'Invalid side: %s', sideCode);
end
path = fullfile(atlasDir, hemi, [roi, '.nii.gz']);
must_be_file(path, sprintf('%s %s atlas mask', sideCode, roi));
end

function verify_atlas_files(atlasDir)
must_be_file(atlas_path(atlasDir, 'L', 'STN'), 'left STN atlas');
must_be_file(atlas_path(atlasDir, 'R', 'STN'), 'right STN atlas');
must_be_file(atlas_path(atlasDir, 'L', 'SNr'), 'left SNr atlas');
must_be_file(atlas_path(atlasDir, 'R', 'SNr'), 'right SNr atlas');
end

function sideIdx = side_to_index(sideCode)
switch upper(char(sideCode))
    case 'R'
        sideIdx = 1;
    case 'L'
        sideIdx = 2;
    otherwise
        error('mh_fiber_run_stnsnr_vta_coverage:InvalidSide', 'Invalid side: %s', sideCode);
end
end

function key = make_condition_key(phase, protocol)
key = sanitize_label(sprintf('%s_%s', phase, protocol));
end

function pattern = condition_pattern(rows)
patterns = unique(string(rows.StimulationPattern), 'stable');
if isscalar(patterns) && patterns == "continuous"
    pattern = 'continuous';
elseif isscalar(patterns) && patterns == "alternating"
    pattern = 'alternating_union';
else
    pattern = 'mixed_union';
end
end

function label = threshold_label(value)
label = strrep(sprintf('%.2f', value), '.', 'p');
end

function out = sanitize_label(value)
out = char(string(value));
out = regexprep(out, '\+', 'plus');
out = regexprep(out, '[^A-Za-z0-9_+-]+', '_');
out = regexprep(out, '_+', '_');
out = regexprep(out, '^_|_$', '');
end

function tf = subject_outputs_complete(subjectOutput, patientName)
coverageCsv = fullfile(subjectOutput, 'reports', [patientName, '_vta_coverage_long.csv']);
contactCsv = fullfile(subjectOutput, 'reports', [patientName, '_contact_mapping_qc.csv']);
summaryMd = fullfile(subjectOutput, 'reports', [patientName, '_vta_coverage_summary.md']);
manifestJson = fullfile(subjectOutput, 'manifest', [patientName, '_vta_coverage_manifest.json']);
vtaFiles = dir(fullfile(subjectOutput, 'masks', '*', '*_desc-vta.nii'));
if ~isempty(vtaFiles)
    vtaFiles = vtaFiles(~startsWith(string({vtaFiles.name}), '._'));
end
tf = isfile(coverageCsv) && isfile(contactCsv) && isfile(summaryMd) && ...
    isfile(manifestJson) && numel(vtaFiles) >= 24;
end

function [cleanup, acquired] = acquire_subject_lock(subjectOutput, subjectId, patientName, opts)
lockDir = fullfile(subjectOutput, '.stnsnr_vta_coverage.lock');
[status, message] = system(sprintf('mkdir %s', shell_quote(lockDir)));
acquired = status == 0;
cleanup = [];
if ~acquired
    if logical(opts.SkipLockedSubjects)
        return;
    end
    error('mh_fiber_run_stnsnr_vta_coverage:SubjectLocked', ...
        'Subject %s (%s) is locked by another worker: %s (%s)', ...
        subjectId, patientName, lockDir, strtrim(message));
end
fid = fopen(fullfile(lockDir, 'owner.txt'), 'w');
if fid >= 0
    fprintf(fid, 'subject_id=%s\npatient_name=%s\npid=%d\ncreated_at=%s\n', ...
        subjectId, patientName, feature('getpid'), ...
        char(datetime('now', 'TimeZone', 'local', 'Format', 'yyyy-MM-dd HH:mm:ss Z')));
    fclose(fid);
end
cleanup = onCleanup(@() release_subject_lock(lockDir));
end

function release_subject_lock(lockDir)
if isfolder(lockDir)
    try
        rmdir(lockDir, 's');
    catch ME
        warning('mh_fiber_run_stnsnr_vta_coverage:CannotReleaseLock', ...
            'Could not release subject lock %s: %s', lockDir, ME.message);
    end
end
end

function quoted = shell_quote(value)
value = char(string(value));
quoted = ['''', strrep(value, '''', '''"''"'''), ''''];
end

function dirs = prepare_subject_dirs(rootDir)
dirs = struct();
dirs.root = rootDir;
dirs.reports = fullfile(rootDir, 'reports');
dirs.masks = fullfile(rootDir, 'masks');
dirs.figures = fullfile(rootDir, 'figures');
dirs.manifest = fullfile(rootDir, 'manifest');
make_dir(dirs.root);
make_dir(dirs.reports);
make_dir(dirs.masks);
make_dir(dirs.figures);
make_dir(dirs.manifest);
end

function dirs = prepare_condition_dirs(parentDirs, conditionKey)
dirs = struct();
dirs.masks = fullfile(parentDirs.masks, conditionKey);
dirs.figures = fullfile(parentDirs.figures, conditionKey);
make_dir(dirs.masks);
make_dir(dirs.figures);
end

function make_dir(path)
if ~isfolder(path)
    mkdir(path);
end
end

function write_json(path, data)
fid = fopen(path, 'w');
if fid < 0
    error('mh_fiber_run_stnsnr_vta_coverage:CannotWriteJson', 'Cannot write JSON: %s', path);
end
cleanup = onCleanup(@() fclose(fid));
try
    text = jsonencode(data, PrettyPrint=true);
catch
    text = jsonencode(data);
end
fprintf(fid, '%s\n', text);
end

function out = rmfield_safe(in, fields)
out = in;
present = fields(isfield(out, fields));
if ~isempty(present)
    out = rmfield(out, present);
end
end

function value = safe_get_field(s, fieldName, fallback)
if isfield(s, fieldName)
    value = s.(fieldName);
else
    value = fallback;
end
end

function must_be_file(path, description)
if ~isfile(path)
    error('mh_fiber_run_stnsnr_vta_coverage:MissingFile', ...
        'Missing %s: %s', description, path);
end
end

function must_be_folder(path, description)
if ~isfolder(path)
    error('mh_fiber_run_stnsnr_vta_coverage:MissingFolder', ...
        'Missing %s: %s', description, path);
end
end

function repoDir = resolve_repo_dir(startPath)
repoDir = fileparts(startPath);
while ~isempty(repoDir) && ~isfolder(fullfile(repoDir, '.git'))
    parent = fileparts(repoDir);
    if strcmp(parent, repoDir)
        break;
    end
    repoDir = parent;
end
if isempty(repoDir) || ~isfolder(fullfile(repoDir, '.git'))
    repoDir = '/Users/mojackhu/Github/leaddbs';
end
end
