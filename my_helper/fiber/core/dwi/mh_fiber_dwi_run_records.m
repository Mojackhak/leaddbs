function record = mh_fiber_dwi_run_records(action, varargin)
% Start or finish one immutable BIDS DWI preprocessing run record.

action = lower(strtrim(char(string(action))));
switch action
    case 'start'
        record = start_record(varargin{:});
    case 'finish'
        record = finish_record(varargin{:});
    otherwise
        error('mh_fiber_dwi_run_records:InvalidAction', ...
            'Action must be start or finish.');
end
end

function record = start_record(source, config, manifest, mode)
if ~isstruct(source) || ~isstruct(config) || ~istable(manifest)
    error('mh_fiber_dwi_run_records:InvalidInput', ...
        'Start requires source/config structs and a manifest table.');
end
mode = lower(strtrim(char(string(mode))));
runRoot = fullfile(config.project.study_root, 'derivatives', 'leaddbs', ...
    'import_logs', 'dwi_runs');
mh_util_make_dir(runRoot);
[runId, runDir] = unique_run_directory(runRoot, mode);
subjectsDir = fullfile(runDir, 'subjects');
mh_util_make_dir(subjectsDir);

sourcePath = fullfile(runDir, 'config_source.yaml');
if isfield(source, 'path') && ~isempty(char(string(source.path))) && isfile(source.path)
    atomic_copy(char(string(source.path)), sourcePath);
else
    atomic_write_yaml(sourcePath, config);
end
resolvedPath = fullfile(runDir, 'config_resolved.json');
atomic_write_json(resolvedPath, config);
manifestPath = fullfile(runDir, 'job_manifest.csv');
atomic_write_table(manifestPath, manifest);

record = struct();
record.runId = runId;
record.mode = mode;
record.runRoot = runRoot;
record.runDir = runDir;
record.sourceConfigPath = sourcePath;
record.resolvedConfigPath = resolvedPath;
record.manifestPath = manifestPath;
record.statusPath = fullfile(runDir, 'status.csv');
record.subjectsDir = subjectsDir;
end

function record = finish_record(record, status)
if ~isstruct(record) || ~isfield(record, 'runDir') || ~isfolder(record.runDir)
    error('mh_fiber_dwi_run_records:InvalidRecord', ...
        'Finish requires a record returned by the start action.');
end
if isstruct(status)
    status = struct2table(status, 'AsArray', true);
end
if ~istable(status) || ~ismember('subject', status.Properties.VariableNames)
    error('mh_fiber_dwi_run_records:InvalidStatus', ...
        'Status must be a table with a subject column.');
end
atomic_write_table(record.statusPath, status);
for i = 1:height(status)
    subjectId = table_text_value(status, 'subject', i);
    safeSubject = regexprep(subjectId, '[^A-Za-z0-9._-]', '_');
    subjectPath = fullfile(record.subjectsDir, ...
        [safeSubject, '_dwi_preprocessing_qc.json']);
    row = table2struct(status(i, :));
    atomic_write_json(subjectPath, row);
end
end

function [runId, runDir] = unique_run_directory(runRoot, mode)
stamp = char(datetime('now', 'Format', 'yyyyMMdd_HHmmss_SSS'));
base = [stamp, '_', regexprep(mode, '[^A-Za-z0-9._-]', '_')];
runId = base;
runDir = fullfile(runRoot, runId);
suffix = 1;
while isfolder(runDir)
    runId = sprintf('%s_%02d', base, suffix);
    runDir = fullfile(runRoot, runId);
    suffix = suffix + 1;
end
mh_util_make_dir(runDir);
end

function value = table_text_value(T, variable, row)
column = T.(variable);
if iscell(column)
    value = char(string(column{row}));
else
    value = char(string(column(row)));
end
end

function atomic_copy(source, target)
tempPath = [tempname(fileparts(target)), '.yaml'];
cleanupObj = onCleanup(@() delete_if_file(tempPath));
[ok, message] = copyfile(source, tempPath, 'f');
if ~ok
    error('mh_fiber_dwi_run_records:WriteFailed', ...
        'Could not copy source configuration: %s', message);
end
atomic_move(tempPath, target);
end

function atomic_write_json(target, value)
tempPath = [tempname(fileparts(target)), '.json'];
cleanupObj = onCleanup(@() delete_if_file(tempPath));
mh_util_write_json(tempPath, value, 'mh_fiber_dwi_run_records:WriteFailed');
atomic_move(tempPath, target);
end

