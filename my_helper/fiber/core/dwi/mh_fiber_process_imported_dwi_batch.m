function summary = mh_fiber_process_imported_dwi_batch(jobSpecs, opts)
% Process imported DWI job specifications and return a status table.

if nargin < 2 || isempty(opts)
    opts = struct();
end
opts = normalize_batch_options(opts);
jobSpecs = normalize_job_specs(jobSpecs);

nJobs = numel(jobSpecs);
workerCount = resolve_worker_count(opts, nJobs);

if opts.Parallel && workerCount > 1
    fprintf('Running DWI processing batch for %d subjects with %d parallel workers.\n', ...
        nJobs, workerCount);
else
    fprintf('Running DWI processing batch for %d subjects serially.\n', nJobs);
end
rows = mh_fiber_run_item_batch(nJobs, ...
    @(jobIndex, ~, isParallelWorker) process_one_job(jobSpecs(jobIndex), opts, isParallelWorker), ...
    empty_batch_row(), ...
    'Parallel', opts.Parallel && workerCount > 1, ...
    'ParallelWorkers', workerCount, ...
    'WorkerSetupFcn', @configure_single_thread_worker, ...
    'ProgressLabelFcn', @(jobIndex) jobSpecs(jobIndex).subjectId);

summary = struct2table(rows, 'AsArray', true);
end

function opts = normalize_batch_options(opts)
opts = fill_option(opts, 'Parallel', false);
opts = fill_option(opts, 'ParallelWorkers', 4);
opts = fill_option(opts, 'MaxConcurrentSynb0', []);
opts = fill_option(opts, 'DistortionCorrection', 'none');
opts = fill_option(opts, 'Synb0MinDockerMemoryGB', 12);

opts.Parallel = logical(opts.Parallel);
opts.ParallelWorkers = max(1, round(double(opts.ParallelWorkers)));
opts.DistortionCorrection = lower(strtrim(char(string(opts.DistortionCorrection))));
opts.Synb0MinDockerMemoryGB = double(opts.Synb0MinDockerMemoryGB);
if isempty(opts.MaxConcurrentSynb0)
    opts.MaxConcurrentSynb0 = NaN;
else
    opts.MaxConcurrentSynb0 = max(1, round(double(opts.MaxConcurrentSynb0)));
end
end

function opts = fill_option(opts, fieldName, value)
if ~isfield(opts, fieldName)
    opts.(fieldName) = value;
end
end

function jobSpecs = normalize_job_specs(jobSpecs)
if istable(jobSpecs)
    jobSpecs = table2struct(jobSpecs);
end
if ~isstruct(jobSpecs)
    error('mh_fiber_process_imported_dwi_batch:InvalidJobSpecs', ...
        'jobSpecs must be a struct array or table.');
end
if isempty(jobSpecs)
    error('mh_fiber_process_imported_dwi_batch:NoJobs', ...
        'No DWI processing jobs were provided.');
end
end

function workerCount = resolve_worker_count(opts, nJobs)
workerCount = min(opts.ParallelWorkers, nJobs);
if ~opts.Parallel || workerCount <= 1
    workerCount = 1;
    return;
end

if strcmp(opts.DistortionCorrection, 'synb0')
    if ~isnan(opts.MaxConcurrentSynb0)
        synb0Limit = opts.MaxConcurrentSynb0;
    else
        memoryGb = resolve_container_or_system_memory_gb();
        if isnan(memoryGb) || opts.Synb0MinDockerMemoryGB <= 0
            synb0Limit = 1;
        else
            synb0Limit = max(1, floor(memoryGb / opts.Synb0MinDockerMemoryGB));
        end
    end
    workerCount = min(workerCount, synb0Limit);
end
workerCount = max(1, workerCount);
end

function memoryGb = resolve_container_or_system_memory_gb()
memoryGb = NaN;
[status, out] = system('docker info --format "{{.MemTotal}}"');
if status == 0
    bytes = str2double(strtrim(out));
    if isfinite(bytes) && bytes > 0
        memoryGb = bytes / 1024^3;
        return;
    end
end

if ismac
    [status, out] = system('sysctl -n hw.memsize');
    if status == 0
        bytes = str2double(strtrim(out));
        if isfinite(bytes) && bytes > 0
            memoryGb = bytes / 1024^3;
        end
    end
elseif isunix && isfile('/proc/meminfo')
    text = fileread('/proc/meminfo');
    token = regexp(text, 'MemTotal:\s+(\d+)\s+kB', 'tokens', 'once');
    if ~isempty(token)
        memoryGb = str2double(token{1}) / 1024^2;
    end
end
end

function row = process_one_job(jobSpec, opts, ~)
row = mh_fiber_process_imported_dwi(jobSpec, opts);
end

function configure_single_thread_worker()
setenv('OMP_NUM_THREADS', '1');
setenv('ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS', '1');
setenv('MKL_NUM_THREADS', '1');
setenv('OPENBLAS_NUM_THREADS', '1');
setenv('VECLIB_MAXIMUM_THREADS', '1');
end

function row = empty_batch_row()
row = struct();
row.subject = '';
row.source_base = '';
row.status = '';
row.message = '';
row.raw_dwi = '';
row.staged_dwi = '';
row.b0 = '';
row.anchor_modality = '';
row.coregistration_method = '';
row.distortion_correction = '';
row.anchor_anat = '';
row.normalization_forward = '';
row.dwi_to_anchor_transform = '';
row.anchor_to_dwi_transform = '';
row.b0_on_anchor = '';
row.anchor_on_b0 = '';
row.qc_dir = '';
row.dwi_volumes = NaN;
row.bval_count = NaN;
row.bvec_count = NaN;
row.b0_count = NaN;
row.dim_x = NaN;
row.dim_y = NaN;
row.dim_z = NaN;
row.voxel_x = NaN;
row.voxel_y = NaN;
row.voxel_z = NaN;
row.low_resolution_warning = false;
row.forward_transform_exists = false;
row.inverse_transform_exists = false;
row.fa_status = '';
row.mask_status = '';
row.coregistration_status = '';
row.synb0_status = '';
row.eddy_status = '';
row.rotated_bvec = '';
row.topup_field = '';
row.total_readout_time = NaN;
row.total_readout_time_source = '';
row.phase_encoding_vector = '';
row.b0_reference_strategy = '';
row.b0_reference_source_index = NaN;
row.b0_reference_hash = '';
row.eddy_volume_mapping = '';
row.fake_b0_preproc = '';
row.fake_b0_coreg_target = '';
row.fake_b0_metadata = '';
end
