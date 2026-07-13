function result = run_single_source_backend_equivalence(varargin)
% Run a copied-subject numerical equivalence gate for two SimBio backends.

parser = inputParser;
parser.FunctionName = 'run_single_source_backend_equivalence';
parser.addParameter('StudyBase', ...
    '/Volumes/VAL/STNSNr/summary/cohort/subj/study_base.json', ...
    @(x) ischar(x) || isstring(x));
parser.addParameter('WorkRoot', '/Volumes/VAL/STNSNr/validation', ...
    @(x) ischar(x) || isstring(x));
parser.addParameter('SubjectId', 'SNr003', @(x) ischar(x) || isstring(x));
parser.addParameter('PhaseId', 'T1', @(x) ischar(x) || isstring(x));
parser.addParameter('ProgramId', 1, @(x) isnumeric(x) && isscalar(x));
parser.addParameter('ReusePreparedRoot', false, @(x) islogical(x) || isnumeric(x));
parser.parse(varargin{:});
opts = parser.Results;

assert_safe_work_root(opts.WorkRoot);

repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(repoDir), '-end');
templateSpace = 'MNI152NLin2009bAsym';
spaceOverrideCleanup = apply_space_override(templateSpace); %#ok<NASGU>

studyBasePath = must_be_file(opts.StudyBase, 'study-base JSON');
studyDocument = jsondecode(fileread(studyBasePath));
validate_study_document(studyDocument);
[subject, cases] = select_cases(studyDocument, opts);
[officialPilot, scope] = classify_scope(opts, cases);
if officialPilot && logical(opts.ReusePreparedRoot)
    error('run_single_source_backend_equivalence:OfficialReuseForbidden', ...
        'Official SNr003 acceptance requires a newly copied validation root.');
end
[gitCommit, gitDirty] = git_provenance(repoDir);
if officialPilot && gitDirty
    error('run_single_source_backend_equivalence:DirtyOfficialPilot', ...
        'Official SNr003 acceptance requires a clean tracked Lead-DBS tree.');
end

runRoot = prepare_run_root(opts.WorkRoot, logical(opts.ReusePreparedRoot));
copiedSubject = prepare_subject_copy(subject, runRoot, logical(opts.ReusePreparedRoot));
archive_copied_headmodel(copiedSubject, runRoot, logical(opts.ReusePreparedRoot));

atlasSet = 'Custom_Ewert_Zhang_Middlebrooks';
thresholdsVPerM = [180 200 220];
rngSeed = 20260712;
inventory = case_inventory(cases, subject, opts);
writetable(inventory, fullfile(runRoot, 'case_inventory.csv'));

manifest = initial_manifest(repoDir, studyBasePath, subject, opts, atlasSet, ...
    thresholdsVPerM, rngSeed, copiedSubject, cases, officialPilot, scope, ...
    gitCommit, gitDirty, templateSpace);
write_json(fullfile(runRoot, 'validation_manifest.json'), manifest);

outputIndex = struct();
backends = {'simbio', 'simbio_onesolve'};
hashRows = cell(numel(cases) * (1 + numel(backends) * 2), 13);
hashRowIndex = 0;
resolvedDefaults = struct([]);
for caseIndex = 1:numel(cases)
    oneCase = cases(caseIndex);
    caseField = matlab.lang.makeValidName(oneCase.case_id);
    seed = rngSeed + 1000 * caseIndex;
    [beforeHash, afterHash, effectiveDefaults, diagnostics, label] = ...
        prepare_case_headmodel(copiedSubject, oneCase, atlasSet, seed);
    hashRowIndex = hashRowIndex + 1;
    hashRows(hashRowIndex, :) = hash_row(oneCase.case_id, 'preparation', ...
        'simbio', 0, label, beforeHash, afterHash, seed, diagnostics);
    resolvedDefaults = merge_effective_defaults( ...
        resolvedDefaults, effectiveDefaults);
    for backendIndex = 1:numel(backends)
        backend = backends{backendIndex};
        backendField = matlab.lang.makeValidName(backend);
        for repeat = 1:2
            [paths, beforeHash, afterHash, effectiveDefaults, ...
                diagnostics, label] = run_one_backend(copiedSubject, ...
                oneCase, backend, repeat, atlasSet, runRoot, seed);
            outputIndex.(caseField).(backendField)(repeat) = paths;
            resolvedDefaults = merge_effective_defaults( ...
                resolvedDefaults, effectiveDefaults);
            hashRowIndex = hashRowIndex + 1;
            hashRows(hashRowIndex, :) = hash_row(oneCase.case_id, ...
                'measured', backend, repeat, label, beforeHash, afterHash, ...
                seed, diagnostics);
        end
    end
end

