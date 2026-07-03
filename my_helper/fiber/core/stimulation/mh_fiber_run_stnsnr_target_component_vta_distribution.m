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
parser = mh_fiber_stnsnr_add_vta_parser_params(parser);
parser.parse(varargin{:});
opts = parser.Results;

repoDir = char(string(opts.RepoDir));
if isempty(repoDir)
    repoDir = mh_util_resolve_repo_dir(mfilename('fullpath'));
end
subjectRoot = char(string(opts.SubjectRoot));
contactQcCsv = char(string(opts.ContactQcCsv));
atlasDir = char(string(opts.AtlasDir));
if isempty(atlasDir)
    atlasDir = fullfile(repoDir, 'templates', 'space', 'MNI152NLin2009bAsym', ...
        'atlases', 'Custom_Ewert_Zhang_Middlebrooks0.05');
end
outputDir = char(string(opts.OutputDir));

mh_util_must_be_folder(repoDir, 'repository directory');
mh_util_must_be_folder(subjectRoot, 'Lead-DBS subject root');
mh_util_must_be_file(contactQcCsv, 'cohort contact mapping QC CSV');
mh_util_must_be_folder(atlasDir, 'STN/SNr atlas directory');
regionSpec = mh_fiber_stnsnr_region_spec(atlasDir);
mh_coverage_verify_region_spec(regionSpec, 'mh_fiber_run_stnsnr_target_component_vta_distribution');

thresholdsVPerMm = unique(double(opts.ThresholdsVPerMm(:))', 'stable');
thresholdsVPerM = thresholdsVPerMm .* 1000;
mainThreshold = double(opts.MainThresholdVPerMm);
exportThreshold = min(thresholdsVPerMm);

mh_util_make_dir(outputDir);
mh_util_make_dir(fullfile(outputDir, 'figures'));
mh_util_make_dir(fullfile(outputDir, 'masks'));

contactTable = readtable(contactQcCsv, 'TextType', 'string');
contactTable = mh_fiber_stnsnr_normalize_contact_table(contactTable);
validate_contact_table(contactTable);

components = build_component_table(contactTable);
validate_component_table(components);

manifest = struct();
manifest.generated_at = char(datetime('now', 'TimeZone', 'local', 'Format', 'yyyy-MM-dd HH:mm:ss Z'));
manifest.repo_dir = repoDir;
manifest.subject_root = subjectRoot;
manifest.contact_qc_csv = contactQcCsv;
manifest.atlas_dir = atlasDir;
manifest.region_spec = regionSpec;
manifest.output_dir = outputDir;
manifest.thresholds_v_per_mm = thresholdsVPerMm;
manifest.thresholds_v_per_m = thresholdsVPerM;
manifest.main_threshold_v_per_mm = mainThreshold;
manifest.horn_export_threshold_v_per_mm = exportThreshold;
manifest.gray_matter_conductivity_s_per_m = 0.33;
manifest.white_matter_conductivity_s_per_m = 0.14;
manifest.analysis_unit = 'subject_id x phase x protocol x side x target';
manifest.component_count = height(components);
manifest = mh_fiber_stnsnr_add_vta_manifest_fields(manifest, opts);
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
    mh_util_must_be_folder(subjectDir, ['subject directory for ', subjectId]);

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
        efieldPaths, componentRows, component, componentOrigin, componentDirs, regionSpec, ...
        thresholdsVPerMm, thresholdsVPerM, mainThreshold, opts.OutputVoxelSizeMm, ...
        logical(opts.ForceOutputs));

    coverageRows = [coverageRows; componentCoverageRows]; %#ok<AGROW>
    componentQcRows(end+1, :) = component_qc_row(component, componentRows, componentOrigin, efieldPaths); %#ok<AGROW>
    manifest.components{end+1} = componentManifest;
end

coverageTable = rows_to_coverage_table(coverageRows);
componentQcTable = rows_to_component_qc_table(componentQcRows);
write_outputs(outputDir, coverageTable, componentQcTable, manifest, mainThreshold);
validate_outputs(outputDir, coverageTable, componentQcTable, thresholdsVPerMm, regionSpec);

