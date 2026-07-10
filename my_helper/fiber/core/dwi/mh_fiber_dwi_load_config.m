function [config, source] = mh_fiber_dwi_load_config(configPath, overrides)
% Load and strictly validate one BIDS/Lead-DBS DWI YAML configuration.

if nargin < 1
    configPath = '';
end
if nargin < 2 || isempty(overrides)
    overrides = struct();
end
configPath = char(string(configPath));
if ~isstruct(overrides) || ~isscalar(overrides)
    error('mh_fiber_dwi_load_config:InvalidOverrides', ...
        'Runtime configuration overrides must be a scalar struct.');
end

schema = config_schema();
config = default_config();
source = struct('path', configPath, 'provided', ~isempty(configPath));

if ~isempty(configPath)
    if ~isfile(configPath)
        error('mh_fiber_dwi_load_config:MissingConfig', ...
            'DWI configuration file does not exist: %s', configPath);
    end
    raw = readyaml(configPath);
    if ~isstruct(raw) || ~isscalar(raw)
        error('mh_fiber_dwi_load_config:InvalidConfig', ...
            'DWI configuration must contain one YAML mapping at its root.');
    end
    reject_unknown_fields(raw, schema, '');
    config = merge_struct(config, raw);
end

reject_unknown_fields(overrides, schema, '');
config = merge_struct(config, overrides);
if isfield(overrides, 'subjects') && isstruct(overrides.subjects) && ...
        isfield(overrides.subjects, 'mode') && ...
        strcmpi(char(string(overrides.subjects.mode)), 'auto') && ...
        ~isfield(overrides.subjects, 'ids') && isfield(config.subjects, 'ids')
    config.subjects = rmfield(config.subjects, 'ids');
end
config = normalize_config(config);
end

function schema = config_schema()
leaf = true;
schema = struct();
schema.schema_version = leaf;
schema.project = struct('name', leaf, 'study_root', leaf, 'session', leaf);
schema.subjects = struct('mode', leaf, 'ids', leaf);
schema.dwi = struct( ...
    'distortion_correction', leaf, ...
    'phase_encoding_vector', leaf, ...
    'total_readout_time', struct('strategy', leaf, 'seconds', leaf));
schema.anatomy = struct( ...
    'synb0_modality', leaf, ...
    'coregistration_anchor', leaf, ...
    'allow_anchor_fallback', leaf);
schema.lead_dbs = struct( ...
    'run_coregistration', leaf, ...
    'coregistration_method', leaf);
schema.processing = struct('generate_optional_dwi_qc', leaf);
schema.execution = struct( ...
    'force', leaf, ...
    'parallel', leaf, ...
    'parallel_workers', leaf, ...
    'max_concurrent_synb0', leaf, ...
    'synb0_min_memory_gb', leaf);
schema.runtime = struct( ...
    'freesurfer_license', leaf, ...
    'synb0', struct( ...
    'container_engine', leaf, ...
    'container_image', leaf, ...
    'work_root', leaf));
end

function config = default_config()
config = struct();
config.schema_version = 1;
config.project = struct('name', '', 'study_root', '', 'session', 'preop');
config.subjects = struct('mode', 'auto');
config.dwi = struct( ...
    'distortion_correction', 'synb0', ...
    'phase_encoding_vector', [0 1 0], ...
    'total_readout_time', struct( ...
    'strategy', 'json_then_fallback', 'seconds', 0.05));
config.anatomy = struct( ...
    'synb0_modality', 'T1w', ...
    'coregistration_anchor', 'T2w', ...
    'allow_anchor_fallback', false);
config.lead_dbs = struct( ...
    'run_coregistration', false, ...
    'coregistration_method', 'SPM');
config.processing = struct('generate_optional_dwi_qc', true);
config.execution = struct( ...
    'force', false, ...
    'parallel', false, ...
    'parallel_workers', 1, ...
    'max_concurrent_synb0', 1, ...
    'synb0_min_memory_gb', 12);