headmodelHashes = cell2table(hashRows, 'VariableNames', { ...
    'case_id', 'run_kind', 'backend', 'repeat', 'stimulation_label', ...
    'hash_before', 'hash_after', 'hash_created', 'hash_unchanged', ...
    'rng_seed_base', 'actual_rng_seed', 'rng_attempt_count', ...
    'rng_attempt_seeds'});
for variable = ["case_id" "run_kind" "backend" "stimulation_label" ...
        "hash_before" "hash_after" "rng_attempt_seeds"]
    headmodelHashes.(variable) = string(headmodelHashes.(variable));
end
rngPass = all(headmodelHashes.actual_rng_seed == ...
    headmodelHashes.rng_seed_base) && ...
    all(headmodelHashes.rng_attempt_count == 1);
writetable(headmodelHashes, fullfile(runRoot, 'headmodel_hashes.csv'));
patientGmMask = must_be_file(resolved_patient_mask(copiedSubject, atlasSet), ...
    'patient-space atlas GM mask');

[efieldMetrics, binaryMetrics, repeatabilityMetrics, comparisonPass] = ...
    compare_all_outputs(cases, outputIndex);
writetable(efieldMetrics, fullfile(runRoot, 'efield_metrics.csv'));
writetable(binaryMetrics, fullfile(runRoot, 'binary_vta_metrics.csv'));
writetable(repeatabilityMetrics, fullfile(runRoot, 'repeatability_metrics.csv'));

preparationRows = headmodelHashes.run_kind == "preparation";
measuredRows = headmodelHashes.run_kind == "measured";
headmodelPass = all(headmodelHashes.hash_created(preparationRows)) && ...
    all(headmodelHashes.hash_unchanged(measuredRows));
overallPass = comparisonPass && headmodelPass && rngPass;
summary = struct( ...
    'pass', overallPass, ...
    'subject_id', char(string(opts.SubjectId)), ...
    'case_count', numel(cases), ...
    'headmodel_hashes_unchanged', headmodelPass, ...
    'rng_streams_matched', rngPass, ...
    'comparison_gates_passed', comparisonPass, ...
    'official_pilot', officialPilot, ...
    'scope', scope, ...
    'created_at', timestamp_iso());
write_json(fullfile(runRoot, 'acceptance_summary.json'), summary);
write_summary_markdown(fullfile(runRoot, 'acceptance_summary.md'), summary, ...
    efieldMetrics, binaryMetrics, repeatabilityMetrics);

manifest.completed_at = timestamp_iso();
manifest.pass = overallPass;
manifest.patient_gm_mask = patientGmMask;
manifest.patient_gm_mask_sha256 = mh_fiber_file_sha256(patientGmMask);
manifest.effective_defaults = resolvedDefaults;
manifest.headmodel_hashes_file = 'headmodel_hashes.csv';
manifest.headmodel_hashes = table2struct(headmodelHashes);
write_json(fullfile(runRoot, 'validation_manifest.json'), manifest);

result = struct('run_root', runRoot, 'pass', overallPass, ...
    'summary', summary, 'case_inventory', inventory);
if ~overallPass
    error('run_single_source_backend_equivalence:AcceptanceFailed', ...
        'Single-source backend equivalence acceptance failed: %s', runRoot);
end
end

function validate_study_document(document)
if ~isstruct(document) || ~isfield(document, 'schema_version') || ...
        ~strcmp(char(string(document.schema_version)), 'dual_frequency_study_v1') || ...
        ~isfield(document, 'study') || ~isfield(document.study, 'subjects')
    error('run_single_source_backend_equivalence:InvalidStudyBase', ...
        'Study-base JSON does not satisfy the required study contract.');
end
end

function [subject, cases] = select_cases(document, opts)
subjects = document.study.subjects;
subjectMask = arrayfun(@(x) strcmp(char(string(x.subject_id)), ...
    char(string(opts.SubjectId))), subjects);
if nnz(subjectMask) ~= 1
    error('run_single_source_backend_equivalence:SubjectSelectionFailed', ...
        'Expected exactly one subject matching %s.', char(string(opts.SubjectId)));
end
subject = subjects(subjectMask);
phases = subject.phases;
phaseMask = arrayfun(@(x) strcmp(char(string(x.phase_id)), ...
    char(string(opts.PhaseId))), phases);
if nnz(phaseMask) ~= 1
    error('run_single_source_backend_equivalence:PhaseSelectionFailed', ...
        'Expected exactly one phase matching %s.', char(string(opts.PhaseId)));
end
programs = phases(phaseMask).programs;
programMask = arrayfun(@(x) double(x.program_id) == double(opts.ProgramId), programs);
if nnz(programMask) ~= 1
    error('run_single_source_backend_equivalence:ProgramSelectionFailed', ...
        'Expected exactly one program matching %g.', double(opts.ProgramId));
