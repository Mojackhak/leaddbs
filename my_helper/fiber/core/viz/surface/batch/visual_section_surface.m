function summary = visual_section_surface( ...
    section_dir, df_type, region_view_map, cfg_n2p, cfg_plot_base, overwrite, ...
    raw_ylabel_tpl, band_tpl, prefix_tpl, cfg_batch ...
)
%VISUAL_SECTION_SURFACE Batch plot NIfTI heatmaps as Lead-DBS surfaces.
%
% Inputs:
%   section_dir (char/string): full path of the section directory.
%   df_type (char/string): prefix key, for example 'norm' or 'raw'.
%   region_view_map (struct|[]): if empty, region_views() is used.
%   cfg_n2p (struct|[]): if empty, default_nifti2patch_config() is used.
%   cfg_plot_base (struct|[]): if empty, default_plot_patch_config() is used.
%   overwrite (logical|0/1): overwrite outputs if they exist.
%   raw_ylabel_tpl, band_tpl, prefix_tpl: optional containers.Map label maps.
%   cfg_batch (struct|[]): optional batch behavior config.

    if nargin < 1 || isempty(section_dir)
        error('section_dir must be provided, e.g. "/Users/Research/STNSNr/med".');
    end
    section_dir = char(string(section_dir));

    if nargin < 2 || isempty(df_type)
        df_type = 'norm';
    end
    df_type = char(string(df_type));

    default_rv = region_views();
    if nargin < 3 || isempty(region_view_map)
        region_view_map = default_rv;
    else
        if ~isstruct(region_view_map)
            error('region_view_map must be a struct or empty.');
        end
        region_view_map = struct_deep_update(default_rv, region_view_map);
    end

    default_cfg_n2p = default_nifti2patch_config();
    if nargin < 4 || isempty(cfg_n2p)
        cfg_n2p = default_cfg_n2p;
    else
        if ~isstruct(cfg_n2p)
            error('cfg_n2p must be a struct or empty.');
        end
        cfg_n2p = struct_deep_update(default_cfg_n2p, cfg_n2p);
    end

    default_cfg_plot = default_plot_patch_config();
    if nargin < 5 || isempty(cfg_plot_base)
        cfg_plot_base = default_cfg_plot;
    else
        if ~isstruct(cfg_plot_base)
            error('cfg_plot_base must be a struct or empty.');
        end
        cfg_plot_base = struct_deep_update(default_cfg_plot, cfg_plot_base);
    end

    if nargin < 6 || isempty(overwrite)
        overwrite = false;
    end
    overwrite = logical(overwrite);

    if nargin < 7, raw_ylabel_tpl = []; end
    if nargin < 8, band_tpl = []; end
    if nargin < 9, prefix_tpl = []; end
    if nargin < 10, cfg_batch = []; end

    if ~isempty(raw_ylabel_tpl) && ~isa(raw_ylabel_tpl, 'containers.Map')
        error('raw_ylabel_tpl must be a containers.Map or empty.');
    end
    if ~isempty(band_tpl) && ~isa(band_tpl, 'containers.Map')
        error('band_tpl must be a containers.Map or empty.');
    end
    if ~isempty(prefix_tpl) && ~isa(prefix_tpl, 'containers.Map')
        error('prefix_tpl must be a containers.Map or empty.');
    end

    cfg_batch = local_resolve_batch_config(cfg_batch);
    output_formats = local_normalize_output_formats(cfg_batch.OutputFormats);

    if cfg_batch.Headless
        cfg_plot_base.FigureVisible = 'off';
        if strcmpi(char(cfg_batch.HeadlessMode), 'strict')
            cfg_plot_base.StrictHeadless = true;
            cfg_plot_base.FigureBackend = 'matlab';
            cfg_plot_base.ExportRenderer = 'painters';
        end
    end

    if ~exist(section_dir, 'dir')
        error('section_dir not found: %s', section_dir);
    end

    surface_root = fileparts(fileparts(mfilename('fullpath')));
    local_init_surface_paths(surface_root);

    headless_cleanup = local_apply_headless(cfg_batch); %#ok<NASGU>

    nifti_files = find_heatmap_niftis(section_dir, ...
        'PathMustContain', cfg_batch.PathMustContain, ...
        'Extensions', [".nii", ".nii.gz"], ...
        'IgnoreCase', true);

    fprintf('[INFO] section_dir: %s\n', section_dir);
    fprintf('[INFO] Found %d NIfTI files (path contains "%s").\n', ...
        numel(nifti_files), char(cfg_batch.PathMustContain));
    fprintf('[INFO] Output formats: %s\n', strjoin(cellstr(output_formats), ', '));

    use_parallel = local_prepare_parallel(cfg_batch, numel(nifti_files), cfg_plot_base);
    if use_parallel
        fprintf('[INFO] Parallel mode: NIfTI-level parfor.\n');
    else
        fprintf('[INFO] Parallel mode: sequential.\n');
    end

    results = cell(numel(nifti_files), 1);
    if use_parallel
        parfor i = 1:numel(nifti_files)
            local_init_surface_paths(surface_root);
            results{i} = local_process_one_nifti( ...
                nifti_files(i), section_dir, df_type, region_view_map, ...
                cfg_n2p, cfg_plot_base, overwrite, raw_ylabel_tpl, ...
                band_tpl, prefix_tpl, cfg_batch, output_formats);
        end
    else
        for i = 1:numel(nifti_files)
            results{i} = local_process_one_nifti( ...
                nifti_files(i), section_dir, df_type, region_view_map, ...
                cfg_n2p, cfg_plot_base, overwrite, raw_ylabel_tpl, ...
                band_tpl, prefix_tpl, cfg_batch, output_formats);
        end
    end

    summary = local_aggregate_results(results);
    summary.section_dir = section_dir;
    summary.df_type = df_type;
    summary.path_must_contain = char(cfg_batch.PathMustContain);
    summary.output_formats = output_formats;
    summary.use_parallel = use_parallel;
    summary.num_nifti_found = numel(nifti_files);
    summary.timestamp = datestr(now);

    fprintf('\n[DONE] nifti=%d, jobs=%d, done=%d, skipped=%d, failed=%d\n', ...
        summary.total_nifti, summary.total_jobs, summary.done_jobs, ...
        summary.skip_jobs, summary.fail_jobs);
    fprintf('[INFO] Failed NIfTI unique count = %d\n', ...
        numel(summary.failed_paths_unique));

    clear headless_cleanup;