config.runtime = struct( ...
    'freesurfer_license', '/Applications/freesurfer/8.2.0/license.txt', ...
    'synb0', struct( ...
    'container_engine', 'auto', ...
    'container_image', 'leonyichencai/synb0-disco:v3.1', ...
    'work_root', fullfile(getenv('HOME'), 'Library', 'Caches', ...
    'leaddbs', 'synb0_work')));
end

function reject_unknown_fields(value, schema, path)
if ~isstruct(value) || ~isscalar(value)
    return;
end
names = fieldnames(value);
allowed = fieldnames(schema);
for i = 1:numel(names)
    name = names{i};
    fieldPath = join_path(path, name);
    if ~ismember(name, allowed)
        error('mh_fiber_dwi_load_config:UnknownField', ...
            'Unknown DWI configuration field: %s', fieldPath);
    end
    childSchema = schema.(name);
    if isstruct(childSchema)
        child = value.(name);
        if ~isstruct(child) || ~isscalar(child)
            error('mh_fiber_dwi_load_config:InvalidType', ...
                'Configuration field %s must be a mapping.', fieldPath);
        end
        reject_unknown_fields(child, childSchema, fieldPath);
    end
end
end

function path = join_path(parent, child)
if isempty(parent)
    path = child;
else
    path = [parent, '.', child];
end
end

function out = merge_struct(base, override)
out = base;
names = fieldnames(override);
for i = 1:numel(names)
    name = names{i};
    value = override.(name);
    if isfield(out, name) && isstruct(out.(name)) && isscalar(out.(name)) && ...
            isstruct(value) && isscalar(value)
        out.(name) = merge_struct(out.(name), value);
    else
        out.(name) = value;
    end
end
end

function config = normalize_config(config)
config.schema_version = require_scalar_number(config.schema_version, 'schema_version');
if config.schema_version ~= 1
    error('mh_fiber_dwi_load_config:UnsupportedSchemaVersion', ...
        'Unsupported DWI configuration schema_version: %g', config.schema_version);
end

config.project.name = require_text(config.project.name, 'project.name', false);
config.project.study_root = require_text(config.project.study_root, 'project.study_root', false);
config.project.session = normalize_bids_label(config.project.session, 'project.session', 'ses-');
config.subjects = normalize_subjects(config.subjects);

config.dwi.distortion_correction = require_enum( ...
    config.dwi.distortion_correction, {'none', 'synb0'}, ...
    'dwi.distortion_correction');
config.dwi.phase_encoding_vector = normalize_phase_encoding( ...
    config.dwi.phase_encoding_vector);
config.dwi.total_readout_time.strategy = require_enum( ...
    config.dwi.total_readout_time.strategy, {'json_then_fallback', 'fixed'}, ...
    'dwi.total_readout_time.strategy');
config.dwi.total_readout_time.seconds = require_scalar_number( ...
    config.dwi.total_readout_time.seconds, 'dwi.total_readout_time.seconds');
if config.dwi.total_readout_time.seconds <= 0
    error('mh_fiber_dwi_load_config:InvalidReadoutTime', ...
        'dwi.total_readout_time.seconds must be positive.');
end

config.anatomy.synb0_modality = normalize_modality( ...
    config.anatomy.synb0_modality, 'anatomy.synb0_modality');
if ~strcmp(config.anatomy.synb0_modality, 'T1w')
    error('mh_fiber_dwi_load_config:InvalidEnum', ...
        'anatomy.synb0_modality must be T1w.');
end
config.anatomy.coregistration_anchor = normalize_modality( ...
    config.anatomy.coregistration_anchor, 'anatomy.coregistration_anchor');
config.anatomy.allow_anchor_fallback = require_logical( ...
    config.anatomy.allow_anchor_fallback, 'anatomy.allow_anchor_fallback');

config.lead_dbs.run_coregistration = require_logical( ...
    config.lead_dbs.run_coregistration, 'lead_dbs.run_coregistration');
