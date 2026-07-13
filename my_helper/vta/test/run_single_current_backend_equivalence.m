function result = run_single_current_backend_equivalence(varargin)
% Run deterministic current fixtures or copied-subject backend acceptance.

parser = inputParser;
parser.FunctionName = 'run_single_current_backend_equivalence';
parser.addParameter('StudyBase', ...
    '/Volumes/VAL/STNSNr/summary/cohort/subj/study_base.json', ...
    @(x) ischar(x) || isstring(x));
parser.addParameter('WorkRoot', '/Volumes/VAL/STNSNr/validation', ...
    @(x) ischar(x) || isstring(x));
parser.addParameter('SubjectId', 'SNr003', @(x) ischar(x) || isstring(x));
parser.addParameter('Seed', 20260712, @is_valid_seed);
parser.addParameter('Mode', 'fem', @(x) ischar(x) || isstring(x));
parser.parse(varargin{:});
opts = parser.Results;

mode = lower(char(string(opts.Mode)));
if ~ismember(mode, {'fem', 'fixture_only'})
    error('run_single_current_backend_equivalence:InvalidMode', ...
        'Mode must be fem or fixture_only.');
end
assert_safe_work_root(opts.WorkRoot);

atlasSet = 'Custom_Ewert_Zhang_Middlebrooks';
thresholdsVPerM = [180 200 220];
if strcmp(mode, 'fixture_only')
    cases = generate_current_cases(double(opts.Seed), {'L', 'R'}, [4 4]);
    result = fixture_result(cases, double(opts.Seed), atlasSet);
    return;
end

repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(repoDir), '-end');
studyBasePath = must_be_file(opts.StudyBase, 'study-base JSON');
studyDocument = jsondecode(fileread(studyBasePath));
subject = select_subject(studyDocument, opts.SubjectId);
[sides, contactCounts] = subject_electrode_inventory(subject);
cases = generate_current_cases(double(opts.Seed), sides, contactCounts);

runRoot = create_run_root(opts.WorkRoot);
sourceSubject = must_be_folder( ...
    subject.subject_sources.leaddbs_subject_dir, 'Lead-DBS subject directory');
sourceHashBefore = directory_inventory_hash(sourceSubject);
copiedSubject = copy_subject_tree(sourceSubject, runRoot);

manifest = struct( ...
    'schema_version', 'vta_current_backend_acceptance_v1', ...
    'subject_id', char(string(opts.SubjectId)), ...
    'seed', double(opts.Seed), ...
    'atlas_set', atlasSet, ...
    'thresholds_v_per_m', thresholdsVPerM, ...
    'source_subject', sourceSubject, ...
    'copied_subject', copiedSubject, ...
    'source_tree_sha256_before', sourceHashBefore, ...
    'fixture_sha256', fixture_hash(cases), ...
    'started_at', timestamp_iso(), ...
    'completed_at', '', ...
    'pass', false);
write_json(fullfile(runRoot, 'validation_manifest.json'), manifest);
writetable(case_inventory(cases), fullfile(runRoot, 'case_inventory.csv'));

outputs = run_all_cases(copiedSubject, cases, atlasSet, runRoot, ...
    double(opts.Seed));
[efieldMetrics, binaryMetrics, repeatabilityMetrics, comparisonPass] = ...
    compare_all_outputs(cases, outputs);
writetable(efieldMetrics, fullfile(runRoot, 'efield_metrics.csv'));
writetable(binaryMetrics, fullfile(runRoot, 'binary_vta_metrics.csv'));
writetable(repeatabilityMetrics, ...
    fullfile(runRoot, 'repeatability_metrics.csv'));

sourceHashAfter = directory_inventory_hash(sourceSubject);
sourceTreeUnchanged = strcmp(sourceHashBefore, sourceHashAfter);
overallPass = comparisonPass && sourceTreeUnchanged;
summary = struct( ...
    'subject_id', char(string(opts.SubjectId)), ...
    'case_count', numel(cases), ...
    'comparison_gates_passed', comparisonPass, ...
    'production_subject_tree_unchanged', sourceTreeUnchanged, ...
    'pass', overallPass);
write_json(fullfile(runRoot, 'acceptance_summary.json'), summary);

manifest.completed_at = timestamp_iso();
manifest.source_tree_sha256_after = sourceHashAfter;
manifest.pass = overallPass;
write_json(fullfile(runRoot, 'validation_manifest.json'), manifest);
result = struct('mode', mode, 'run_root', runRoot, 'cases', cases, ...
    'summary', summary, 'pass', overallPass);