end

function cfg_batch = local_resolve_batch_config(cfg_batch_in)
%LOCAL_RESOLVE_BATCH_CONFIG Merge caller batch config into defaults.

    defaults = struct();
    defaults.OutputFormats = "png";
    defaults.Headless = true;
    defaults.HeadlessMode = "standard";
    defaults.UseParallel = false;
    defaults.NumWorkers = [];
    defaults.PathMustContain = "";
    defaults.SkipExisting = true;
    defaults.CloseFigures = true;

    if nargin < 1 || isempty(cfg_batch_in)
        cfg_batch = defaults;
        return;
    end
    if ~isstruct(cfg_batch_in)
        error('cfg_batch must be a struct or empty.');
    end

    cfg_batch = struct_deep_update(defaults, cfg_batch_in);
    cfg_batch.Headless = logical(cfg_batch.Headless);
    cfg_batch.UseParallel = logical(cfg_batch.UseParallel);
    cfg_batch.SkipExisting = logical(cfg_batch.SkipExisting);
    cfg_batch.CloseFigures = logical(cfg_batch.CloseFigures);
    cfg_batch.HeadlessMode = string(cfg_batch.HeadlessMode);
    cfg_batch.PathMustContain = string(cfg_batch.PathMustContain);
end

function output_formats = local_normalize_output_formats(output_formats_in)
%LOCAL_NORMALIZE_OUTPUT_FORMATS Return lowercase extensions without dots.

    if isempty(output_formats_in)
        output_formats = "png";
    elseif ischar(output_formats_in)
        output_formats = string({output_formats_in});
    elseif isstring(output_formats_in)
        output_formats = output_formats_in;
    elseif iscellstr(output_formats_in)
        output_formats = string(output_formats_in);
    else
        output_formats = string(output_formats_in);
    end

    output_formats = strip(lower(output_formats(:)));
    output_formats = erase(output_formats, ".");
    output_formats(output_formats == "") = [];
    output_formats = unique(output_formats, 'stable');
    if isempty(output_formats)
        error('cfg_batch.OutputFormats must contain at least one output format.');
    end
