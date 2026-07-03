function summary = mh_fiber_process_imported_dwi_batch(jobSpecs, opts)
% Process imported DWI job specifications in serial and return a status table.

if nargin < 2 || isempty(opts)
    opts = struct();
end
jobSpecs = normalize_job_specs(jobSpecs);

nJobs = numel(jobSpecs);
rows = repmat(empty_batch_row(), nJobs, 1);

fprintf('Running DWI processing batch for %d subjects.\n', nJobs);
for i = 1:nJobs
    fprintf('\n[%d/%d] %s\n', i, nJobs, char(string(jobSpecs(i).subjectId)));
    rows(i) = mh_fiber_process_imported_dwi(jobSpecs(i), opts);
end

summary = struct2table(rows, 'AsArray', true);
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
row.fake_b0_preproc = '';
row.fake_b0_coreg_target = '';
row.fake_b0_metadata = '';
end