result = struct();
result.outputDir = outputDir;
result.coverageLongCsv = fullfile(outputDir, 'cohort_target_component_vta_coverage_long.csv');
result.componentQcCsv = fullfile(outputDir, 'cohort_target_component_contact_qc.csv');
result.summaryCsv = fullfile(outputDir, 'cohort_target_component_distribution_summary.csv');
result.manifestJson = fullfile(outputDir, 'cohort_target_component_generation_manifest.json');
end

function validate_contact_table(contactTable)
required = {'subject_id', 'name_en', 'phase', 'protocol', 'target', 'side', ...
    'voltage', 'pulse_width', 'frequency', 'stimulation_pattern', ...
    'raw_contact', 'lead_contact', 'contact_side_rule_ok'};
mh_util_require_table_vars(contactTable, required, ...
    'mh_fiber_run_stnsnr_target_component_vta_distribution:MissingContactColumn', ...
    'Missing contact QC column: %s');
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
    componentId(i) = string(mh_fiber_stnsnr_target_component_id( ...
        components.subject_id(i), components.phase(i), components.protocol(i), ...
        components.side(i), components.target(i)));
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
    label = mh_fiber_stnsnr_vta_program_label( ...
        subjectId, phase, protocol, 'Pattern', 'continuous');
    efieldPaths(end+1, 1) = mh_fiber_vta_efield_path(subjectDir, patientName, label, sideCode);
elseif isscalar(patterns) && patterns == "alternating"
    alternatingRows = conditionRows(conditionRows.stimulation_pattern == "alternating", :);
    for i = 1:height(alternatingRows)
        one = alternatingRows(i, :);
        if one.side == string(sideCode) && one.target == string(target) && ...
                any(componentRows.raw_contact == one.raw_contact)
            label = mh_fiber_stnsnr_vta_program_label( ...
                subjectId, phase, protocol, ...
                'Pattern', 'alternating', ...
                'Side', one.side(1), ...
                'Target', one.target(1), ...
                'RawContact', one.raw_contact(1), ...
                'RowIndex', i);
            efieldPaths(end+1, 1) = mh_fiber_vta_efield_path( ...
                subjectDir, patientName, label, sideCode); %#ok<AGROW>
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
    mh_util_must_be_file(efieldPaths{i}, sprintf('observed e-field for %s', char(component.component_id)));
end
end

function efieldPaths = generate_component_efield(componentRows, subjectDir, patientName, ...
    component, exportThresholdVPerMm, opts)
sideCode = char(component.side);
componentId = char(component.component_id);
label = mh_fiber_stnsnr_target_component_vta_label(componentId);
modelKey = char(string(opts.VtaModelKey));
cfg = mh_fiber_default_config(subjectDir, label);
cfg.forceRecomputeVTA = logical(opts.ForceVta);
cfg.vta.modelKey = modelKey;
cfg.vta.model = mh_fiber_model_name(modelKey);
cfg.vta.gmAtlas = char(string(opts.VtaGmAtlas));
cfg = mh_vta_apply_execution_options(cfg, opts);
stimSpec = mh_fiber_stnsnr_stimspec_from_table(componentRows, label, ...
    'Model', modelKey);
[taskResults, ~, cfg] = mh_vta_run_stim_spec_tasks( ...
    cfg, stimSpec, {sideCode}, ...
    'ModelKey', modelKey, ...
    'Force', logical(opts.ForceVta), ...
    'OutputSpaces', {'mni'}, ...
    'ExportThresholdVPerMm', exportThresholdVPerMm, ...
    'GmAtlas', char(string(opts.VtaGmAtlas)), ...
    'UseAtlas', true, ...
    'RemoveElectrode', true);
taskResult = taskResults(1);

efieldPath = taskResult.efield_mni;
mh_util_must_be_file(efieldPath, sprintf('target-component e-field for %s', componentId));
efieldPaths = {efieldPath};

if ~strcmp(patientName, cfg.patientName)
    error('mh_fiber_run_stnsnr_target_component_vta_distribution:PatientNameMismatch', ...
        'Unexpected patient name mismatch for %s.', componentId);
end
end

function [coverageRows, componentManifest] = analyze_component_coverage( ...
    efieldPaths, componentRows, component, componentOrigin, componentDirs, regionSpec, ...
    thresholdsVPerMm, thresholdsVPerM, mainThreshold, outputVoxelSize, forceOutputs)