end

function cleanup_obj = local_apply_headless(cfg_batch)
%LOCAL_APPLY_HEADLESS Hide figures globally for the current MATLAB process.

    cleanup_obj = [];
    if ~cfg_batch.Headless
        return;
    end

    old_vis = get(groot, 'DefaultFigureVisible');
    set(groot, 'DefaultFigureVisible', 'off');
    cleanup_obj = onCleanup(@() set(groot, 'DefaultFigureVisible', old_vis));
end

function local_init_surface_paths(surface_root)
%LOCAL_INIT_SURFACE_PATHS Ensure batch workers can find local helpers.

    addpath(fullfile(surface_root, 'batch'));
    addpath(fullfile(surface_root, 'batch_helper'));
    addpath(fullfile(surface_root, 'render'));
end

function use_parallel = local_prepare_parallel(cfg_batch, n_files, cfg_plot_base)
%LOCAL_PREPARE_PARALLEL Start a pool when possible, otherwise fall back.

    use_parallel = false;
    if ~cfg_batch.UseParallel || n_files <= 1
        return;
    end

    if exist('parpool', 'file') ~= 2 || exist('gcp', 'file') ~= 2
        warning('VISUAL_SECTION_SURFACE:ParallelUnavailable', ...
            'Parallel Computing Toolbox is unavailable; using sequential mode.');
        return;
    end

    try
        pool = gcp('nocreate');
        if isempty(pool)
            if isempty(cfg_batch.NumWorkers)
                parpool('local');
            else
                parpool('local', cfg_batch.NumWorkers);
            end
        end
        if ~local_parallel_font_preflight(cfg_plot_base)
            warning('VISUAL_SECTION_SURFACE:ParallelFontUnavailable', ...
                ['Parallel workers failed the strict PDF font probe; ', ...
                 'using sequential strict-headless mode.']);
            return;
        end
        use_parallel = true;
    catch ME
        warning('VISUAL_SECTION_SURFACE:ParallelStartFailed', ...
            'Parallel pool startup failed; using sequential mode. %s', ME.message);
        use_parallel = false;
    end
end

function ok = local_parallel_font_preflight(cfg_plot)
%LOCAL_PARALLEL_FONT_PREFLIGHT Verify strict PDF font rendering on workers.

    ok = true;
    if ~local_plot_requires_sans_font(cfg_plot)
        return;
    end

    candidates = local_parallel_font_candidates(cfg_plot);
    if isempty(candidates)
        return;
    end

    try
        spmd
            use_symbol_for_greek = logical(local_get_plot_field(cfg_plot, 'UseSymbolForGreek', false));
            worker_ok = local_worker_pdf_font_probe(candidates, use_symbol_for_greek);
        end

        ok_values = false(1, numel(worker_ok));
        for i = 1:numel(worker_ok)
            ok_values(i) = logical(worker_ok{i});
        end
        ok = all(ok_values);
    catch ME
        warning('VISUAL_SECTION_SURFACE:ParallelFontPreflightFailed', ...
            'Parallel worker font preflight failed; using sequential mode. %s', ME.message);
        ok = false;
    end
end

function tf = local_plot_requires_sans_font(cfg_plot)
%LOCAL_PLOT_REQUIRES_SANS_FONT Return true for strict sans-serif plotting.

    try
        tf = isstruct(cfg_plot) && isfield(cfg_plot, 'RequireSansSerifFont') && ...
            logical(cfg_plot.RequireSansSerifFont);
    catch
        tf = false;
    end