function atomic_write_table(target, value)
tempPath = [tempname(fileparts(target)), '.csv'];
cleanupObj = onCleanup(@() delete_if_file(tempPath));
writetable(value, tempPath);
atomic_move(tempPath, target);
end

function atomic_write_yaml(target, config)
tempPath = [tempname(fileparts(target)), '.yaml'];
cleanupObj = onCleanup(@() delete_if_file(tempPath));
write_config_yaml(tempPath, config);
atomic_move(tempPath, target);
end

function atomic_move(source, target)
[ok, message] = movefile(source, target, 'f');
if ~ok
    error('mh_fiber_dwi_run_records:WriteFailed', ...
        'Could not finalize run record %s: %s', target, message);
end
end

function delete_if_file(path)
if isfile(path)
    delete(path);
end
end

function write_config_yaml(path, config)
fid = fopen(path, 'w');
if fid < 0
    error('mh_fiber_dwi_run_records:WriteFailed', ...
        'Could not write generated YAML configuration: %s', path);
end
cleanupObj = onCleanup(@() fclose(fid));

fprintf(fid, 'schema_version: %d\n\n', config.schema_version);
fprintf(fid, 'project:\n');
fprintf(fid, '  name: %s\n', yaml_text(config.project.name));
fprintf(fid, '  study_root: %s\n', yaml_text(config.project.study_root));
fprintf(fid, '  session: %s\n\n', yaml_text(config.project.session));
fprintf(fid, 'subjects:\n');
fprintf(fid, '  mode: %s\n', config.subjects.mode);
if strcmp(config.subjects.mode, 'explicit')
    fprintf(fid, '  ids:\n');
    for i = 1:numel(config.subjects.ids)
        fprintf(fid, '    - %s\n', yaml_text(config.subjects.ids{i}));
    end
end
fprintf(fid, '\n');
fprintf(fid, 'dwi:\n');
fprintf(fid, '  distortion_correction: %s\n', config.dwi.distortion_correction);
fprintf(fid, '  phase_encoding_vector: [%g, %g, %g]\n', ...
    config.dwi.phase_encoding_vector);
fprintf(fid, '  b0_reference:\n');
fprintf(fid, '    strategy: %s\n', config.dwi.b0_reference.strategy);
fprintf(fid, '    threshold: %.12g\n', config.dwi.b0_reference.threshold);
fprintf(fid, '  total_readout_time:\n');
fprintf(fid, '    strategy: %s\n', config.dwi.total_readout_time.strategy);
fprintf(fid, '    seconds: %.12g\n\n', config.dwi.total_readout_time.seconds);
fprintf(fid, 'anatomy:\n');
fprintf(fid, '  synb0_modality: %s\n', config.anatomy.synb0_modality);
fprintf(fid, '  coregistration_anchor: %s\n', config.anatomy.coregistration_anchor);
fprintf(fid, '  allow_anchor_fallback: %s\n\n', yaml_bool(config.anatomy.allow_anchor_fallback));
fprintf(fid, 'lead_dbs:\n');
fprintf(fid, '  run_coregistration: %s\n', yaml_bool(config.lead_dbs.run_coregistration));
fprintf(fid, '  coregistration_method: %s\n\n', yaml_text(config.lead_dbs.coregistration_method));
fprintf(fid, 'processing:\n');
fprintf(fid, '  generate_optional_dwi_qc: %s\n\n', ...
    yaml_bool(config.processing.generate_optional_dwi_qc));
fprintf(fid, 'execution:\n');
fprintf(fid, '  force: %s\n', yaml_bool(config.execution.force));
fprintf(fid, '  parallel: %s\n', yaml_bool(config.execution.parallel));
fprintf(fid, '  parallel_workers: %d\n', config.execution.parallel_workers);
fprintf(fid, '  max_concurrent_synb0: %d\n', config.execution.max_concurrent_synb0);
fprintf(fid, '  synb0_min_memory_gb: %.12g\n\n', config.execution.synb0_min_memory_gb);
fprintf(fid, 'runtime:\n');
fprintf(fid, '  freesurfer_license: %s\n', yaml_text(config.runtime.freesurfer_license));
fprintf(fid, '  synb0:\n');
fprintf(fid, '    container_engine: %s\n', yaml_text(config.runtime.synb0.container_engine));
fprintf(fid, '    container_image: %s\n', yaml_text(config.runtime.synb0.container_image));
fprintf(fid, '    work_root: %s\n', yaml_text(config.runtime.synb0.work_root));
end

function value = yaml_text(value)
value = jsonencode(char(string(value)));
end

function value = yaml_bool(value)
if value
    value = 'true';
else
    value = 'false';
end
end