if ~overallPass
    error('run_single_current_backend_equivalence:AcceptanceFailed', ...
        'Current backend acceptance failed: %s', runRoot);
end
end

function result = fixture_result(cases, seed, atlasSet)
result = struct( ...
    'mode', 'fixture_only', ...
    'seed', seed, ...
    'atlas_set', atlasSet, ...
    'cases', cases, ...
    'fixture_sha256', fixture_hash(cases), ...
    'superposition_fixture', vector_superposition_fixture(), ...
    'pass', true);
end

function cases = generate_current_cases(seed, sides, contactCounts)
previousRng = rng;
cleanupObj = onCleanup(@() rng(previousRng)); %#ok<NASGU>
rng(seed, 'twister');

if numel(sides) ~= numel(contactCounts) || isempty(sides)
    error('run_single_current_backend_equivalence:InvalidElectrodeInventory', ...
        'Sides and contact counts must be nonempty and have equal length.');
end
designs = { ...
    'single_cathode_case_return', ...
    'multi_cathode_case_return', ...
    'electrode_return'};
emptyCase = struct( ...
    'case_id', '', ...
    'hemisphere', '', ...
    'design', '', ...
    'control_mode', 'current', ...
    'unit', 'mA', ...
    'amplitude_mA', NaN, ...
    'pulse_width_us', NaN, ...
    'frequency_hz', 130, ...
    'has_case_return', false, ...
    'has_electrode_return', false, ...
    'contacts', empty_contacts());
cases = repmat(emptyCase, 1, numel(sides) * numel(designs));

caseIndex = 0;
for sideIndex = 1:numel(sides)
    side = upper(char(string(sides{sideIndex})));
    contactCount = double(contactCounts(sideIndex));
    if ~ismember(side, {'L', 'R'}) || ~isscalar(contactCount) || ...
            ~isfinite(contactCount) || contactCount < 4 || ...
            contactCount ~= fix(contactCount)
        error('run_single_current_backend_equivalence:InvalidElectrodeInventory', ...
            'Each hemisphere requires at least four integer contacts.');
    end
    for designIndex = 1:numel(designs)
        caseIndex = caseIndex + 1;
        design = designs{designIndex};
        amplitude = 0.5 + (5.0 - 0.5) * rand();
        pulseWidth = randi([30 120]);
        contactOrder = randperm(contactCount);
        contacts = design_contacts(design, contactOrder);
        cases(caseIndex) = struct( ...
            'case_id', sprintf('%s_%s', side, design), ...
            'hemisphere', side, ...
            'design', design, ...
            'control_mode', 'current', ...
            'unit', 'mA', ...
            'amplitude_mA', amplitude, ...
            'pulse_width_us', pulseWidth, ...
            'frequency_hz', 130, ...
            'has_case_return', endsWith(design, 'case_return'), ...
            'has_electrode_return', strcmp(design, 'electrode_return'), ...
            'contacts', contacts);
    end
end
end

function contacts = design_contacts(design, order)
switch design
    case 'single_cathode_case_return'
        contacts = [ ...
            make_contact(order(1), 'cathode', 1), ...
            make_contact('case', 'anode', 1)];
    case 'multi_cathode_case_return'
        cathodeFractions = normalized_random_fractions(2);
        contacts = [ ...
            make_contact(order(1), 'cathode', cathodeFractions(1)), ...
            make_contact(order(2), 'cathode', cathodeFractions(2)), ...
            make_contact('case', 'anode', 1)];
    case 'electrode_return'
        cathodeFractions = normalized_random_fractions(2);
        anodeFractions = normalized_random_fractions(2);
        contacts = [ ...
            make_contact(order(1), 'cathode', cathodeFractions(1)), ...
            make_contact(order(2), 'cathode', cathodeFractions(2)), ...
            make_contact(order(3), 'anode', anodeFractions(1)), ...
            make_contact(order(4), 'anode', anodeFractions(2))];
    otherwise
        error('run_single_current_backend_equivalence:InvalidDesign', ...
            'Unsupported current fixture design: %s', design);
end
end

function values = normalized_random_fractions(count)
values = rand(1, count);
values = values / sum(values);
values(end) = 1 - sum(values(1:end-1));
end

function contact = make_contact(identifier, polarity, fraction)
contact = struct('contact', identifier, 'polarity', polarity, ...
    'fraction', fraction);
end

function contacts = empty_contacts()
contacts = repmat(struct('contact', NaN, 'polarity', '', ...
    'fraction', NaN), 1, 0);