coverageRows = {};
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
ref = mh_coverage_reference_grid(efieldPaths, outputVoxelSize, ...
    'ErrorId', 'mh_fiber_run_stnsnr_target_component_vta_distribution:ReferenceGridTooLarge');
regionMasks = mh_coverage_sample_region_masks(regionSpec, sideCode, ref);
sampledEfields = mh_coverage_sample_efields_to_grid(efieldPaths, ref);
componentPattern = mh_fiber_stnsnr_stimulation_pattern_label(componentRows, ...
    'Column', 'stimulation_pattern');

for t = 1:numel(thresholdsVPerM)
    thresholdVPerMm = thresholdsVPerMm(t);
    thresholdVPerM = thresholdsVPerM(t);
    thresholdLabel = mh_coverage_threshold_label(thresholdVPerMm);
    thresholdResult = mh_coverage_threshold_sampled_efields( ...
        sampledEfields, ref, thresholdVPerM, regionMasks, ...
        'ErrorId', 'mh_fiber_run_stnsnr_target_component_vta_distribution:CategorySumMismatch');
    vtaMask = thresholdResult.vta_mask;
    overlapMask = thresholdResult.overlap_mask;
    categories = thresholdResult.categories;
    totalVoxels = thresholdResult.total_voxels;
    paths = write_component_masks(ref, vtaMask, categories, overlapMask, componentDirs, ...
        component, thresholdLabel, forceOutputs);
    categoryRows = thresholdResult.category_rows;
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
            mh_util_join_values(componentRows.raw_contact), ...
            mh_util_join_values(componentRows.lead_contact), ...
            mh_util_join_values(componentRows.voltage), ...
            mh_util_join_values(componentRows.pulse_width), ...
            mh_util_join_values(componentRows.frequency), componentPattern, ...
            mh_util_join_values(efieldPaths), paths.vta, paths.category, paths.overlap};
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

function paths = write_component_masks(ref, vtaMask, categories, overlapMask, componentDirs, ...
    component, thresholdLabel, forceOutputs)
base = mh_fiber_stnsnr_vta_artifact_base(component.patient_name, ...
    component.phase, component.protocol, component.side, thresholdLabel, ...
    'Target', component.target);
paths = mh_coverage_write_standard_masks(ref, componentDirs.masks, base, ...
    vtaMask, categories.categoryImg, overlapMask, ...
    'Force', forceOutputs, ...
    'VtaDescription', 'stnsnr target component vta', ...
    'CategoryDescription', 'stnsnr target component category', ...
    'OverlapDescription', 'stnsnr target component program overlap');
end

function write_component_figure(componentDirs, component, thresholdLabel, categoryRows)
base = mh_fiber_stnsnr_vta_artifact_base(component.patient_name, ...
    component.phase, component.protocol, component.side, thresholdLabel, ...
    'Target', component.target);
titleText = sprintf('%s %s %s %s target %s %s', component.patient_name, ...
    component.phase, component.protocol, component.side, component.target, thresholdLabel);
mh_coverage_write_composition_figure(componentDirs.figures, base, categoryRows, titleText);
end

function dirs = prepare_component_dirs(outputDir, component)
targetKey = mh_fiber_stnsnr_condition_key(component.phase, component.protocol, ...
    'Target', component.target);
dirs = struct();
dirs.masks = fullfile(outputDir, 'masks', targetKey);
dirs.figures = fullfile(outputDir, 'figures', targetKey);
mh_util_make_dir(dirs.masks);
mh_util_make_dir(dirs.figures);
end

function row = component_qc_row(component, componentRows, componentOrigin, efieldPaths)
row = {char(component.component_id), char(component.subject_id), char(component.patient_name), ...
    char(component.phase), char(component.protocol), char(component.side), char(component.target), ...
    componentOrigin, height(componentRows), mh_util_join_values(componentRows.raw_contact), ...
    mh_util_join_values(componentRows.lead_contact), mh_util_join_values(componentRows.voltage), ...
    mh_util_join_values(componentRows.pulse_width), mh_util_join_values(componentRows.frequency), ...
    mh_fiber_stnsnr_stimulation_pattern_label(componentRows, 'Column', 'stimulation_pattern'), ...
    mh_util_join_values(efieldPaths)};
end

