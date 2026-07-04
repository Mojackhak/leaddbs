function results = mh_vta_run_compute_tasks(cfg, S, options, tasks)
% Run an array of atomic VTA compute tasks using the configured execution mode.

if isempty(tasks)
    results = struct([]);
    return;
end

tasks = tasks(:);
exec = mh_vta_execution_config(cfg, numel(tasks));
resultCells = cell(numel(tasks), 1);

if any(strcmp(exec.mode, {'parpool', 'process'}))
    materialize_subject_gm_atlases(cfg, options, tasks);
end

switch exec.mode
    case 'sequential'
        for i = 1:numel(tasks)
            resultCells{i} = mh_vta_run_compute_task(cfg, S, options, tasks(i));
        end
    case 'parpool'
        parfor i = 1:numel(tasks)
            resultCells{i} = mh_vta_run_compute_task(cfg, S, options, tasks(i));
        end
    case 'process'
        results = mh_vta_run_compute_tasks_process(cfg, S, options, tasks, exec);
        return;
    otherwise
        error('mh_vta_run_compute_tasks:UnsupportedMode', ...
            'Unsupported VTA execution mode: %s', exec.mode);
end

results = vertcat(resultCells{:});
end

function materialize_subject_gm_atlases(cfg, options, tasks)
atlasNames = requested_gm_atlases(cfg, options, tasks);
for i = 1:numel(atlasNames)
    atlasName = char(atlasNames(i));
    preflightOptions = options;
    preflightOptions.native = 1;
    preflightOptions.orignative = 1;
    preflightOptions.atlasset = atlasName;
    request = struct('gmAtlas', atlasName, 'useAtlas', true);
    [preflightOptions, ~] = mh_vta_apply_settings(preflightOptions, cfg, request);

    fprintf('Ensuring subject-space VTA gray-matter atlas: %s\n', atlasName);
    ea_ptspecific_atl(preflightOptions);
    maskPath = subject_gm_mask_path(preflightOptions, atlasName);
    if ~isfile(maskPath)
        error('mh_vta_run_compute_tasks:MissingSubjectGmMask', ...
            'Subject-space gray-matter mask was not materialized: %s', maskPath);
    end
end
end

function atlasNames = requested_gm_atlases(cfg, options, tasks)
atlasNames = strings(0, 1);
for i = 1:numel(tasks)
    request = task_request(tasks(i));
    if isfield(request, 'useAtlas') && ~isempty(request.useAtlas) && ...
            ~logical(request.useAtlas)
        continue;
    end

    atlasName = task_gm_atlas(cfg, options, request);
    if strlength(string(atlasName)) > 0
        atlasNames(end+1, 1) = string(atlasName); %#ok<AGROW>
    end
end
atlasNames = unique(atlasNames, 'stable');
end

function request = task_request(task)
if isfield(task, 'request') && isstruct(task.request)
    request = task.request;
else
    request = struct();
end
end

function atlasName = task_gm_atlas(cfg, options, request)
atlasName = '';
if isfield(request, 'gmAtlas') && strlength(string(request.gmAtlas)) > 0
    atlasName = char(string(request.gmAtlas));
elseif isfield(cfg, 'vta') && isfield(cfg.vta, 'gmAtlas') && ...
        strlength(string(cfg.vta.gmAtlas)) > 0
    atlasName = char(string(cfg.vta.gmAtlas));
elseif isfield(options, 'atlasset') && strlength(string(options.atlasset)) > 0
    atlasName = char(string(options.atlasset));
end
end

function maskPath = subject_gm_mask_path(options, atlasName)
if ~isfield(options, 'root') || ~isfield(options, 'patientname')
    error('mh_vta_run_compute_tasks:MissingSubjectAtlasContext', ...
        'Options must include root and patientname to materialize subject-space atlas masks.');
end

maskBase = fullfile(options.root, options.patientname, 'atlases', atlasName, 'gm_mask.nii');
[maskPath, ~] = ea_niigz(maskBase);
end