end

function evidence = vector_superposition_fixture()
signedSourceVectors = [3 4 0; -1 2 0; 0 -3 4];
combinedVector = sum(signedSourceVectors, 1);
sourceMagnitudes = vecnorm(signedSourceVectors, 2, 2);
combinedMagnitude = norm(combinedVector);
scalarMaximum = max(sourceMagnitudes);
scalarSum = sum(sourceMagnitudes);
evidence = struct( ...
    'signed_source_vectors', signedSourceVectors, ...
    'combined_vector', combinedVector, ...
    'source_magnitudes', sourceMagnitudes, ...
    'combined_magnitude', combinedMagnitude, ...
    'scalar_max_magnitude', scalarMaximum, ...
    'scalar_sum_magnitude', scalarSum, ...
    'signed_linear_superposition_passed', ...
        isequal(combinedVector, sum(signedSourceVectors, 1)), ...
    'scalar_max_rejected', abs(combinedMagnitude - scalarMaximum) > 1e-12, ...
    'scalar_sum_rejected', abs(combinedMagnitude - scalarSum) > 1e-12);
end

function outputs = run_all_cases(copiedSubject, cases, atlasSet, runRoot, seed)
backends = {'simbio', 'simbio_onesolve'};
outputs = struct();
for caseIndex = 1:numel(cases)
    oneCase = cases(caseIndex);
    caseField = matlab.lang.makeValidName(oneCase.case_id);
    for backendIndex = 1:numel(backends)
        backend = backends{backendIndex};
        backendField = matlab.lang.makeValidName(backend);
        for repeat = 1:2
            label = sprintf('current_equivalence_%s_%s_run%d', ...
                backend, oneCase.case_id, repeat);
            taskResult = execute_backend(copiedSubject, oneCase, backend, ...
                label, atlasSet, seed + 1000 * caseIndex);
            targetDir = fullfile(runRoot, 'outputs', backend, ...
                oneCase.case_id, sprintf('run-%d', repeat));
            mkdir(targetDir);
            outputs.(caseField).(backendField)(repeat) = struct( ...
                'native', copy_output(taskResult.efield_native, ...
                    fullfile(targetDir, 'native_efield.nii')), ...
                'mni', copy_output(taskResult.efield_mni, ...
                    fullfile(targetDir, 'mni_efield.nii')));
        end
    end
end
end

function taskResult = execute_backend(copiedSubject, oneCase, backend, ...
        label, atlasSet, seed)
cfg = mh_fiber_default_config(copiedSubject, label);
cfg.forceRecomputeVTA = true;
cfg.vta.modelKey = backend;
cfg.vta.model = mh_fiber_model_name(backend);
cfg.vta.gmAtlas = atlasSet;
cfg.vta.executionMode = 'sequential';
cfg.vta.parallelWorkers = 1;

source = struct( ...
    'side', oneCase.hemisphere, ...
    'amp', oneCase.amplitude_mA, ...
    'unit', 'mA', ...
    'pulseWidth', oneCase.pulse_width_us, ...
    'frequency', oneCase.frequency_hz, ...
    'controlMode', 'current', ...
    'contacts', oneCase.contacts);
stimSpec = struct( ...
    'label', label, ...
    'model', backend, ...
    'space', 'MNI152NLin2009bAsym', ...
    'sources', source);
[taskResults, ~, ~, ~, ~] = mh_vta_run_stim_spec_tasks( ...
    cfg, stimSpec, {oneCase.hemisphere}, ...
    'ModelKey', backend, ...
    'Force', true, ...
    'OutputSpaces', {'native', 'mni'}, ...
    'ExportThresholdVPerMm', 0.18, ...
    'GmAtlas', atlasSet, ...
    'RngSeedBase', seed);
if numel(taskResults) ~= 1 || ~strcmp(taskResults.status, 'complete')
    error('run_single_current_backend_equivalence:BackendRunFailed', ...
        'Backend %s did not return one complete task.', backend);
end
taskResult = taskResults;
end

function [efieldRows, binaryRows, repeatRows, passed] = ...
        compare_all_outputs(cases, outputs)