end
program = programs(programMask);

electrodes = subject.electrodes;
order = cellstr(string(subject.contact_numbering.electrode_order));
offsets = electrode_offsets(electrodes, order);
caseCells = {};
for epIndex = 1:numel(program.electrode_programs)
    electrodeProgram = program.electrode_programs(epIndex);
    electrode = find_electrode(electrodes, electrodeProgram.electrode_id);
    groups = electrodeProgram.frequency_groups;
    if numel(groups) ~= 1 || ~strcmp(char(string(groups.delivery_mode)), 'continuous') || ...
            numel(groups.sources) ~= 1
        error('run_single_source_backend_equivalence:NotSingleContinuousSource', ...
            'Each selected hemisphere must contain one continuous single-source group.');
    end
    source = groups.sources;
    validate_source(source);
    globalContact = cathodic_contact(source.contacts);
    localContact = globalContact - offsets.(matlab.lang.makeValidName( ...
        char(string(electrode.electrode_id)))) + 1;
    if localContact < 1 || localContact > double(electrode.contact_count)
        error('run_single_source_backend_equivalence:ContactOutOfRange', ...
            'Mapped contact is outside the selected electrode.');
    end
    oneCase = struct();
    oneCase.side = char(string(electrode.hemisphere));
    oneCase.electrode_id = char(string(electrode.electrode_id));
    oneCase.electrode_model = char(string(electrode.electrode_model));
    oneCase.contact_count = double(electrode.contact_count);
    oneCase.frequency_group_id = char(string(groups.frequency_group_id));
    oneCase.delivery_mode = char(string(groups.delivery_mode));
    oneCase.source = source;
    oneCase.local_contact = localContact;
    oneCase.case_id = sprintf('%s_%s', char(string(opts.SubjectId)), oneCase.side);
    caseCells{end+1} = oneCase; %#ok<AGROW>
end
cases = [caseCells{:}];
if numel(cases) ~= 2 || ~isequal(sort(string({cases.side})), ["L" "R"])
    error('run_single_source_backend_equivalence:BilateralCasesRequired', ...
        'Acceptance requires exactly one left and one right single-source case.');
end
end

function offsets = electrode_offsets(electrodes, order)
offsets = struct();
offset = 0;
for i = 1:numel(order)
    electrode = find_electrode(electrodes, order{i});
    offsets.(matlab.lang.makeValidName(order{i})) = offset;
    offset = offset + double(electrode.contact_count);
end
end

function electrode = find_electrode(electrodes, electrodeId)
mask = arrayfun(@(x) strcmp(char(string(x.electrode_id)), ...
    char(string(electrodeId))), electrodes);
if nnz(mask) ~= 1
    error('run_single_source_backend_equivalence:ElectrodeSelectionFailed', ...
        'Expected exactly one electrode matching %s.', char(string(electrodeId)));
end
electrode = electrodes(mask);
end

function validate_source(source)
if ~strcmp(char(string(source.control_mode)), 'voltage')
    error('run_single_source_backend_equivalence:UnsupportedControlMode', ...
        'Acceptance requires a voltage-controlled source.');
end
requiredPositiveFields = {'amplitude', 'pulse_width_us', 'frequency_hz'};
for i = 1:numel(requiredPositiveFields)
    field = requiredPositiveFields{i};
    if ~isfield(source, field) || ~isnumeric(source.(field)) || ...
            ~isscalar(source.(field)) || ~isfinite(source.(field)) || ...
            source.(field) <= 0
        error('run_single_source_backend_equivalence:InvalidSourceParameter', ...
            'Source field %s must be a finite positive scalar.', field);
    end
end
contacts = source.contacts;
cathodes = arrayfun(@(x) isnumeric(x.contact) && ...
    strcmp(char(string(x.polarity)), 'cathode') && double(x.fraction) == 1, contacts);
caseAnodes = arrayfun(@(x) ischar(x.contact) && strcmpi(x.contact, 'case') && ...
    strcmp(char(string(x.polarity)), 'anode') && double(x.fraction) == 1, contacts);
if nnz(cathodes) ~= 1 || nnz(caseAnodes) ~= 1 || numel(contacts) ~= 2
    error('run_single_source_backend_equivalence:UnsupportedContactDesign', ...
        'Acceptance requires one full-fraction cathode and one full-fraction case anode.');
end
end

function contact = cathodic_contact(contacts)
mask = arrayfun(@(x) isnumeric(x.contact) && ...
    strcmp(char(string(x.polarity)), 'cathode'), contacts);
contact = double(contacts(mask).contact);
end