function tableOut = rows_to_coverage_table(rows)
variableNames = { ...
    'component_id', 'subject_id', 'patient_name', 'phase', 'protocol', 'side', ...
    'target', 'component_origin', 'threshold_v_per_mm', 'threshold_v_per_m', ...
    'category', 'voxel_count', 'volume_mm3', 'percent_total_vta', ...
    'percent_anatomical_compartment', 'total_vta_voxels', 'total_vta_volume_mm3', ...
    'program_count', 'program_overlap_voxels', 'program_overlap_volume_mm3', ...
    'raw_contacts', 'lead_contacts', 'voltages', 'pulse_widths', 'frequencies', ...
    'stimulation_pattern', 'efield_paths', 'vta_mask_path', 'category_mask_path', ...
    'program_overlap_mask_path'};
stringVars = {'component_id', 'subject_id', 'patient_name', 'phase', 'protocol', ...
    'side', 'target', 'component_origin', 'category', 'raw_contacts', 'lead_contacts', ...
    'voltages', 'pulse_widths', 'frequencies', 'stimulation_pattern', 'efield_paths', ...
    'vta_mask_path', 'category_mask_path', 'program_overlap_mask_path'};
tableOut = mh_util_cell_rows_to_table(rows, variableNames, stringVars);
end

function tableOut = rows_to_component_qc_table(rows)
variableNames = { ...
    'component_id', 'subject_id', 'patient_name', 'phase', 'protocol', 'side', ...
    'target', 'component_origin', 'n_contacts', 'raw_contacts', 'lead_contacts', ...
    'voltages', 'pulse_widths', 'frequencies', 'stimulation_pattern', 'efield_paths'};
stringVars = {'component_id', 'subject_id', 'patient_name', 'phase', 'protocol', ...
    'side', 'target', 'component_origin', 'raw_contacts', 'lead_contacts', ...
    'voltages', 'pulse_widths', 'frequencies', 'stimulation_pattern', 'efield_paths'};
tableOut = mh_util_cell_rows_to_table(rows, variableNames, stringVars);
end

function write_outputs(outputDir, coverageTable, componentQcTable, manifest, mainThreshold)
writetable(coverageTable, fullfile(outputDir, 'cohort_target_component_vta_coverage_long.csv'));
keyVars = {'component_id', 'subject_id', 'patient_name', 'phase', 'protocol', ...
    'side', 'target', 'component_origin', 'threshold_v_per_mm', 'threshold_v_per_m', ...
    'total_vta_voxels', 'total_vta_volume_mm3', 'program_count', ...
    'program_overlap_voxels', 'program_overlap_volume_mm3', 'raw_contacts', ...
    'lead_contacts', 'voltages', 'pulse_widths', 'frequencies', 'stimulation_pattern'};
wide = mh_coverage_category_wide_table(coverageTable, keyVars);
writetable(wide, fullfile(outputDir, 'cohort_target_component_vta_coverage_wide.csv'));
summary = summarize_distribution(coverageTable);
writetable(summary, fullfile(outputDir, 'cohort_target_component_distribution_summary.csv'));
writetable(componentQcTable, fullfile(outputDir, 'cohort_target_component_contact_qc.csv'));
mh_util_write_json(fullfile(outputDir, 'cohort_target_component_generation_manifest.json'), manifest);
write_summary_figures(outputDir, coverageTable, mainThreshold);
end

function summary = summarize_distribution(coverageTable)
summary = mh_coverage_category_summary_table(coverageTable, ...
    {'target', 'phase', 'protocol'}, ...
    'IncludeCounts', true, ...
    'IncludeIqr', true, ...
    'IncludeMinMax', true);
end

function write_summary_figures(outputDir, coverageTable, mainThreshold)
figureDir = fullfile(outputDir, 'figures');
mh_util_make_dir(figureDir);
mainRows = coverageTable(abs(coverageTable.threshold_v_per_mm - mainThreshold) < 1e-9, :);
summary = summarize_distribution(mainRows);

[targets, categories, matrix] = mh_coverage_category_matrix( ...
    summary.target, summary.category, summary.mean_percent_total_vta);
fig = mh_viz_stacked_share_bar(targets, categories, matrix, ...
    'Title', sprintf('Target-component VTA coverage share at %.2f V/mm', mainThreshold), ...
    'OutputPath', fullfile(figureDir, 'target_component_stacked_bar_thr0p20.png'));
