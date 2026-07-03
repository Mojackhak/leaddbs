function manifest = mh_fiber_stnsnr_add_vta_manifest_fields(manifest, opts)
% Add shared STN/SNr VTA option selections to a manifest struct.

manifest.vta_gm_atlas = char(string(opts.VtaGmAtlas));
manifest.vta_model_key = char(string(opts.VtaModelKey));
manifest.vta_execution_mode = char(string(opts.VtaExecutionMode));
manifest.vta_parallel_workers = double(opts.VtaParallelWorkers);
manifest.vta_process_work_dir = char(string(opts.VtaProcessWorkDir));
manifest.vta_process_dry_run = logical(opts.VtaProcessDryRun);
manifest.vta_process_poll_seconds = double(opts.VtaProcessPollSeconds);
manifest.vta_process_timeout_seconds = double(opts.VtaProcessTimeoutSeconds);
end