end

function candidates = local_parallel_font_candidates(cfg_plot)
%LOCAL_PARALLEL_FONT_CANDIDATES Return non-Helvetica strict font candidates.

    candidates = {};
    candidates = local_append_font_candidates(candidates, ...
        local_get_plot_field(cfg_plot, 'FontName', 'Arial'));
    candidates = local_append_font_candidates(candidates, ...
        local_get_plot_field(cfg_plot, 'FontFallbackNames', ...
        {'Arial', 'Arial Unicode MS', 'Helvetica', 'DejaVu Sans', 'Liberation Sans'}));
    candidates = candidates(~cellfun(@isempty, candidates));

    keep = true(size(candidates));
    for i = 1:numel(candidates)
        normalized = regexprep(lower(candidates{i}), '[^a-z0-9]', '');
        keep(i) = ~contains(normalized, 'helvetica');
    end
    candidates = candidates(keep);

    [~, idx] = unique(lower(candidates), 'stable');
    candidates = candidates(sort(idx));
end

function candidates = local_append_font_candidates(candidates, value)
%LOCAL_APPEND_FONT_CANDIDATES Append font names from char, string, or cellstr.

    if isempty(value)
        return;
    end

    if ischar(value)
        candidates{end + 1} = strtrim(value);
    elseif isstring(value)
        for i = 1:numel(value)
            candidates{end + 1} = strtrim(char(value(i)));
        end
    elseif iscellstr(value)
        for i = 1:numel(value)
            candidates{end + 1} = strtrim(value{i});
        end
    end
end

function tf = local_worker_pdf_font_probe(candidates, use_symbol_for_greek)
%LOCAL_WORKER_PDF_FONT_PROBE Check actual PDF font embedding on a worker.

    if nargin < 2 || isempty(use_symbol_for_greek)
        use_symbol_for_greek = false;
    end
    tf = false;
    font_name = candidates{1};
    out_file = [tempname, '.pdf'];
    h_fig = [];
    cleanup_obj = local_apply_root_font_defaults(font_name); %#ok<NASGU>

    try
        h_fig = figure( ...
            'Visible', 'off', ...
            'Color', 'white', ...
            'Renderer', 'painters', ...
            'InvertHardcopy', 'off', ...
            'DefaultAxesFontName', font_name, ...
            'DefaultTextFontName', font_name);
        h_ax = axes('Parent', h_fig, 'FontName', font_name, 'Visible', 'off');
        axis(h_ax, [0 1 0 1]);
        axis(h_ax, 'off');
        if use_symbol_for_greek
            text(h_ax, 0.45, 0.5, 'Arial', ...
                'FontName', font_name, ...
                'Interpreter', 'none', ...
                'FontSize', 24, ...
                'HorizontalAlignment', 'right', ...
                'VerticalAlignment', 'middle');
            text(h_ax, 0.47, 0.5, '\fontname{Symbol} Δβδ', ...
                'FontName', font_name, ...
                'Interpreter', 'tex', ...
                'FontSize', 24, ...
                'HorizontalAlignment', 'left', ...
                'VerticalAlignment', 'middle');
        else
            text(h_ax, 0.5, 0.5, 'Δβδ Arial', ...
                'FontName', font_name, ...
                'Interpreter', 'none', ...
                'FontSize', 24, ...
                'HorizontalAlignment', 'center', ...
                'VerticalAlignment', 'middle');
        end
        exportgraphics(h_fig, out_file, 'ContentType', 'vector');
        close(h_fig);
        h_fig = [];

        raw_text = local_read_text_lower(out_file);
        font_names = local_extract_pdf_font_names(raw_text);
        tf = local_pdf_fonts_are_strict_sans(font_names, candidates, raw_text, use_symbol_for_greek);
    catch ME
        fprintf('[WARN] Worker PDF font probe failed: %s\n', ME.message);
        tf = false;
    end

    if ~isempty(h_fig) && isvalid(h_fig)
        try
            close(h_fig);
        catch
        end
    end
    local_delete_file_if_exists(out_file);
    clear cleanup_obj;