function runRoot = prepare_run_root(workRootValue, reuse)
workRoot = char(string(workRootValue));
prefix = 'vta_single_source_backend_equivalence_';
[~, leaf] = fileparts(workRoot);
isExactRoot = startsWith(leaf, prefix);
if reuse
    if ~isExactRoot || ~isfolder(workRoot)
        error('run_single_source_backend_equivalence:InvalidPreparedRoot', ...
            'ReusePreparedRoot requires an existing timestamped validation root.');
    end
    if isfolder(fullfile(workRoot, 'outputs')) || ...
            isfile(fullfile(workRoot, 'acceptance_summary.json')) || ...
            isfile(fullfile(workRoot, 'acceptance_summary.md'))
        error('run_single_source_backend_equivalence:PreparedRootNotOutputFree', ...
            ['ReusePreparedRoot requires an incomplete prepared root with ', ...
            'no backend outputs or acceptance summary.']);
    end
    runRoot = workRoot;
    return;
end
if isExactRoot && isfolder(workRoot)
    error('run_single_source_backend_equivalence:ExistingValidationRoot', ...
        'Refusing to overwrite existing validation root: %s', workRoot);
end
if ~isfolder(workRoot)
    mkdir(workRoot);
end
stamp = char(datetime('now', 'Format', 'yyyyMMdd_HHmmss_SSS'));
runRoot = fullfile(workRoot, [prefix, stamp]);
if isfolder(runRoot)
    error('run_single_source_backend_equivalence:ExistingValidationRoot', ...
        'Refusing to overwrite existing validation root: %s', runRoot);
end
mkdir(runRoot);
end

function copiedSubject = prepare_subject_copy(subject, runRoot, reuse)
sourceSubject = must_be_folder(subject.subject_sources.leaddbs_subject_dir, ...
    'Lead-DBS subject directory');
copyRoot = fullfile(runRoot, 'copied_subject');
[sourceDatasetRoot, sourceDerivativeRoot] = bids_roots(sourceSubject);
[~, subjectLeaf] = fileparts(sourceSubject);
copiedDerivativeRoot = fullfile(copyRoot, 'derivatives', 'leaddbs');
copiedSubject = fullfile(copiedDerivativeRoot, subjectLeaf);
if reuse
    must_be_folder(copiedSubject, 'prepared copied subject');
    return;
end
mkdir(copiedDerivativeRoot);
copy_required_file(fullfile(sourceDatasetRoot, 'dataset_description.json'), ...
    fullfile(copyRoot, 'dataset_description.json'), ...
    'source BIDS dataset description');
copy_optional_file(fullfile(sourceDatasetRoot, '.bidsignore'), ...
    fullfile(copyRoot, '.bidsignore'));
copy_optional_file(fullfile(sourceDerivativeRoot, 'dataset_description.json'), ...
    fullfile(copiedDerivativeRoot, 'dataset_description.json'));
[ok, message] = copyfile(sourceSubject, copiedSubject);
if ~ok
    error('run_single_source_backend_equivalence:SubjectCopyFailed', ...
        'Could not copy subject directory: %s', message);
end
end

function [datasetRoot, derivativeRoot] = bids_roots(subjectDir)
marker = [filesep, 'derivatives', filesep, 'leaddbs', filesep];
markerIndex = strfind(subjectDir, marker);
if numel(markerIndex) ~= 1
    error('run_single_source_backend_equivalence:InvalidBidsSubjectPath', ...
        'Lead-DBS subject path must be under derivatives/leaddbs: %s', ...
        subjectDir);
end
datasetRoot = subjectDir(1:markerIndex - 1);
derivativeRoot = fullfile(datasetRoot, 'derivatives', 'leaddbs');
end

function copy_required_file(source, target, label)
must_be_file(source, label);
[ok, message] = copyfile(source, target);
if ~ok
    error('run_single_source_backend_equivalence:MetadataCopyFailed', ...
        'Could not copy %s: %s', label, message);
end
end

function copy_optional_file(source, target)
if ~isfile(source)
    return;
end
[ok, message] = copyfile(source, target);
if ~ok
    error('run_single_source_backend_equivalence:MetadataCopyFailed', ...
        'Could not copy optional BIDS metadata %s: %s', source, message);
end
end

function archive_copied_headmodel(copiedSubject, runRoot, reuse)
if reuse
    return;
end
source = fullfile(copiedSubject, 'headmodel');
if ~isfolder(source)
    return;
end
destination = fullfile(runRoot, 'archived_input_headmodel');
if isfolder(destination) || isfile(destination)
    error('run_single_source_backend_equivalence:ExistingHeadmodelArchive', ...
        'Head-model archive already exists: %s', destination);
end
[ok, message] = movefile(source, destination);
if ~ok
    error('run_single_source_backend_equivalence:HeadmodelArchiveFailed', ...
        'Could not archive copied head model: %s', message);
end
end

function [beforeHash, afterHash, effectiveDefaults, diagnostics, label] = ...
        prepare_case_headmodel(copiedSubject, oneCase, atlasSet, seed)