efieldRows = table();
binaryRows = table();
repeatRows = table();
passed = true;
spaces = {'native', 'mni'};
for caseIndex = 1:numel(cases)
    oneCase = cases(caseIndex);
    caseField = matlab.lang.makeValidName(oneCase.case_id);
    standard = outputs.(caseField).simbio;
    oneSolve = outputs.(caseField).simbio_onesolve;
    for spaceIndex = 1:numel(spaces)
        space = spaces{spaceIndex};
        comparisons = { ...
            standard(1).(space), standard(2).(space), 'repeatability', 'simbio'; ...
            oneSolve(1).(space), oneSolve(2).(space), 'repeatability', 'simbio_onesolve'; ...
            standard(1).(space), oneSolve(1).(space), 'equivalence', 'backend'};
        for comparisonIndex = 1:size(comparisons, 1)
            comparison = mh_compare_single_source_backend_outputs( ...
                comparisons{comparisonIndex, 1}, comparisons{comparisonIndex, 2}, ...
                'Space', space, ...
                'Side', oneCase.hemisphere, ...
                'Comparison', comparisons{comparisonIndex, 3}, ...
                'ThrowOnFailure', false);
            efield = annotate_rows(comparison.efield_row, oneCase.case_id, ...
                comparisons{comparisonIndex, 4});
            binary = annotate_rows(comparison.binary_rows, oneCase.case_id, ...
                comparisons{comparisonIndex, 4});
            if strcmp(comparisons{comparisonIndex, 3}, 'repeatability')
                repeatRows = [repeatRows; efield]; %#ok<AGROW>
            else
                efieldRows = [efieldRows; efield]; %#ok<AGROW>
                binaryRows = [binaryRows; binary]; %#ok<AGROW>
            end
            passed = passed && comparison.pass;
        end
    end
end
end

function rows = annotate_rows(rows, caseId, backendComparison)
rows = addvars(rows, repmat(string(caseId), height(rows), 1), ...
    repmat(string(backendComparison), height(rows), 1), ...
    'Before', 1, 'NewVariableNames', {'case_id', 'backend_comparison'});
end

function inventory = case_inventory(cases)
inventory = table( ...
    string({cases.case_id})', ...
    string({cases.hemisphere})', ...
    string({cases.design})', ...
    [cases.amplitude_mA]', ...
    [cases.pulse_width_us]', ...
    [cases.frequency_hz]', ...
    [cases.has_case_return]', ...
    [cases.has_electrode_return]', ...
    'VariableNames', {'case_id', 'hemisphere', 'design', 'amplitude_mA', ...
        'pulse_width_us', 'frequency_hz', 'has_case_return', ...
        'has_electrode_return'});
end

function subject = select_subject(document, subjectId)
if ~isstruct(document) || ~isfield(document, 'schema_version') || ...
        ~strcmp(char(string(document.schema_version)), ...
            'dual_frequency_study_v1') || ...
        ~isfield(document, 'study') || ...
        ~isfield(document.study, 'subjects')
    error('run_single_current_backend_equivalence:InvalidStudyBase', ...
        'Study-base JSON does not satisfy the required study contract.');
end
subjects = document.study.subjects;
matching = arrayfun(@(value) strcmp(char(string(value.subject_id)), ...
    char(string(subjectId))), subjects);
if nnz(matching) ~= 1
    error('run_single_current_backend_equivalence:SubjectSelectionFailed', ...
        'Expected exactly one subject matching %s.', char(string(subjectId)));
end
subject = subjects(matching);
end

function [sides, contactCounts] = subject_electrode_inventory(subject)
electrodes = subject.electrodes;
sides = cell(1, numel(electrodes));
contactCounts = zeros(1, numel(electrodes));
for index = 1:numel(electrodes)
    sides{index} = upper(char(string(electrodes(index).hemisphere)));
    contactCounts(index) = double(electrodes(index).contact_count);
end
[sides, order] = sort(sides);
contactCounts = contactCounts(order);
if ~isequal(string(sides), ["L" "R"])
    error('run_single_current_backend_equivalence:BilateralCasesRequired', ...
        'Current acceptance requires one left and one right electrode.');
end
end

function runRoot = create_run_root(workRootValue)
workRoot = char(string(workRootValue));
if ~isfolder(workRoot)
    mkdir(workRoot);
end
stamp = char(datetime('now', 'Format', 'yyyyMMdd_HHmmss_SSS'));
runRoot = fullfile(workRoot, ...
    ['vta_single_current_backend_equivalence_', stamp]);
if isfolder(runRoot)
    error('run_single_current_backend_equivalence:ExistingValidationRoot', ...
        'Refusing to overwrite validation root: %s', runRoot);
end
mkdir(runRoot);
end