end

function cleanup_obj = local_apply_root_font_defaults(font_name)
%LOCAL_APPLY_ROOT_FONT_DEFAULTS Temporarily set root default fonts.

    cleanup_obj = [];
    if isempty(strtrim(char(font_name)))
        return;
    end

    old_axes_font = get(groot, 'DefaultAxesFontName');
    old_text_font = get(groot, 'DefaultTextFontName');
    set(groot, 'DefaultAxesFontName', font_name, 'DefaultTextFontName', font_name);
    cleanup_obj = onCleanup(@() set(groot, ...
        'DefaultAxesFontName', old_axes_font, ...
        'DefaultTextFontName', old_text_font));
end

function raw_text = local_read_text_lower(file_path)
%LOCAL_READ_TEXT_LOWER Read a file as lower-case text.

    fid = fopen(file_path, 'r');
    if fid < 0
        error('Could not read file: %s', file_path);
    end
    cleaner = onCleanup(@() fclose(fid));
    bytes = fread(fid, Inf, '*uint8')';
    clear cleaner;
    raw_text = lower(char(bytes));
end

function font_names = local_extract_pdf_font_names(raw_text)
%LOCAL_EXTRACT_PDF_FONT_NAMES Extract normalized FontName/BaseFont entries.

    matches = regexp(raw_text, '/(?:fontname|basefont)\s*/([^\s<>\[\]()/]+)', ...
        'tokens');
    font_names = cell(1, numel(matches));
    for i = 1:numel(matches)
        font_name = matches{i}{1};
        font_name = regexprep(font_name, '^[a-z]{6}\+', '');
        font_name = regexprep(font_name, '[^a-z0-9]', '');
        font_names{i} = font_name;
    end
    font_names = font_names(~cellfun(@isempty, font_names));
    font_names = unique(font_names, 'stable');
end

function tf = local_pdf_fonts_are_strict_sans(font_names, candidates, raw_text, use_symbol_for_greek)
%LOCAL_PDF_FONTS_ARE_STRICT_SANS Validate worker probe PDF fonts.

    if nargin < 4 || isempty(use_symbol_for_greek)
        use_symbol_for_greek = false;
    end
    tf = false;
    if isempty(font_names)
        return;
    end

    forbidden = {'helvetica', 'mwacmr', 'mwbcmr', 'cmr', 'cmmi', 'cmsy', 'stix'};
    if ~use_symbol_for_greek
        forbidden = unique([forbidden, {'symbol'}], 'stable');
    end
    if any(local_font_names_match_tokens(font_names, forbidden)) || ...
            contains(raw_text, 'computer modern')
        return;
    end

    allowed = local_pdf_allowed_unicode_font_tokens(candidates, use_symbol_for_greek);
    tf = any(local_font_names_match_tokens(font_names, allowed)) && ...
        all(local_font_names_match_tokens(font_names, allowed));
    if use_symbol_for_greek
        tf = tf && any(local_font_names_match_tokens(font_names, {'symbol'}));
    end
end

function tokens = local_pdf_allowed_unicode_font_tokens(candidates, use_symbol_for_greek)
%LOCAL_PDF_ALLOWED_UNICODE_FONT_TOKENS Return allowed strict PDF font tokens.

    if nargin < 2 || isempty(use_symbol_for_greek)
        use_symbol_for_greek = false;
    end
    tokens = {'arial', 'arialmt', 'arialunicodems', 'arialunicode', ...
        'dejavusans', 'liberationsans'};
    if use_symbol_for_greek
        tokens{end + 1} = 'symbol';
    end
    for i = 1:numel(candidates)
        name = lower(candidates{i});
        normalized = regexprep(name, '[^a-z0-9]', '');
        if contains(normalized, 'arial') || ...
                strcmp(normalized, 'dejavusans') || ...
                strcmp(normalized, 'liberationsans')
            tokens{end + 1} = normalized; %#ok<AGROW>
        end
    end
    tokens = tokens(~cellfun(@isempty, tokens));
    tokens = unique(tokens, 'stable');