label = sprintf('backend_equivalence_headmodel_prepare_%s', oneCase.side);
[~, beforeHash, afterHash, effectiveDefaults, diagnostics] = ...
    execute_backend(copiedSubject, oneCase, 'simbio', label, atlasSet, seed);
if ~isempty(beforeHash)
    error('run_single_source_backend_equivalence:HeadmodelPreparationNotFresh', ...
        'Head-model preparation expected no existing model for %s.', ...
        oneCase.case_id);
end
end

function [paths, beforeHash, afterHash, effectiveDefaults, diagnostics, label] = ...
        run_one_backend(copiedSubject, oneCase, backend, repeat, atlasSet, ...
        runRoot, seed)
label = sprintf('backend_equivalence_%s_%s_run%d', backend, oneCase.side, repeat);
[taskResults, beforeHash, afterHash, effectiveDefaults, diagnostics] = ...
    execute_backend(copiedSubject, oneCase, backend, label, atlasSet, seed);

targetDir = fullfile(runRoot, 'outputs', backend, oneCase.side, ...
    sprintf('run-%d', repeat));
mkdir(targetDir);
paths = struct();
paths.native = copy_output(taskResults.efield_native, ...
    fullfile(targetDir, 'native_efield.nii'));
paths.mni = copy_output(taskResults.efield_mni, ...
    fullfile(targetDir, 'mni_efield.nii'));
end

function [taskResults, beforeHash, afterHash, effectiveDefaults, diagnostics] = ...
        execute_backend(copiedSubject, oneCase, backend, label, atlasSet, seed)
cfg = mh_fiber_default_config(copiedSubject, label);
cfg.forceRecomputeVTA = true;
cfg.vta.modelKey = backend;
cfg.vta.model = mh_fiber_model_name(backend);
cfg.vta.gmAtlas = atlasSet;
cfg.vta.executionMode = 'sequential';
cfg.vta.parallelWorkers = 1;

stimSpec = struct();
stimSpec.label = label;
stimSpec.model = backend;
stimSpec.space = 'MNI152NLin2009bAsym';
stimSpec.sources = struct( ...
    'side', oneCase.side, ...
    'contact', oneCase.local_contact, ...
    'amp', double(oneCase.source.amplitude), ...
    'unit', 'V', ...
    'pulseWidth', double(oneCase.source.pulse_width_us), ...
    'frequency', double(oneCase.source.frequency_hz), ...
    'cathode', true, ...
    'anode', 'case');

headmodel = expected_headmodel(copiedSubject, oneCase.side);
beforeHash = hash_if_file(headmodel);
[taskResults, ~, ~, ~, options] = mh_vta_run_stim_spec_tasks( ...
    cfg, stimSpec, {oneCase.side}, ...
    'ModelKey', backend, ...
    'Force', true, ...
    'OutputSpaces', {'native', 'mni'}, ...
    'ExportThresholdVPerMm', 0.18, ...
    'GmAtlas', atlasSet, ...
    'RngSeedBase', seed);
if numel(taskResults) ~= 1 || ~strcmp(taskResults.status, 'complete')
    error('run_single_source_backend_equivalence:BackendRunFailed', ...
        'Backend %s did not return one complete task.', backend);
end
afterHash = mh_fiber_file_sha256(must_be_file(headmodel, 'shared head model'));
if ~isfield(taskResults, 'rng_diagnostics')
    error('run_single_source_backend_equivalence:MissingRngDiagnostics', ...
        'Backend %s did not return RNG diagnostics.', backend);
end
diagnostics = taskResults.rng_diagnostics;
effectiveDefaults = extract_effective_defaults(options);
end

function path = copy_output(source, target)
source = must_be_file(source, 'backend E-field');
if endsWith(source, '.nii.gz')
    target = [erase(target, '.nii'), '.nii.gz'];
end
[ok, message] = copyfile(source, target, 'f');
if ~ok
    error('run_single_source_backend_equivalence:OutputCopyFailed', ...
        'Could not copy backend output: %s', message);
end
path = target;
end

function path = expected_headmodel(subjectDir, side)
[~, patientName] = fileparts(subjectDir);
sideIndex = 1;
if strcmp(side, 'L')
    sideIndex = 2;
end
path = fullfile(subjectDir, 'headmodel', 'native', ...
    sprintf('%s_desc-headmodel%d.mat', patientName, sideIndex));
end

function row = hash_row(caseId, runKind, backend, repeat, label, ...
        beforeHash, afterHash, seedBase, diagnostics)