config.lead_dbs.coregistration_method = normalize_coregistration_method( ...
    config.lead_dbs.coregistration_method);
config.processing.generate_optional_dwi_qc = require_logical( ...
    config.processing.generate_optional_dwi_qc, ...
    'processing.generate_optional_dwi_qc');

config.execution.force = require_logical(config.execution.force, 'execution.force');
config.execution.parallel = require_logical(config.execution.parallel, 'execution.parallel');
config.execution.parallel_workers = require_positive_integer( ...
    config.execution.parallel_workers, 'execution.parallel_workers');
config.execution.max_concurrent_synb0 = require_positive_integer( ...
    config.execution.max_concurrent_synb0, 'execution.max_concurrent_synb0');
config.execution.synb0_min_memory_gb = require_scalar_number( ...
    config.execution.synb0_min_memory_gb, 'execution.synb0_min_memory_gb');
if config.execution.synb0_min_memory_gb < 0
    error('mh_fiber_dwi_load_config:InvalidValue', ...
        'execution.synb0_min_memory_gb must be nonnegative.');
end

config.runtime.freesurfer_license = require_text( ...
    config.runtime.freesurfer_license, 'runtime.freesurfer_license', true);
config.runtime.synb0.container_engine = require_text( ...
    config.runtime.synb0.container_engine, 'runtime.synb0.container_engine', false);
config.runtime.synb0.container_image = require_text( ...
    config.runtime.synb0.container_image, 'runtime.synb0.container_image', false);
config.runtime.synb0.work_root = require_text( ...
    config.runtime.synb0.work_root, 'runtime.synb0.work_root', true);
end

function subjects = normalize_subjects(subjects)
mode = lower(strtrim(require_text(subjects.mode, 'subjects.mode', false)));
if ~ismember(mode, {'auto', 'explicit'})
    error('mh_fiber_dwi_load_config:InvalidSubjects', ...
        'subjects.mode must be auto or explicit.');
end
subjects.mode = mode;
if strcmp(mode, 'auto')
    if isfield(subjects, 'ids')
        error('mh_fiber_dwi_load_config:InvalidSubjects', ...
            'subjects.ids is not allowed when subjects.mode is auto.');
    end
    return;
end
if ~isfield(subjects, 'ids')
    error('mh_fiber_dwi_load_config:InvalidSubjects', ...
        'subjects.ids is required when subjects.mode is explicit.');
end
ids = normalize_text_list(subjects.ids, 'subjects.ids');
if isempty(ids)
    error('mh_fiber_dwi_load_config:InvalidSubjects', ...
        'subjects.ids must be nonempty when subjects.mode is explicit.');
end
for i = 1:numel(ids)
    ids{i} = normalize_bids_label(ids{i}, sprintf('subjects.ids{%d}', i), 'sub-');
end
subjects.ids = unique(ids, 'stable');
end

function ids = normalize_text_list(value, fieldName)
if ischar(value) || (isstring(value) && isscalar(value))
    ids = {char(string(value))};