end

function tf = local_font_names_match_tokens(font_names, tokens)
%LOCAL_FONT_NAMES_MATCH_TOKENS Match normalized font names to tokens.

    tf = false(size(font_names));
    for i = 1:numel(font_names)
        tf(i) = any(strcmp(font_names{i}, tokens)) || ...
            any(contains(font_names{i}, tokens));
    end
end

function local_delete_file_if_exists(file_path)
%LOCAL_DELETE_FILE_IF_EXISTS Delete a temporary file.

    if exist(file_path, 'file') == 2
        try
            delete(file_path);
        catch
        end
    end
end

function result = local_process_one_nifti( ...
    data_path, section_dir, df_type, region_view_map, cfg_n2p, cfg_plot_base, ...
    overwrite, raw_ylabel_tpl, band_tpl, prefix_tpl, cfg_batch, output_formats)
%LOCAL_PROCESS_ONE_NIFTI Build one patch and export all requested views.

    result = local_empty_result(data_path);
    result.total_nifti = 1;

    worker_cleanup = local_apply_headless(cfg_batch); %#ok<NASGU>

    try
        info = parse_heatmap_path(data_path, section_dir);
    catch ME
        fprintf('[WARN] Unsupported NIfTI layout, skip: %s\n', data_path);
        fprintf('       %s\n', ME.message);
        result.skip_jobs = 1;
        result.skipped_paths = string(data_path);
        return;
    end

    if ~isfield(region_view_map, info.region_key)
        fprintf('[WARN] Unknown region="%s" (region_key="%s"), skip: %s\n', ...
            info.region, info.region_key, data_path);
        result.skip_jobs = 1;
        result.skipped_paths = string(data_path);
        return;
    end

    clabel = local_format_colorbar_label( ...
        info, df_type, raw_ylabel_tpl, band_tpl, prefix_tpl, data_path, cfg_plot_base);
    views = region_view_map.(info.region_key);
    n_views = numel(views);
    n_formats = numel(output_formats);
    result.total_jobs = n_views * n_formats;

    out_base = strip_nii_ext(data_path);
    out_files = strings(n_views, n_formats);
    needs = false(n_views, n_formats);

    for vidx = 1:n_views
        for fidx = 1:n_formats
            out_files(vidx, fidx) = sprintf('%s_surface%d.%s', ...
                out_base, vidx, output_formats(fidx));
            needs(vidx, fidx) = overwrite || ~cfg_batch.SkipExisting || ...
                exist(out_files(vidx, fidx), 'file') ~= 2;
        end
    end

    if ~any(needs(:))
        fprintf('[SKIP] All outputs exist: %s\n', data_path);
        result.skip_jobs = result.total_jobs;
        result.skipped_paths = string(data_path);
        return;
    end

    fprintf('[DO ] Patch build: %s\n', data_path);
    try
        patch_obj = leaddbs_nifti2patch(data_path, cfg_n2p);
    catch ME
        fprintf('[FAIL] Patch build failed: %s\n', data_path);
        fprintf('       %s\n', ME.message);
        result.fail_jobs = sum(needs(:));
        result.failed_paths = string(data_path);
        local_close_figures(cfg_batch);
        return;
    end

    for vidx = 1:n_views
        for fidx = 1:n_formats
            out_file = out_files(vidx, fidx);
            if ~needs(vidx, fidx)
                fprintf('[SKIP] Exists: %s\n', out_file);
                result.skip_jobs = result.skip_jobs + 1;
                continue;
            end

            fprintf('[DO ] View %d/%d -> %s\n', vidx, n_views, out_file);
            try
                cfg_plot = cfg_plot_base;
                cfg_plot.ViewStruct = views{vidx};
                cfg_plot.ColorbarLabel = clabel;
                cfg_plot.ExportFile = out_file;

                leaddbs_plot_patch(patch_obj, cfg_plot);

                result.done_jobs = result.done_jobs + 1;
            catch ME
                fprintf('[FAIL] Plot failed (view %d): %s\n', vidx, data_path);
                fprintf('       %s\n', ME.message);
                result.fail_jobs = result.fail_jobs + 1;
                result.failed_paths(end + 1, 1) = string(data_path);
            end
            local_close_figures(cfg_batch);
        end
    end

    clear worker_cleanup;