hashCreated = isempty(beforeHash) && ~isempty(afterHash);
hashUnchanged = ~isempty(beforeHash) && strcmp(beforeHash, afterHash);
row = {caseId, runKind, backend, repeat, label, beforeHash, afterHash, ...
    hashCreated, hashUnchanged, seedBase, double(diagnostics.seed_used), ...
    double(diagnostics.attempt_count), jsonencode(diagnostics.attempt_seeds)};
end

function resolved = merge_effective_defaults(resolved, candidate)
if isempty(resolved)
    resolved = candidate;
elseif ~isequaln(resolved, candidate)
    error('run_single_source_backend_equivalence:EffectiveDefaultsChanged', ...
        'Effective Lead-DBS defaults changed between backend runs.');
end
end

function [official, scope] = classify_scope(opts, cases)
official = strcmp(char(string(opts.SubjectId)), 'SNr003') && ...
    strcmp(char(string(opts.PhaseId)), 'T1') && ...
    double(opts.ProgramId) == 1;
hardwareMatches = all(strcmp(string({cases.electrode_model}), ...
    "Medtronic 3387")) && all([cases.contact_count] == 4) && ...
    all(arrayfun(@(x) x.local_contact >= 1 && x.local_contact <= 4, cases));
if official && ~hardwareMatches
    error('run_single_source_backend_equivalence:OfficialHardwareMismatch', ...
        'Official SNr003 pilot requires bilateral Medtronic 3387 leads.');
end
if official
    scope = 'SNr003 Medtronic 3387 bilateral single-source pilot only';
else
    scope = sprintf(['Custom single-source validation: %s/%s/program %g; ', ...
        'not the official SNr003 pilot'], char(string(opts.SubjectId)), ...
        char(string(opts.PhaseId)), double(opts.ProgramId));
end
end

function [efieldRows, binaryRows, repeatRows, passed] = compare_all_outputs( ...
        cases, outputs)
passed = true;
spaces = {'native', 'mni'};
comparisonCount = numel(cases) * numel(spaces);
efieldCells = cell(comparisonCount, 1);
binaryCells = cell(comparisonCount, 1);
repeatCells = cell(comparisonCount * 2, 1);
comparisonIndex = 0;
for i = 1:numel(cases)
    oneCase = cases(i);
    field = matlab.lang.makeValidName(oneCase.case_id);
    standard = outputs.(field).simbio;
    oneSolve = outputs.(field).simbio_onesolve;
    for s = 1:numel(spaces)
        space = spaces{s};
        repeatStandard = mh_compare_single_source_backend_outputs( ...
            standard(1).(space), standard(2).(space), ...
            'Side', oneCase.side, 'Space', space, ...
            'Comparison', 'repeatability', 'ThrowOnFailure', false);
        repeatOneSolve = mh_compare_single_source_backend_outputs( ...
            oneSolve(1).(space), oneSolve(2).(space), ...
            'Side', oneCase.side, 'Space', space, ...
            'Comparison', 'repeatability', 'ThrowOnFailure', false);
        equivalence = mh_compare_single_source_backend_outputs( ...
            standard(1).(space), oneSolve(1).(space), ...
            'Side', oneCase.side, 'Space', space, ...
            'Comparison', 'equivalence', 'ThrowOnFailure', false);
        comparisonIndex = comparisonIndex + 1;
        repeatCells{comparisonIndex * 2 - 1} = annotate_efield( ...
            repeatStandard.efield_row, oneCase.case_id, 'simbio');
        repeatCells{comparisonIndex * 2} = annotate_efield( ...
            repeatOneSolve.efield_row, oneCase.case_id, 'simbio_onesolve');
        efieldCells{comparisonIndex} = annotate_efield( ...
            equivalence.efield_row, oneCase.case_id, ...
            'simbio_vs_simbio_onesolve');
        binaryCells{comparisonIndex} = annotate_binary( ...
            equivalence.binary_rows, oneCase.case_id, ...
            'simbio_vs_simbio_onesolve');
        passed = passed && repeatStandard.pass && repeatOneSolve.pass && ...
            equivalence.pass;
    end
end
efieldRows = vertcat(efieldCells{:});
binaryRows = vertcat(binaryCells{:});
repeatRows = vertcat(repeatCells{:});
end

function row = annotate_efield(row, caseId, backendComparison)
row = addvars(row, string(caseId), string(backendComparison), ...
    'Before', 1, 'NewVariableNames', {'case_id', 'backend_comparison'});
end

function rows = annotate_binary(rows, caseId, backendComparison)
rows = addvars(rows, repmat(string(caseId), height(rows), 1), ...
    repmat(string(backendComparison), height(rows), 1), ...
    'Before', 1, 'NewVariableNames', {'case_id', 'backend_comparison'});
end

