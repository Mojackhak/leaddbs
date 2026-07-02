function result = mh_fiber_run_stnsnr_target_component_vta_distribution(varargin)
% Compute target-component STN/SNr VTA coverage distributions.

parser = inputParser;
parser.FunctionName = 'mh_fiber_run_stnsnr_target_component_vta_distribution';
parser.addParameter('RepoDir', '', @(x) ischar(x) || isstring(x));
parser.addParameter('SubjectRoot', '/Volumes/VAL/STNSNr/derivatives/leaddbs', @(x) ischar(x) || isstring(x));
parser.addParameter('ContactQcCsv', '/Volumes/VAL/STNSNr/summary/vta/cohort_contact_mapping_qc.csv', @(x) ischar(x) || isstring(x));
parser.addParameter('AtlasDir', '', @(x) ischar(x) || isstring(x));
parser.addParameter('OutputDir', '/Volumes/VAL/STNSNr/summary/vta/target_component_distribution', @(x) ischar(x) || isstring(x));
parser.addParameter('ThresholdsVPerMm', [0.18, 0.20, 0.22], @(x) isnumeric(x) && isvector(x));
parser.addParameter('MainThresholdVPerMm', 0.20, @(x) isnumeric(x) && isscalar(x));
parser.addParameter('OutputVoxelSizeMm', 0.5, @(x) isnumeric(x) && isscalar(x) && x > 0);
parser.addParameter('ForceVta', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('ForceOutputs', false, @(x) islogical(x) || isnumeric(x));
parser.parse(varargin{:});
opts = parser.Results;

repoDir = char(string(opts.RepoDir));
if isempty(repoDir)
    repoDir = resolve_repo_dir(mfilename('fullpath'));
end
subjectRoot = char(string(opts.SubjectRoot));
contactQcCsv = char(string(opts.ContactQcCsv));
atlasDir = char(string(opts.AtlasDir));
if isempty(atlasDir)
    atlasDir = fullfile(repoDir, 'templates', 'space', 'MNI152NLin2009bAsym', ...
        'atlases', 'Custom_Ewert_Zhang_Middlebrooks0.05');
end
outputDir = char(string(opts.OutputDir));

must_be_folder(repoDir, 'repository directory');
must_be_folder(subjectRoot, 'Lead-DBS subject root');
must_be_file(contactQcCsv, 'cohort contact mapping QC CSV');
must_be_folder(atlasDir, 'STN/SNr atlas directory');
verify_atlas_files(atlasDir);

thresholdsVPerMm = unique(double(opts.ThresholdsVPerMm(:))', 'stable');
thresholdsVPerM = thresholdsVPerMm .* 1000;
mainThreshold = double(opts.MainThresholdVPerMm);
exportThreshold = min(thresholdsVPerMm);

make_dir(outputDir);
make_dir(fullfile(outputDir, 'figures'));
make_dir(fullfile(outputDir, 'masks'));

contactTable = readtable(contactQcCsv, 'TextType', 'string');
contactTable = normalize_contact_table(contactTable);
validate_contact_table(contactTable);

components = build_component_table(contactTable);
validate_component_table(components);

manifest = struct();
manifest.generated_at = char(datetime('now', 'TimeZone', 'local', 'Format', 'yyyy-MM-dd HH:mm:ss Z'));
manifest.repo_dir = repoDir;
manifest.subject_root = subjectRoot;
manifest.contact_qc_csv = contactQcCsv;
manifest.atlas_dir = atlasDir;
manifest.output_dir = outputDir;
manifest.thresholds_v_per_mm = thresholdsVPerMm;
manifest.thresholds_v_per_m = thresholdsVPerM;
manifest.main_threshold_v_per_mm = mainThreshold;
manifest.horn_export_threshold_v_per_mm = exportThreshold;
manifest.gray_matter_conductivity_s_per_m = 0.33;
manifest.white_matter_conductivity_s_per_m = 0.14;
manifest.analysis_unit = 'subject_id x phase x protocol x side x target';
manifest.component_count = height(components);
manifest.component_origin_definitions = struct( ...
    'observed_single_target', 'Original side-level condition contains only one target.', ...
    'observed_target_union', 'Multiple same-target contacts or alternating subprograms represented as a union.', ...
    'counterfactual_component_from_continuous_mixed', ...
    'Continuous STN+SNr stimulation split into a target-specific component proxy.');
manifest.components = {};

coverageRows = {};
componentQcRows = {};
for c = 1:height(components)
    component = components(c, :);
    subjectId = char(component.subject_id);
    patientName = char(component.patient_name);
    phase = char(component.phase);
    protocol = char(component.protocol);
    sideCode = char(component.side);
    target = char(component.target);
    subjectDir = fullfile(subjectRoot, patientName);

    fprintf('\n[%d/%d] Target-component VTA: %s %s %s %s %s\n', ...
        c, height(components), subjectId, phase, protocol, sideCode, target);
    must_be_folder(subjectDir, ['subject directory for ', subjectId]);

    componentRows = contactTable(contactTable.subject_id == component.subject_id & ...
        contactTable.phase == component.phase & contactTable.protocol == component.protocol & ...
        contactTable.side == component.side & contactTable.target == component.target, :);
    sideRows = contactTable(contactTable.subject_id == component.subject_id & ...
        contactTable.phase == component.phase & contactTable.protocol == component.protocol & ...
        contactTable.side == component.side, :);
    conditionRows = contactTable(contactTable.subject_id == component.subject_id & ...
        contactTable.phase == component.phase & contactTable.protocol == component.protocol, :);

    componentOrigin = determine_component_origin(sideRows, componentRows);
    efieldPaths = resolve_component_efields(componentRows, sideRows, conditionRows, ...
        subjectDir, patientName, component, componentOrigin, exportThreshold, opts);

    componentDirs = prepare_component_dirs(outputDir, component);
    [componentCoverageRows, componentManifest] = analyze_component_coverage( ...
        efieldPaths, componentRows, component, componentOrigin, componentDirs, atlasDir, ...
        thresholdsVPerMm, thresholdsVPerM, mainThreshold, opts.OutputVoxelSizeMm, ...
        logical(opts.ForceOutputs));

    coverageRows = [coverageRows; componentCoverageRows]; %#ok<AGROW>
    componentQcRows(end+1, :) = component_qc_row(component, componentRows, componentOrigin, efieldPaths); %#ok<AGROW>
    manifest.components{end+1} = componentManifest;
end

coverageTable = rows_to_coverage_table(coverageRows);
componentQcTable = rows_to_component_qc_table(componentQcRows);
write_outputs(outputDir, coverageTable, componentQcTable, manifest, mainThreshold);
validate_outputs(outputDir, coverageTable, componentQcTable, thresholdsVPerMm);

result = struct();
result.outputDir = outputDir;
result.coverageLongCsv = fullfile(outputDir, 'cohort_target_component_vta_coverage_long.csv');
result.componentQcCsv = fullfile(outputDir, 'cohort_target_component_contact_qc.csv');
result.summaryCsv = fullfile(outputDir, 'cohort_target_component_distribution_summary.csv');
result.manifestJson = fullfile(outputDir, 'cohort_target_component_generation_manifest.json');
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
stringVars = {'subject_id', 'name_en', 'name_zh', 'phase', 'protocol', 'target', ...
    'side', 'parameter_source', 'stimulation_pattern', 'alternating_group', ...
    'notes', 'subject_dir'};
tableOut = force_string_vars(tableOut, stringVars);
if ismember('contact_side_rule_ok', tableOut.Properties.VariableNames)
    tableOut.contact_side_rule_ok = force_logical_values(tableOut.contact_side_rule_ok);
end
numericVars = {'contact', 'voltage', 'pulse_width', 'frequency', ...
    'num_contacts_per_side', 'raw_contact', 'lead_contact'};
for i = 1:numel(numericVars)
    if ismember(numericVars{i}, tableOut.Properties.VariableNames)
        tableOut.(numericVars{i}) = double(tableOut.(numericVars{i}));
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
    error('mh_fiber_run_stnsnr_target_component_vta_distribution:InvalidLogicalColumn', ...
        'Could not parse logical values in contact_side_rule_ok.');
end
end

function validate_contact_table(contactTable)
required = {'subject_id', 'name_en', 'phase', 'protocol', 'target', 'side', ...
    'voltage', 'pulse_width', 'frequency', 'stimulation_pattern', ...
    'raw_contact', 'lead_contact', 'contact_side_rule_ok'};
for i = 1:numel(required)
    if ~ismember(required{i}, contactTable.Properties.VariableNames)
        error('mh_fiber_run_stnsnr_target_component_vta_distribution:MissingContactColumn', ...
            'Missing contact QC column: %s', required{i});
    end
end
if height(contactTable) ~= 194
    error('mh_fiber_run_stnsnr_target_component_vta_distribution:UnexpectedContactRowCount', ...
        'Expected 194 contact rows, found %d.', height(contactTable));
end
if any(~contactTable.contact_side_rule_ok)
    error('mh_fiber_run_stnsnr_target_component_vta_distribution:ContactRuleQcFailed', ...
        'At least one contact failed the side mapping rule.');
end
if ~all(ismember(unique(contactTable.target), ["STN", "SNr"]))
    error('mh_fiber_run_stnsnr_target_component_vta_distribution:UnexpectedTarget', ...
        'Contact QC contains targets other than STN and SNr.');
end
end

function components = build_component_table(contactTable)
keyVars = {'subject_id', 'name_en', 'name_zh', 'phase', 'protocol', 'side', 'target'};
components = unique(contactTable(:, keyVars), 'rows', 'stable');
components.patient_name = "sub-" + components.name_en;
componentId = strings(height(components), 1);
for i = 1:height(components)
    componentId(i) = string(sanitize_label(sprintf('%s_%s_%s_%s_%s', ...
        components.subject_id(i), components.phase(i), components.protocol(i), ...
        components.side(i), components.target(i))));
end
components.component_id = componentId;
components = movevars(components, {'component_id', 'patient_name'}, 'After', 'subject_id');
end

function validate_component_table(components)
if height(components) ~= 190
    error('mh_fiber_run_stnsnr_target_component_vta_distribution:UnexpectedComponentCount', ...
        'Expected 190 target components, found %d.', height(components));
end
stnCount = nnz(components.target == "STN");
snrCount = nnz(components.target == "SNr");
if stnCount ~= 126 || snrCount ~= 64
    error('mh_fiber_run_stnsnr_target_component_vta_distribution:UnexpectedTargetComponentCount', ...
        'Expected 126 STN and 64 SNr components, found %d STN and %d SNr.', stnCount, snrCount);
end
end

function componentOrigin = determine_component_origin(sideRows, componentRows)
targets = unique(sideRows.target, 'stable');
patterns = unique(sideRows.stimulation_pattern, 'stable');
if isscalar(targets)
    if height(componentRows) == 1 && isscalar(patterns) && patterns == "continuous"
        componentOrigin = 'observed_single_target';
    else
        componentOrigin = 'observed_target_union';
    end
    return;
end
if isscalar(patterns) && patterns == "alternating"
    componentOrigin = 'observed_target_union';
elseif isscalar(patterns) && patterns == "continuous"
    componentOrigin = 'counterfactual_component_from_continuous_mixed';
else
    error('mh_fiber_run_stnsnr_target_component_vta_distribution:UnsupportedMixedPattern', ...
        'Unsupported mixed stimulation pattern for component splitting.');
end
end

function efieldPaths = resolve_component_efields(componentRows, sideRows, conditionRows, ...
    subjectDir, patientName, component, componentOrigin, exportThresholdVPerMm, opts)
switch componentOrigin
    case 'counterfactual_component_from_continuous_mixed'
        efieldPaths = generate_component_efield(componentRows, subjectDir, patientName, ...
            component, exportThresholdVPerMm, opts);
    otherwise
        efieldPaths = existing_component_efields(componentRows, sideRows, conditionRows, ...
            subjectDir, patientName, component);
end
end

function efieldPaths = existing_component_efields(componentRows, sideRows, conditionRows, ...
    subjectDir, patientName, component)
sideCode = char(component.side);
target = char(component.target);
subjectId = char(component.subject_id);
phase = char(component.phase);
protocol = char(component.protocol);
patterns = unique(sideRows.stimulation_pattern, 'stable');

efieldPaths = strings(0, 1);
if isscalar(patterns) && patterns == "continuous"
    label = sanitize_label(sprintf('stnsnr_vta_%s_%s_%s_continuous', subjectId, phase, protocol));
    efieldPaths(end+1, 1) = efield_path(subjectDir, patientName, label, sideCode);
elseif isscalar(patterns) && patterns == "alternating"
    alternatingRows = conditionRows(conditionRows.stimulation_pattern == "alternating", :);
    for i = 1:height(alternatingRows)
        one = alternatingRows(i, :);
        if one.side == string(sideCode) && one.target == string(target) && ...
                any(componentRows.raw_contact == one.raw_contact)
            label = sanitize_label(sprintf('stnsnr_vta_%s_%s_%s_alt_%s_%s_c%d_row%d', ...
                subjectId, phase, protocol, one.side(1), one.target(1), one.raw_contact(1), i));
            efieldPaths(end+1, 1) = efield_path(subjectDir, patientName, label, sideCode); %#ok<AGROW>
        end
    end
else
    error('mh_fiber_run_stnsnr_target_component_vta_distribution:UnsupportedObservedPattern', ...
        'Unsupported observed component pattern.');
end

if isempty(efieldPaths)
    error('mh_fiber_run_stnsnr_target_component_vta_distribution:MissingObservedEfield', ...
        'Could not resolve observed e-field for %s %s %s %s %s.', ...
        subjectId, phase, protocol, sideCode, target);
end
efieldPaths = cellstr(efieldPaths);
for i = 1:numel(efieldPaths)
    must_be_file(efieldPaths{i}, sprintf('observed e-field for %s', char(component.component_id)));
end
end

function efieldPaths = generate_component_efield(componentRows, subjectDir, patientName, ...
    component, exportThresholdVPerMm, opts)
sideCode = char(component.side);
componentId = char(component.component_id);
label = sanitize_label(['stnsnr_target_component_', componentId]);
cfg = mh_fiber_default_config(subjectDir, label);
cfg.forceRecomputeVTA = logical(opts.ForceVta);
cfg.vta.modelKey = 'simbio';
cfg.vta.model = mh_fiber_model_name('simbio');
cfg.vta.gmAtlas = 'DISTAL Minimal (Ewert 2017)';
stimSpec = rows_to_stim_spec(componentRows, label);
cfg = mh_fiber_set_stimulation(cfg, stimSpec);
[S, options, stimFolders] = mh_fiber_build_stimulation(cfg);
options.prefs.machine.vatsettings.horn_cgm = 0.33;
options.prefs.machine.vatsettings.horn_cwm = 0.14;
options.prefs.machine.vatsettings.horn_ethresh = exportThresholdVPerMm;
options.prefs.machine.vatsettings.horn_useatlas = 1;
options.prefs.machine.vatsettings.horn_atlasset = 'DISTAL Minimal (Ewert 2017)';
options.prefs.machine.vatsettings.horn_removeElectrode = 1;

vta = mh_fiber_vta_paths(cfg, stimFolders);
efieldPath = vta.mni.(sideCode).efieldNii;
if logical(opts.ForceVta) || ~isfile(efieldPath)
    fprintf('Generating component e-field: %s side %s\n', label, sideCode);
    run_horn_with_retry(S, side_to_index(sideCode), options, label, efieldPath);
else
    fprintf('Reusing component e-field: %s side %s\n', label, sideCode);
end
must_be_file(efieldPath, sprintf('target-component e-field for %s', componentId));
efieldPaths = {efieldPath};

if ~strcmp(patientName, cfg.patientName)
    error('mh_fiber_run_stnsnr_target_component_vta_distribution:PatientNameMismatch', ...
        'Unexpected patient name mismatch for %s.', componentId);
end
end

function stimSpec = rows_to_stim_spec(rows, label)
stimSpec = struct();
stimSpec.label = char(string(label));
stimSpec.model = 'simbio';
stimSpec.space = 'native_and_mni';
stimSpec.sources = repmat(empty_source(), height(rows), 1);
for i = 1:height(rows)
    source = empty_source();
    source.side = char(rows.side(i));
    source.contact = double(rows.lead_contact(i));
    source.amp = double(rows.voltage(i));
    source.unit = 'V';
    source.pulseWidth = double(rows.pulse_width(i));
    source.frequency = double(rows.frequency(i));
    source.cathode = true;
    source.anode = 'case';
    stimSpec.sources(i) = source;
end
end

function source = empty_source()
source = struct('side', '', 'contact', NaN, 'amp', NaN, 'unit', 'V', ...
    'pulseWidth', NaN, 'frequency', NaN, 'cathode', true, 'anode', 'case');
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
            warning('mh_fiber_run_stnsnr_target_component_vta_distribution:HornPostWriteFailure', ...
                ['Lead-DBS Horn raised an error after writing the expected e-field ', ...
                'for %s side %d: %s'], stimLabel, sideIdx, ME.message);
            return;
        end
        if ~is_horn_index_error(ME) || attempt == maxAttempts
            rethrow(ME);
        end
        warning('mh_fiber_run_stnsnr_target_component_vta_distribution:HornIndexRetry', ...
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

function [coverageRows, componentManifest] = analyze_component_coverage( ...
    efieldPaths, componentRows, component, componentOrigin, componentDirs, atlasDir, ...
    thresholdsVPerMm, thresholdsVPerM, mainThreshold, outputVoxelSize, forceOutputs)
coverageRows = cell(numel(thresholdsVPerM) * 4, 30);
coverageRow = 0;
componentManifest = struct();
componentManifest.component_id = char(component.component_id);
componentManifest.subject_id = char(component.subject_id);
componentManifest.patient_name = char(component.patient_name);
componentManifest.phase = char(component.phase);
componentManifest.protocol = char(component.protocol);
componentManifest.side = char(component.side);
componentManifest.target = char(component.target);
componentManifest.component_origin = componentOrigin;
componentManifest.efield_paths = efieldPaths;
componentManifest.thresholds = struct([]);

sideCode = char(component.side);
ref = build_component_reference_grid(efieldPaths, outputVoxelSize);
stnMask = sample_mask_to_grid(atlas_path(atlasDir, sideCode, 'STN'), ref);
snrMask = sample_mask_to_grid(atlas_path(atlasDir, sideCode, 'SNr'), ref);
if ~any(stnMask(:)) || ~any(snrMask(:))
    error('mh_fiber_run_stnsnr_target_component_vta_distribution:EmptyReslicedAtlasMask', ...
        'Empty STN/SNr mask after reslicing for %s.', char(component.component_id));
end

for t = 1:numel(thresholdsVPerM)
    thresholdVPerMm = thresholdsVPerMm(t);
    thresholdVPerM = thresholdsVPerM(t);
    thresholdLabel = threshold_label(thresholdVPerMm);
    hitCount = zeros(ref.dim, 'uint16');
    for e = 1:numel(efieldPaths)
        hitCount = hitCount + uint16(sample_threshold_to_grid(efieldPaths{e}, ref, thresholdVPerM));
    end
    vtaMask = hitCount > 0;
    overlapMask = hitCount > 1;
    categories = classify_vta(vtaMask, stnMask, snrMask);
    categorySum = nnz(categories.STN_only) + nnz(categories.SNr_only) + ...
        nnz(categories.STN_SNr) + nnz(categories.Outside);
    totalVoxels = nnz(vtaMask);
    if categorySum ~= totalVoxels
        error('mh_fiber_run_stnsnr_target_component_vta_distribution:CategorySumMismatch', ...
            'Category voxel sum does not equal total VTA voxel count.');
    end
    paths = write_component_masks(ref, vtaMask, categories, overlapMask, componentDirs, ...
        component, thresholdLabel, forceOutputs);
    categoryRows = category_summary_rows(categories, vtaMask, stnMask, snrMask, ...
        ref.voxel_volume_mm3);
    for r = 1:size(categoryRows, 1)
        coverageRow = coverageRow + 1;
        coverageRows(coverageRow, :) = { ...
            char(component.component_id), char(component.subject_id), char(component.patient_name), ...
            char(component.phase), char(component.protocol), char(component.side), ...
            char(component.target), componentOrigin, thresholdVPerMm, thresholdVPerM, ...
            categoryRows{r, 1}, categoryRows{r, 2}, categoryRows{r, 3}, ...
            categoryRows{r, 4}, categoryRows{r, 5}, totalVoxels, ...
            totalVoxels * ref.voxel_volume_mm3, numel(efieldPaths), ...
            nnz(overlapMask), nnz(overlapMask) * ref.voxel_volume_mm3, ...
            join_numeric(componentRows.raw_contact), join_numeric(componentRows.lead_contact), ...
            join_numeric(componentRows.voltage), join_numeric(componentRows.pulse_width), ...
            join_numeric(componentRows.frequency), component_pattern(componentRows), ...
            strjoin(string(efieldPaths), ';'), paths.vta, paths.category, paths.overlap};
    end
    if abs(thresholdVPerMm - mainThreshold) < 1e-9
        write_component_figure(componentDirs, component, thresholdLabel, categoryRows);
    end
    componentManifest.thresholds(end+1).threshold_v_per_mm = thresholdVPerMm;
    componentManifest.thresholds(end).threshold_v_per_m = thresholdVPerM;
    componentManifest.thresholds(end).vta_voxels = totalVoxels;
    componentManifest.thresholds(end).vta_volume_mm3 = totalVoxels * ref.voxel_volume_mm3;
    componentManifest.thresholds(end).overlap_voxels = nnz(overlapMask);
    componentManifest.thresholds(end).overlap_volume_mm3 = nnz(overlapMask) * ref.voxel_volume_mm3;
    componentManifest.thresholds(end).vta_mask = paths.vta;
    componentManifest.thresholds(end).category_mask = paths.category;
    componentManifest.thresholds(end).overlap_mask = paths.overlap;
end
end

function ref = build_component_reference_grid(efieldPaths, voxelSize)
allCorners = zeros(0, 3);
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
    error('mh_fiber_run_stnsnr_target_component_vta_distribution:ReferenceGridTooLarge', ...
        'Component reference grid is too large: %s voxels.', mat2str(dim));
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
                error('mh_fiber_run_stnsnr_target_component_vta_distribution:InvalidSampleMode', ...
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

function paths = write_component_masks(ref, vtaMask, categories, overlapMask, componentDirs, ...
    component, thresholdLabel, forceOutputs)
base = sanitize_label(sprintf('%s_phase-%s_protocol-%s_hemi-%s_target-%s_thr-%s', ...
    component.patient_name, component.phase, component.protocol, component.side, ...
    component.target, thresholdLabel));
paths = struct();
paths.vta = fullfile(componentDirs.masks, [base, '_desc-vta.nii']);
paths.category = fullfile(componentDirs.masks, [base, '_desc-vtaCategory.nii']);
paths.overlap = fullfile(componentDirs.masks, [base, '_desc-vtaProgramOverlap.nii']);
if forceOutputs || ~isfile(paths.vta)
    write_ref_nii(ref, double(vtaMask), paths.vta, 2, 'stnsnr target component vta');
end
if forceOutputs || ~isfile(paths.category)
    categoryImg = zeros(ref.dim, 'uint8');
    categoryImg(categories.STN_only) = 1;
    categoryImg(categories.SNr_only) = 2;
    categoryImg(categories.STN_SNr) = 3;
    categoryImg(categories.Outside) = 4;
    write_ref_nii(ref, categoryImg, paths.category, 2, 'stnsnr target component category');
end
if forceOutputs || ~isfile(paths.overlap)
    write_ref_nii(ref, double(overlapMask), paths.overlap, 2, ...
        'stnsnr target component program overlap');
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

function write_component_figure(componentDirs, component, thresholdLabel, categoryRows)
figPath = fullfile(componentDirs.figures, [sanitize_label(sprintf( ...
    '%s_phase-%s_protocol-%s_hemi-%s_target-%s_thr-%s', component.patient_name, ...
    component.phase, component.protocol, component.side, component.target, thresholdLabel)), ...
    '_desc-vtaCoverage.png']);
fig = figure('Visible', 'off', 'Color', 'w', 'Position', [100, 100, 760, 420]);
cleanup = onCleanup(@() close(fig));
names = string(categoryRows(:, 1));
volumes = cell2mat(categoryRows(:, 3));
bar(categorical(names), volumes);
ylabel('Volume (mm3)');
title(sprintf('%s %s %s %s target %s %s', component.patient_name, component.phase, ...
    component.protocol, component.side, component.target, thresholdLabel), 'Interpreter', 'none');
grid on;
exportgraphics(fig, figPath, 'Resolution', 220, 'BackgroundColor', 'white');
clear cleanup;
end

function dirs = prepare_component_dirs(outputDir, component)
conditionKey = sanitize_label(sprintf('%s_%s', component.phase, component.protocol));
targetKey = sanitize_label(sprintf('%s_%s', conditionKey, component.target));
dirs = struct();
dirs.masks = fullfile(outputDir, 'masks', targetKey);
dirs.figures = fullfile(outputDir, 'figures', targetKey);
make_dir(dirs.masks);
make_dir(dirs.figures);
end

function row = component_qc_row(component, componentRows, componentOrigin, efieldPaths)
row = {char(component.component_id), char(component.subject_id), char(component.patient_name), ...
    char(component.phase), char(component.protocol), char(component.side), char(component.target), ...
    componentOrigin, height(componentRows), join_numeric(componentRows.raw_contact), ...
    join_numeric(componentRows.lead_contact), join_numeric(componentRows.voltage), ...
    join_numeric(componentRows.pulse_width), join_numeric(componentRows.frequency), ...
    component_pattern(componentRows), strjoin(string(efieldPaths), ';')};
end

function pattern = component_pattern(rows)
patterns = unique(string(rows.stimulation_pattern), 'stable');
pattern = strjoin(patterns, ';');
end

function tableOut = rows_to_coverage_table(rows)
if isempty(rows)
    tableOut = table();
    return;
end
tableOut = cell2table(rows, 'VariableNames', { ...
    'component_id', 'subject_id', 'patient_name', 'phase', 'protocol', 'side', ...
    'target', 'component_origin', 'threshold_v_per_mm', 'threshold_v_per_m', ...
    'category', 'voxel_count', 'volume_mm3', 'percent_total_vta', ...
    'percent_anatomical_compartment', 'total_vta_voxels', 'total_vta_volume_mm3', ...
    'program_count', 'program_overlap_voxels', 'program_overlap_volume_mm3', ...
    'raw_contacts', 'lead_contacts', 'voltages', 'pulse_widths', 'frequencies', ...
    'stimulation_pattern', 'efield_paths', 'vta_mask_path', 'category_mask_path', ...
    'program_overlap_mask_path'});
stringVars = {'component_id', 'subject_id', 'patient_name', 'phase', 'protocol', ...
    'side', 'target', 'component_origin', 'category', 'raw_contacts', 'lead_contacts', ...
    'voltages', 'pulse_widths', 'frequencies', 'stimulation_pattern', 'efield_paths', ...
    'vta_mask_path', 'category_mask_path', 'program_overlap_mask_path'};
tableOut = force_string_vars(tableOut, stringVars);
end

function tableOut = rows_to_component_qc_table(rows)
if isempty(rows)
    tableOut = table();
    return;
end
tableOut = cell2table(rows, 'VariableNames', { ...
    'component_id', 'subject_id', 'patient_name', 'phase', 'protocol', 'side', ...
    'target', 'component_origin', 'n_contacts', 'raw_contacts', 'lead_contacts', ...
    'voltages', 'pulse_widths', 'frequencies', 'stimulation_pattern', 'efield_paths'});
stringVars = {'component_id', 'subject_id', 'patient_name', 'phase', 'protocol', ...
    'side', 'target', 'component_origin', 'raw_contacts', 'lead_contacts', ...
    'voltages', 'pulse_widths', 'frequencies', 'stimulation_pattern', 'efield_paths'};
tableOut = force_string_vars(tableOut, stringVars);
end

function write_outputs(outputDir, coverageTable, componentQcTable, manifest, mainThreshold)
writetable(coverageTable, fullfile(outputDir, 'cohort_target_component_vta_coverage_long.csv'));
wide = make_wide_table(coverageTable);
writetable(wide, fullfile(outputDir, 'cohort_target_component_vta_coverage_wide.csv'));
summary = summarize_distribution(coverageTable);
writetable(summary, fullfile(outputDir, 'cohort_target_component_distribution_summary.csv'));
writetable(componentQcTable, fullfile(outputDir, 'cohort_target_component_contact_qc.csv'));
write_json(fullfile(outputDir, 'cohort_target_component_generation_manifest.json'), manifest);
write_summary_figures(outputDir, coverageTable, mainThreshold);
end

function wide = make_wide_table(coverageTable)
keyVars = {'component_id', 'subject_id', 'patient_name', 'phase', 'protocol', ...
    'side', 'target', 'component_origin', 'threshold_v_per_mm', 'threshold_v_per_m', ...
    'total_vta_voxels', 'total_vta_volume_mm3', 'program_count', ...
    'program_overlap_voxels', 'program_overlap_volume_mm3', 'raw_contacts', ...
    'lead_contacts', 'voltages', 'pulse_widths', 'frequencies', 'stimulation_pattern'};
wideInput = coverageTable(:, [keyVars, {'category', 'volume_mm3'}]);
wide = unstack(wideInput, 'volume_mm3', 'category');
end

function summary = summarize_distribution(coverageTable)
[G, target, phase, protocol, threshold, category] = findgroups(coverageTable.target, ...
    coverageTable.phase, coverageTable.protocol, coverageTable.threshold_v_per_mm, ...
    coverageTable.category);
nComponents = splitapply(@numel, coverageTable.volume_mm3, G);
nSubjects = splitapply(@(x) numel(unique(string(x))), coverageTable.subject_id, G);
meanVolume = splitapply(@(x) mean(x, 'omitnan'), coverageTable.volume_mm3, G);
medianVolume = splitapply(@(x) median(x, 'omitnan'), coverageTable.volume_mm3, G);
sdVolume = splitapply(@(x) std(x, 'omitnan'), coverageTable.volume_mm3, G);
iqrVolume = splitapply(@local_iqr, coverageTable.volume_mm3, G);
minVolume = splitapply(@(x) min(x, [], 'omitnan'), coverageTable.volume_mm3, G);
maxVolume = splitapply(@(x) max(x, [], 'omitnan'), coverageTable.volume_mm3, G);
meanPercent = splitapply(@(x) mean(x, 'omitnan'), coverageTable.percent_total_vta, G);
summary = table(target, phase, protocol, threshold, category, nComponents, nSubjects, ...
    meanVolume, medianVolume, sdVolume, iqrVolume, minVolume, maxVolume, meanPercent, ...
    'VariableNames', {'target', 'phase', 'protocol', 'threshold_v_per_mm', 'category', ...
    'n_components', 'n_subjects', 'mean_volume_mm3', 'median_volume_mm3', ...
    'sd_volume_mm3', 'iqr_volume_mm3', 'min_volume_mm3', 'max_volume_mm3', ...
    'mean_percent_total_vta'});
end

function value = local_iqr(values)
values = values(~isnan(values));
if isempty(values)
    value = NaN;
else
    value = quantile(values, 0.75) - quantile(values, 0.25);
end
end

function write_summary_figures(outputDir, coverageTable, mainThreshold)
figureDir = fullfile(outputDir, 'figures');
make_dir(figureDir);
mainRows = coverageTable(abs(coverageTable.threshold_v_per_mm - mainThreshold) < 1e-9, :);
summary = summarize_distribution(mainRows);

barData = unstack(summary(:, {'target', 'category', 'mean_volume_mm3'}), ...
    'mean_volume_mm3', 'category');
targets = categorical(barData.target);
categories = {'STN_only', 'SNr_only', 'STN_SNr', 'Outside'};
matrix = zeros(height(barData), numel(categories));
for i = 1:numel(categories)
    if ismember(categories{i}, barData.Properties.VariableNames)
        matrix(:, i) = barData.(categories{i});
    end
end
fig = figure('Visible', 'off', 'Color', 'w', 'Position', [100, 100, 760, 420]);
bar(targets, matrix, 'stacked');
ylabel('Mean volume (mm3)');
title(sprintf('Target-component VTA coverage at %.2f V/mm', mainThreshold));
legend(categories, 'Location', 'eastoutside', 'Interpreter', 'none');
grid on;
exportgraphics(fig, fullfile(figureDir, 'target_component_stacked_bar_thr0p20.png'), ...
    'Resolution', 220, 'BackgroundColor', 'white');
close(fig);

fig = figure('Visible', 'off', 'Color', 'w', 'Position', [100, 100, 920, 420]);
boxchart(categorical(strcat(mainRows.target, " / ", mainRows.category)), mainRows.volume_mm3);
ylabel('Volume (mm3)');
title(sprintf('Target-component category volumes at %.2f V/mm', mainThreshold));
grid on;
exportgraphics(fig, fullfile(figureDir, 'target_component_boxplot_thr0p20.png'), ...
    'Resolution', 220, 'BackgroundColor', 'white');
close(fig);

totalRows = unique(coverageTable(:, {'component_id', 'target', 'threshold_v_per_mm', ...
    'total_vta_volume_mm3'}), 'rows');
[G, target, threshold] = findgroups(totalRows.target, totalRows.threshold_v_per_mm);
meanTotal = splitapply(@(x) mean(x, 'omitnan'), totalRows.total_vta_volume_mm3, G);
plotTable = table(target, threshold, meanTotal);
fig = figure('Visible', 'off', 'Color', 'w', 'Position', [100, 100, 620, 420]);
hold on;
targetValues = unique(plotTable.target, 'stable');
for i = 1:numel(targetValues)
    one = sortrows(plotTable(plotTable.target == targetValues(i), :), 'threshold');
    plot(one.threshold, one.meanTotal, '-o', 'LineWidth', 1.5, 'DisplayName', targetValues(i));
end
hold off;
xlabel('Threshold (V/mm)');
ylabel('Mean total VTA volume (mm3)');
title('Target-component threshold sensitivity');
legend('Location', 'best');
grid on;
exportgraphics(fig, fullfile(figureDir, 'target_component_threshold_sensitivity.png'), ...
    'Resolution', 220, 'BackgroundColor', 'white');
close(fig);
end

function validate_outputs(outputDir, coverageTable, componentQcTable, thresholdsVPerMm)
if height(componentQcTable) ~= 190
    error('mh_fiber_run_stnsnr_target_component_vta_distribution:ComponentQcRowCount', ...
        'Expected 190 component QC rows, found %d.', height(componentQcTable));
end
if height(coverageTable) ~= 2280
    error('mh_fiber_run_stnsnr_target_component_vta_distribution:CoverageRowCount', ...
        'Expected 2280 coverage rows, found %d.', height(coverageTable));
end
stnCount = nnz(componentQcTable.target == "STN");
snrCount = nnz(componentQcTable.target == "SNr");
if stnCount ~= 126 || snrCount ~= 64
    error('mh_fiber_run_stnsnr_target_component_vta_distribution:OutputTargetCount', ...
        'Expected 126 STN and 64 SNr rows, found %d STN and %d SNr.', stnCount, snrCount);
end

[G, componentId, threshold] = findgroups(coverageTable.component_id, coverageTable.threshold_v_per_mm);
for g = 1:max(G)
    one = coverageTable(G == g, :);
    if height(one) ~= 4
        error('mh_fiber_run_stnsnr_target_component_vta_distribution:MissingCategoryRows', ...
            'Expected four category rows for %s at %.2f.', componentId(g), threshold(g));
    end
    if abs(sum(one.voxel_count) - one.total_vta_voxels(1)) > 0
        error('mh_fiber_run_stnsnr_target_component_vta_distribution:CategoryVoxelMismatch', ...
            'Category voxel count does not equal total VTA voxel count.');
    end
end

totalRows = unique(coverageTable(:, {'component_id', 'threshold_v_per_mm', ...
    'total_vta_volume_mm3'}), 'rows');
[G, componentId] = findgroups(totalRows.component_id);
for g = 1:max(G)
    one = sortrows(totalRows(G == g, :), 'threshold_v_per_mm');
    if height(one) ~= numel(thresholdsVPerMm)
        error('mh_fiber_run_stnsnr_target_component_vta_distribution:MissingThresholdRows', ...
            'Missing threshold rows for %s.', componentId(g));
    end
    if any(diff(one.total_vta_volume_mm3) > 1e-6)
        error('mh_fiber_run_stnsnr_target_component_vta_distribution:ThresholdMonotonicityFailed', ...
            'VTA volume is not monotonic for %s.', componentId(g));
    end
end

required = {'cohort_target_component_vta_coverage_long.csv', ...
    'cohort_target_component_vta_coverage_wide.csv', ...
    'cohort_target_component_distribution_summary.csv', ...
    'cohort_target_component_contact_qc.csv', ...
    'cohort_target_component_generation_manifest.json', ...
    fullfile('figures', 'target_component_stacked_bar_thr0p20.png'), ...
    fullfile('figures', 'target_component_boxplot_thr0p20.png'), ...
    fullfile('figures', 'target_component_threshold_sensitivity.png')};
for i = 1:numel(required)
    must_be_file(fullfile(outputDir, required{i}), sprintf('target-component output %s', required{i}));
end
end

function value = join_numeric(values)
value = strjoin(string(values(:))', ';');
end

function label = threshold_label(value)
label = strrep(sprintf('%.2f', value), '.', 'p');
end

function path = efield_path(subjectDir, patientName, stimLabel, sideCode)
path = fullfile(subjectDir, 'stimulations', ea_nt(0), char(stimLabel), ...
    sprintf('%s_sim-efield_model-simbio_hemi-%s.nii', patientName, sideCode));
end

function path = atlas_path(atlasDir, sideCode, roi)
switch sideCode
    case 'L'
        hemi = 'lh';
    case 'R'
        hemi = 'rh';
    otherwise
        error('mh_fiber_run_stnsnr_target_component_vta_distribution:InvalidSide', ...
            'Invalid side: %s', sideCode);
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
        error('mh_fiber_run_stnsnr_target_component_vta_distribution:InvalidSide', ...
            'Invalid side: %s', sideCode);
end
end

function out = sanitize_label(value)
out = char(string(value));
out = regexprep(out, '\+', 'plus');
out = regexprep(out, '[^A-Za-z0-9_+-]+', '_');
out = regexprep(out, '_+', '_');
out = regexprep(out, '^_|_$', '');
end

function make_dir(path)
if ~isfolder(path)
    mkdir(path);
end
end

function must_be_file(path, description)
if ~isfile(path)
    error('mh_fiber_run_stnsnr_target_component_vta_distribution:MissingFile', ...
        'Missing %s: %s', description, path);
end
end

function must_be_folder(path, description)
if ~isfolder(path)
    error('mh_fiber_run_stnsnr_target_component_vta_distribution:MissingFolder', ...
        'Missing %s: %s', description, path);
end
end

function repoDir = resolve_repo_dir(pathInRepo)
repoDir = fileparts(pathInRepo);
while ~isempty(repoDir) && ~isfolder(fullfile(repoDir, 'ea_modules'))
    parent = fileparts(repoDir);
    if strcmp(parent, repoDir)
        break;
    end
    repoDir = parent;
end
if isempty(repoDir) || ~isfolder(fullfile(repoDir, 'ea_modules'))
    repoDir = pwd;
end
end

function write_json(path, data)
fid = fopen(path, 'w');
if fid < 0
    error('mh_fiber_run_stnsnr_target_component_vta_distribution:CannotWriteJson', ...
        'Cannot write JSON: %s', path);
end
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', jsonencode(data, PrettyPrint = true));
clear cleanup;
end