end

function result = local_empty_result(data_path)
%LOCAL_EMPTY_RESULT Create an aggregation-friendly result struct.

    result = struct();
    result.data_path = string(data_path);
    result.total_nifti = 0;
    result.total_jobs = 0;
    result.done_jobs = 0;
    result.skip_jobs = 0;
    result.fail_jobs = 0;
    result.failed_paths = strings(0, 1);
    result.skipped_paths = strings(0, 1);
end

function clabel = local_format_colorbar_label( ...
    info, df_type, raw_ylabel_tpl, band_tpl, prefix_tpl, data_path, cfg_plot_base)
%LOCAL_FORMAT_COLORBAR_LABEL Resolve a label with fallback behavior.

    label_style = local_get_plot_field(cfg_plot_base, 'ColorbarLabelStyle', 'latex');
    require_sans = logical(local_get_plot_field(cfg_plot_base, 'RequireSansSerifFont', false));

    try
        if isempty(raw_ylabel_tpl) && isempty(band_tpl) && isempty(prefix_tpl)
            clabel = format_label(info.param_type, ...
                'Prefix', df_type, ...
                'Band', info.band, ...
                'LabelStyle', label_style);
        else
            clabel = format_label(info.param_type, ...
                'Prefix', df_type, ...
                'Band', info.band, ...
                'RawYLabelTpl', raw_ylabel_tpl, ...
                'BandTpl', band_tpl, ...
                'PrefixTpl', prefix_tpl, ...
                'LabelStyle', label_style);
        end
    catch ME
        if require_sans && strcmpi(char(label_style), 'plain')
            rethrow(ME);
        end
        fprintf('[WARN] Label format failed, fallback to param_type. path=%s\n', data_path);
        fprintf('       %s\n', ME.message);
        clabel = char(info.param_type);
    end
end

function value = local_get_plot_field(cfg_plot, field_name, default_value)
%LOCAL_GET_PLOT_FIELD Return an optional plotting config value.

    value = default_value;
    try
        if isstruct(cfg_plot) && isfield(cfg_plot, field_name)
            value = cfg_plot.(field_name);
        end
    catch
        value = default_value;
    end
end

function local_close_figures(cfg_batch)
%LOCAL_CLOSE_FIGURES Close figures when batch config requests cleanup.

    if cfg_batch.CloseFigures
        try
            close all force;
        catch
            try
                close all;
            catch
            end
        end
    end
end

function summary = local_aggregate_results(results)
%LOCAL_AGGREGATE_RESULTS Combine worker result structs.

    summary = struct();
    summary.total_nifti = 0;
    summary.total_jobs = 0;
    summary.done_jobs = 0;
    summary.skip_jobs = 0;
    summary.fail_jobs = 0;

    failed_paths = strings(0, 1);
    skipped_paths = strings(0, 1);

    for i = 1:numel(results)
        if isempty(results{i})
            continue;
        end
        r = results{i};
        summary.total_nifti = summary.total_nifti + r.total_nifti;
        summary.total_jobs = summary.total_jobs + r.total_jobs;
        summary.done_jobs = summary.done_jobs + r.done_jobs;
        summary.skip_jobs = summary.skip_jobs + r.skip_jobs;
        summary.fail_jobs = summary.fail_jobs + r.fail_jobs;
        failed_paths = [failed_paths; r.failed_paths(:)]; %#ok<AGROW>
        skipped_paths = [skipped_paths; r.skipped_paths(:)]; %#ok<AGROW>
    end

    summary.failed_paths_unique = unique(failed_paths);
    summary.skipped_paths_unique = unique(skipped_paths);
end