elseif isstring(value)
    ids = cellstr(value(:)');
elseif iscell(value)
    ids = cell(size(value));
    for i = 1:numel(value)
        if ~(ischar(value{i}) || (isstring(value{i}) && isscalar(value{i})))
            error('mh_fiber_dwi_load_config:InvalidType', ...
                '%s must contain text values.', fieldName);
        end
        ids{i} = char(string(value{i}));
    end
    ids = reshape(ids, 1, []);
else
    error('mh_fiber_dwi_load_config:InvalidType', ...
        '%s must be a YAML sequence of text values.', fieldName);
end
end

function value = normalize_phase_encoding(value)
if ~isnumeric(value) || numel(value) ~= 3 || any(~isfinite(value(:)))
    error('mh_fiber_dwi_load_config:InvalidPhaseEncodingVector', ...
        'dwi.phase_encoding_vector must contain three finite numeric values.');
end
value = double(value(:)');
if any(~ismember(value, [-1 0 1])) || sum(abs(value) == 1) ~= 1
    error('mh_fiber_dwi_load_config:InvalidPhaseEncodingVector', ...
        ['dwi.phase_encoding_vector must contain exactly one signed unit ', ...
        'axis and two zeros.']);
end
end

function value = normalize_modality(value, fieldName)
value = lower(require_text(value, fieldName, false));
switch value
    case {'t1', 't1w'}
        value = 'T1w';
    case {'t2', 't2w'}
        value = 'T2w';
    otherwise
        error('mh_fiber_dwi_load_config:InvalidEnum', ...
            '%s must be T1w or T2w.', fieldName);
end
end

function value = normalize_coregistration_method(value)
raw = lower(strtrim(require_text(value, 'lead_dbs.coregistration_method', false)));
switch raw
    case {'spm', 'spm (friston 2007)'}
        value = 'SPM';
    case {'ants', 'ants (avants 2008)'}
        value = 'ANTs';
    case {'hybrid spm & ants', 'hybridspmants', 'hybrid spm and ants'}
        value = 'Hybrid SPM & ANTs';
    case {'flirt bbr', 'flirtbbr', 'bbr', 'fsl flirt bbr'}
        value = 'FLIRT BBR';
    otherwise
        error('mh_fiber_dwi_load_config:InvalidEnum', ...
            'Unsupported lead_dbs.coregistration_method: %s', raw);
end
end

function value = require_enum(value, allowed, fieldName)
value = lower(strtrim(require_text(value, fieldName, false)));
if ~ismember(value, allowed)
    error('mh_fiber_dwi_load_config:InvalidEnum', ...
        '%s must be one of: %s.', fieldName, strjoin(allowed, ', '));
end
end

function value = require_text(value, fieldName, allowEmpty)
if ~(ischar(value) || (isstring(value) && isscalar(value)))
    error('mh_fiber_dwi_load_config:InvalidType', ...
        '%s must be text.', fieldName);
end
value = strtrim(char(string(value)));
if ~allowEmpty && isempty(value)
    error('mh_fiber_dwi_load_config:InvalidValue', ...
        '%s must not be empty.', fieldName);
end
end

function value = normalize_bids_label(value, fieldName, disallowedPrefix)
value = require_text(value, fieldName, false);
if startsWith(value, disallowedPrefix)
    if strcmp(disallowedPrefix, 'sub-')
        error('mh_fiber_dwi_load_config:InvalidSubjectId', ...
            '%s must not include the sub- prefix: %s', fieldName, value);
    end
    error('mh_fiber_dwi_load_config:InvalidValue', ...
        '%s must not include the %s prefix.', fieldName, disallowedPrefix);
end
if isempty(regexp(value, '^[A-Za-z0-9][A-Za-z0-9._-]*$', 'once'))
    error('mh_fiber_dwi_load_config:InvalidValue', ...
        '%s contains unsupported BIDS label characters: %s', fieldName, value);
end
end

function value = require_logical(value, fieldName)
if islogical(value) && isscalar(value)
    return;
end
if ischar(value) || (isstring(value) && isscalar(value))
    raw = lower(strtrim(char(string(value))));
    if strcmp(raw, 'true')
        value = true;
        return;
    elseif strcmp(raw, 'false')
        value = false;
        return;
    end
end
error('mh_fiber_dwi_load_config:InvalidType', ...
    '%s must be true or false.', fieldName);
end

function value = require_scalar_number(value, fieldName)
if ~isnumeric(value) || ~isscalar(value) || ~isfinite(value)
    error('mh_fiber_dwi_load_config:InvalidType', ...
        '%s must be one finite number.', fieldName);
end
value = double(value);
end

function value = require_positive_integer(value, fieldName)
value = require_scalar_number(value, fieldName);
if value < 1 || value ~= round(value)
    error('mh_fiber_dwi_load_config:InvalidValue', ...
        '%s must be a positive integer.', fieldName);
end
end