function inventory = case_inventory(cases, subject, opts)
rows = cell(numel(cases), 15);
for i = 1:numel(cases)
    one = cases(i);
    rows(i, :) = {one.case_id, char(string(subject.subject_id)), ...
        char(string(opts.PhaseId)), double(opts.ProgramId), one.side, ...
        one.electrode_id, one.electrode_model, one.frequency_group_id, ...
        one.delivery_mode, char(string(one.source.source_id)), ...
        char(string(one.source.component_id)), double(one.source.frequency_hz), ...
        double(one.source.amplitude), double(one.source.pulse_width_us), ...
        double(one.local_contact)};
end
inventory = cell2table(rows, 'VariableNames', { ...
    'case_id', 'subject_id', 'phase_id', 'program_id', 'side', ...
    'electrode_id', 'electrode_model', 'frequency_group_id', 'delivery_mode', ...
    'source_id', 'component_id', 'frequency_hz', 'amplitude', ...
    'pulse_width_us', 'local_contact'});
end

function manifest = initial_manifest(repoDir, studyBase, subject, opts, atlasSet, ...
        thresholds, rngSeed, copiedSubject, cases, officialPilot, scope, ...
        gitCommit, gitDirty, templateSpace)
atlasDir = fullfile(repoDir, 'templates', 'space', 'MNI152NLin2009bAsym', ...
    'atlases', atlasSet);
templateMask = must_be_file(fullfile(atlasDir, 'gm_mask.nii.gz'), ...
    'template atlas GM mask');
manifest = struct();
manifest.schema_version = 'vta_backend_equivalence_v1';
manifest.created_at = timestamp_iso();
manifest.study_base = studyBase;
manifest.study_base_sha256 = mh_fiber_file_sha256(studyBase);
manifest.subject_id = char(string(opts.SubjectId));
manifest.subject_label = char(string(subject.subject_label));
manifest.phase_id = char(string(opts.PhaseId));
manifest.program_id = double(opts.ProgramId);
manifest.source_subject_dir = char(string( ...
    subject.subject_sources.leaddbs_subject_dir));
manifest.copied_subject_dir = copiedSubject;
manifest.reconstruction = char(string( ...
    subject.subject_sources.electrode_reconstruction.path));
manifest.reconstruction_sha256 = hash_if_file(manifest.reconstruction);
manifest.native_to_mni_transform = resolve_native_to_mni_transform( ...
    manifest.source_subject_dir);
manifest.native_to_mni_transform_sha256 = ...
    hash_if_file(manifest.native_to_mni_transform);
manifest.atlas_set = atlasSet;
manifest.template_space = templateSpace;
manifest.atlas_dir = atlasDir;
manifest.template_gm_mask = templateMask;
manifest.template_gm_mask_sha256 = mh_fiber_file_sha256(templateMask);
manifest.thresholds_v_per_m = thresholds;
manifest.rng_seed_base = rngSeed;
manifest.backends = {'simbio', 'simbio_onesolve'};
manifest.matlab_version = version;
manifest.leaddbs_commit = gitCommit;
manifest.leaddbs_dirty = gitDirty;
manifest.official_pilot = officialPilot;
manifest.case_ids = {cases.case_id};
manifest.selected_sources = table2struct(case_inventory(cases, subject, opts));
manifest.scope = scope;
manifest.code_file_hashes = acceptance_code_hashes(repoDir);
end

function cleanup = apply_space_override(templateSpace)
previous = getenv('LEADDBS_SPACE_OVERRIDE');
setenv('LEADDBS_SPACE_OVERRIDE', templateSpace);
cleanup = onCleanup(@() setenv('LEADDBS_SPACE_OVERRIDE', previous));
end

function hashes = acceptance_code_hashes(repoDir)
relativePaths = { ...
    'my_helper/vta/test/run_single_source_backend_equivalence.m', ...
    'my_helper/vta/test/mh_compare_single_source_backend_outputs.m', ...
    ['my_helper/fiber/core/stimulation/model/backends/', ...
        'mh_vta_backend_simbio_twosource.m'], ...
    ['my_helper/fiber/core/stimulation/model/backends/', ...
        'mh_vta_backend_simbio_onesolve.m'], ...
    'my_helper/fiber/core/stimulation/model/mh_vta_run_horn_with_retry.m', ...
    'helpers/space/ea_getspace.m'};
hashes = repmat(struct('path', '', 'sha256', ''), numel(relativePaths), 1);
for i = 1:numel(relativePaths)
    hashes(i).path = relativePaths{i};
    hashes(i).sha256 = mh_fiber_file_sha256( ...
        must_be_file(fullfile(repoDir, relativePaths{i}), 'acceptance code file'));
end
end