close(fig);

fig = mh_viz_box(strcat(mainRows.target, " / ", mainRows.category), mainRows.volume_mm3, ...
    'YLabel', 'Volume (mm3)', ...
    'Title', sprintf('Target-component category volumes at %.2f V/mm', mainThreshold), ...
    'OutputPath', fullfile(figureDir, 'target_component_boxplot_thr0p20.png'));
close(fig);

totalRows = unique(coverageTable(:, {'component_id', 'target', 'threshold_v_per_mm', ...
    'total_vta_volume_mm3'}), 'rows');
plotTable = mh_coverage_threshold_trend_table(totalRows, {'target'});
fig = mh_viz_trend_line(plotTable.threshold_v_per_mm, plotTable.mean_total_vta_volume_mm3, ...
    'Group', plotTable.target, ...
    'XLabel', 'Threshold (V/mm)', ...
    'YLabel', 'Mean total VTA volume (mm3)', ...
    'Title', 'Target-component threshold sensitivity', ...
    'OutputPath', fullfile(figureDir, 'target_component_threshold_sensitivity.png'));
close(fig);
end

function validate_outputs(outputDir, coverageTable, componentQcTable, thresholdsVPerMm, regionSpec)
if height(componentQcTable) ~= 190
    error('mh_fiber_run_stnsnr_target_component_vta_distribution:ComponentQcRowCount', ...
        'Expected 190 component QC rows, found %d.', height(componentQcTable));
end
expectedCategoryRows = mh_coverage_region_category_count(regionSpec);
expectedCoverageRows = height(componentQcTable) * numel(thresholdsVPerMm) * expectedCategoryRows;
if height(coverageTable) ~= expectedCoverageRows
    error('mh_fiber_run_stnsnr_target_component_vta_distribution:CoverageRowCount', ...
        'Expected %d coverage rows, found %d.', expectedCoverageRows, height(coverageTable));
end
stnCount = nnz(componentQcTable.target == "STN");
snrCount = nnz(componentQcTable.target == "SNr");
if stnCount ~= 126 || snrCount ~= 64
    error('mh_fiber_run_stnsnr_target_component_vta_distribution:OutputTargetCount', ...
        'Expected 126 STN and 64 SNr rows, found %d STN and %d SNr.', stnCount, snrCount);
end

mh_coverage_validate_category_totals(coverageTable, ...
    {'component_id', 'threshold_v_per_mm'}, expectedCategoryRows, ...
    'CountErrorId', 'mh_fiber_run_stnsnr_target_component_vta_distribution:MissingCategoryRows', ...
    'CountMessage', sprintf('Expected %d category rows for %%s at %%.2f.', expectedCategoryRows), ...
    'SumErrorId', 'mh_fiber_run_stnsnr_target_component_vta_distribution:CategoryVoxelMismatch', ...
    'SumMessage', 'Category voxel count does not equal total VTA voxel count.');

totalRows = unique(coverageTable(:, {'component_id', 'threshold_v_per_mm', ...
    'total_vta_volume_mm3'}), 'rows');
mh_coverage_validate_threshold_series(totalRows, {'component_id'}, thresholdsVPerMm, ...
    'MissingErrorId', 'mh_fiber_run_stnsnr_target_component_vta_distribution:MissingThresholdRows', ...
    'MissingMessage', 'Missing threshold rows for %s.', ...
    'MonotonicErrorId', 'mh_fiber_run_stnsnr_target_component_vta_distribution:ThresholdMonotonicityFailed', ...
    'MonotonicMessage', 'VTA volume is not monotonic for %s.');

required = {'cohort_target_component_vta_coverage_long.csv', ...
    'cohort_target_component_vta_coverage_wide.csv', ...
    'cohort_target_component_distribution_summary.csv', ...
    'cohort_target_component_contact_qc.csv', ...
    'cohort_target_component_generation_manifest.json', ...
    fullfile('figures', 'target_component_stacked_bar_thr0p20.png'), ...
    fullfile('figures', 'target_component_boxplot_thr0p20.png'), ...
    fullfile('figures', 'target_component_threshold_sensitivity.png')};
mh_coverage_require_output_files(outputDir, required, ...
    'DescriptionPrefix', 'target-component output ');
end