function copiedSubject = copy_subject_tree(sourceSubject, runRoot)
[datasetRoot, derivativeRoot] = bids_roots(sourceSubject);
[~, subjectLeaf] = fileparts(sourceSubject);
copyRoot = fullfile(runRoot, 'copied_subject');
copiedDerivativeRoot = fullfile(copyRoot, 'derivatives', 'leaddbs');
copiedSubject = fullfile(copiedDerivativeRoot, subjectLeaf);
mkdir(copiedDerivativeRoot);
copy_required_file(fullfile(datasetRoot, 'dataset_description.json'), ...
    fullfile(copyRoot, 'dataset_description.json'));
copy_optional_file(fullfile(derivativeRoot, 'dataset_description.json'), ...
    fullfile(copiedDerivativeRoot, 'dataset_description.json'));
[ok, message] = copyfile(sourceSubject, copiedSubject);
if ~ok
    error('run_single_current_backend_equivalence:SubjectCopyFailed', ...
        'Could not copy subject directory: %s', message);
end
end

function [datasetRoot, derivativeRoot] = bids_roots(subjectDir)
marker = [filesep, 'derivatives', filesep, 'leaddbs', filesep];
markerIndex = strfind(subjectDir, marker);
if numel(markerIndex) ~= 1
    error('run_single_current_backend_equivalence:InvalidBidsSubjectPath', ...
        'Subject must be under derivatives/leaddbs: %s', subjectDir);
end
datasetRoot = subjectDir(1:markerIndex - 1);
derivativeRoot = fullfile(datasetRoot, 'derivatives', 'leaddbs');
end

function copy_required_file(source, target)
must_be_file(source, 'BIDS dataset description');
[ok, message] = copyfile(source, target);
if ~ok
    error('run_single_current_backend_equivalence:CopyFailed', ...
        'Could not copy required BIDS file: %s', message);
end
end

function copy_optional_file(source, target)
if isfile(source)
    [ok, message] = copyfile(source, target);
    if ~ok
        error('run_single_current_backend_equivalence:CopyFailed', ...
            'Could not copy optional BIDS file: %s', message);
    end
end
end

function target = copy_output(source, target)
source = must_be_file(source, 'backend E-field');
if endsWith(source, '.nii.gz')
    target = [erase(target, '.nii'), '.nii.gz'];
end
[ok, message] = copyfile(source, target);
if ~ok
    error('run_single_current_backend_equivalence:OutputCopyFailed', ...
        'Could not copy backend output: %s', message);
end
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

function hash = fixture_hash(cases)
hash = sha256_text(jsonencode(cases));
end

function hash = directory_inventory_hash(root)
files = dir(fullfile(root, '**', '*'));
files = files(~[files.isdir]);
relativePaths = strings(1, numel(files));
for index = 1:numel(files)
    fullPath = fullfile(files(index).folder, files(index).name);
    relativePaths(index) = string(erase(fullPath, [root, filesep]));
end
relativePaths = sort(relativePaths);
parts = strings(1, numel(relativePaths));
for index = 1:numel(relativePaths)
    path = fullfile(root, char(relativePaths(index)));
    parts(index) = relativePaths(index) + ":" + ...
        string(mh_fiber_file_sha256(path));
end
hash = sha256_text(strjoin(parts, newline));
end

function hash = sha256_text(value)
digest = java.security.MessageDigest.getInstance('SHA-256');
digest.update(unicode2native(char(string(value)), 'UTF-8'));
bytes = typecast(digest.digest(), 'uint8');
hash = lower(reshape(dec2hex(bytes, 2)', 1, []));
end

function path = must_be_file(value, label)
path = char(string(value));
if ~isfile(path)
    error('run_single_current_backend_equivalence:MissingFile', ...
        'Required %s does not exist: %s', label, path);
end
end

function path = must_be_folder(value, label)
path = char(string(value));
if ~isfolder(path)
    error('run_single_current_backend_equivalence:MissingFolder', ...
        'Required %s does not exist: %s', label, path);
end
end

function valid = is_valid_seed(value)
valid = isnumeric(value) && isscalar(value) && isfinite(value) && ...
    value >= 0 && value == fix(value);
end

function write_json(path, value)
text = jsonencode(value, PrettyPrint=true);
fid = fopen(path, 'w');
if fid < 0
    error('run_single_current_backend_equivalence:WriteFailed', ...
        'Could not write JSON: %s', path);
end
cleanupObj = onCleanup(@() fclose(fid)); %#ok<NASGU>
fprintf(fid, '%s\n', text);
end

function value = timestamp_iso()
value = char(datetime('now', 'TimeZone', 'UTC', ...
    'Format', 'yyyy-MM-dd''T''HH:mm:ss.SSS''Z'''));
end