function defaults = extract_effective_defaults(options)
settings = mh_vta_settings();
preferences = ea_prefs_default('');
defaults = struct();
defaults.gray_matter_conductivity_s_per_m = settings.horn_cgm;
defaults.white_matter_conductivity_s_per_m = settings.horn_cwm;
defaults.use_atlas = logical(settings.horn_useatlas);
defaults.remove_electrode = logical(settings.horn_removeElectrode);
defaults.gray_matter_source = char(string(preferences.vat.gm));
defaults.hullsmooth = double(preferences.hullsmooth);
if isstruct(options) && isfield(options, 'prefs')
    if isfield(options.prefs, 'vat') && isfield(options.prefs.vat, 'gm')
        defaults.gray_matter_source = char(string(options.prefs.vat.gm));
    end
    if isfield(options.prefs, 'hullsmooth')
        defaults.hullsmooth = double(options.prefs.hullsmooth);
    end
end
defaults.mask_surface_threshold_rule = 'max(smoothed_mask)/2';
defaults.tetrahedron_inside_fraction = 0.70;
end

function path = resolve_native_to_mni_transform(subjectDir)
transformDir = fullfile(char(string(subjectDir)), 'normalization', ...
    'transformations');
matches = dir(fullfile(transformDir, ...
    '*_from-anchorNative_to-MNI152NLin2009bAsym_desc-ants.nii.gz'));
matches = matches(~startsWith(string({matches.name}), '._'));
if numel(matches) ~= 1
    error('run_single_source_backend_equivalence:TransformSelectionFailed', ...
        'Expected one native-to-MNI transform under %s.', transformDir);
end
path = fullfile(matches(1).folder, matches(1).name);
end

function [commit, dirty] = git_provenance(repoDir)
[status, output] = system(sprintf('git -C %s rev-parse HEAD', ...
    mh_fiber_shell_quote(repoDir)));
if status == 0
    commit = strtrim(output);
else
    commit = '';
end
[status, output] = system(sprintf('git -C %s status --porcelain', ...
    mh_fiber_shell_quote(repoDir)));
dirty = status ~= 0 || ~isempty(strtrim(output));
end

function write_summary_markdown(path, summary, efield, binary, repeatability)
fid = fopen(path, 'w');
if fid < 0
    error('run_single_source_backend_equivalence:SummaryWriteFailed', ...
        'Could not write summary: %s', path);
end
cleanupObj = onCleanup(@() fclose(fid));
fprintf(fid, '# Single-Source Backend Equivalence\n\n');
fprintf(fid, '- Pass: `%s`\n', string(summary.pass));
fprintf(fid, '- Subject: `%s`\n', summary.subject_id);
fprintf(fid, '- Scope: %s\n', summary.scope);
fprintf(fid, '- E-field comparisons: `%d`\n', height(efield));
fprintf(fid, '- Binary VTA comparisons: `%d`\n', height(binary));
fprintf(fid, '- Repeatability comparisons: `%d`\n', height(repeatability));
end

function write_json(path, value)
fid = fopen(path, 'w');
if fid < 0
    error('run_single_source_backend_equivalence:JsonWriteFailed', ...
        'Could not write JSON: %s', path);
end
cleanupObj = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', jsonencode(value, PrettyPrint=true));
end

function path = resolved_patient_mask(subjectDir, atlasSet)
base = fullfile(subjectDir, 'atlases', atlasSet, 'gm_mask.nii');
if isfile([base, '.gz'])
    path = [base, '.gz'];
elseif isfile(base)
    path = base;
else
    path = '';
end
end

function hash = hash_if_file(path)
path = char(string(path));
if isempty(path) || ~isfile(path)
    hash = '';
else
    hash = mh_fiber_file_sha256(path);
end
end

function path = must_be_file(value, label)
path = char(string(value));
if ~isfile(path)
    error('run_single_source_backend_equivalence:MissingFile', ...
        '%s does not exist: %s', label, path);
end
end

function path = must_be_folder(value, label)
path = char(string(value));
if ~isfolder(path)
    error('run_single_source_backend_equivalence:MissingDirectory', ...
        '%s does not exist: %s', label, path);
end
end

function value = timestamp_iso()
value = char(datetime('now', 'TimeZone', 'UTC', ...
    'Format', 'yyyy-MM-dd''T''HH:mm:ss.SSS''Z'''));
end

function assert_safe_work_root(value)
root = canonical_path(value);
production = canonical_path('/Volumes/VAL/STNSNr/derivatives/leaddbs');
rootPrefix = [root, filesep];
productionPrefix = [production, filesep];
if strcmp(root, production) || startsWith(rootPrefix, productionPrefix) || ...
        startsWith(productionPrefix, rootPrefix)
    error('mh_vta_acceptance:UnsafeWorkRoot', ...
        'WorkRoot must be outside the production Lead-DBS derivatives tree.');
end
end

function path = canonical_path(value)
path = char(java.io.File(char(string(value))).getCanonicalPath());
while numel(path) > 1 && path(end) == filesep
    path(end) = [];
end
end
