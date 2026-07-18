function label = format_label(param_type, varargin)
%DBSLFP_FORMAT_LABEL Format a colorbar label from param_type, prefix, and band key.
%
% Behavior change:
%   - If a key is not found in RAW_YLABEL_TPL / BAND_TPL / PREFIX_TPL,
%     fall back to returning the key itself (no error).

    p = inputParser;
    p.addRequired('param_type', @(x) ischar(x) || isstring(x));
    p.addParameter('Prefix', '', @(x) ischar(x) || isstring(x));
    p.addParameter('Band', '', @(x) ischar(x) || isstring(x));
    p.addParameter('RawYLabelTpl', [], @(x) isempty(x) || isa(x, 'containers.Map'));
    p.addParameter('BandTpl', [], @(x) isempty(x) || isa(x, 'containers.Map'));
    p.addParameter('PrefixTpl', [], @(x) isempty(x) || isa(x, 'containers.Map'));
    p.addParameter('LabelStyle', 'latex', @(x) ischar(x) || (isstring(x) && isscalar(x)));

    p.parse(param_type, varargin{:});

    param_type = char(string(p.Results.param_type));
    prefix_arg = char(string(p.Results.Prefix));
    band       = char(string(p.Results.Band));
    label_style = local_normalize_label_style(p.Results.LabelStyle);

    if isempty(band)
        error('Band must be provided.');
    end

    raw_ylabel_tpl_in = p.Results.RawYLabelTpl;
    band_tpl_in       = p.Results.BandTpl;
    prefix_tpl_in     = p.Results.PrefixTpl;

    if isempty(raw_ylabel_tpl_in) || isempty(band_tpl_in) || isempty(prefix_tpl_in)
        [raw_ylabel_tpl_def, band_tpl_def, prefix_tpl_def] = local_get_maps();
        if isempty(raw_ylabel_tpl_in), raw_ylabel_tpl_in = raw_ylabel_tpl_def; end
        if isempty(band_tpl_in),       band_tpl_in       = band_tpl_def;       end
        if isempty(prefix_tpl_in),     prefix_tpl_in     = prefix_tpl_def;     end
    end

    raw_ylabel_tpl = raw_ylabel_tpl_in;
    band_tpl       = band_tpl_in;
    prefix_tpl     = prefix_tpl_in;

    % ---- Resolve prefix (if not found in PREFIX_TPL, keep as-is) ----
    prefix = prefix_arg;
    if ~isempty(prefix_arg)
        prefix_key = strtrim(prefix_arg);
        mapped = map_lookup_case_insensitive(prefix_tpl, prefix_key, '');  % keep old logic
        if ~isempty(mapped)
            prefix = mapped;
        end
    end

    % If param_type not found in RAW_YLABEL_TPL, use param_type itself.
    tpl = map_lookup_case_insensitive(raw_ylabel_tpl, param_type, param_type);

    % If band not found in BAND_TPL, use band itself.
    key = map_lookup_case_insensitive(band_tpl, band, band);

    label = strrep(tpl, '<prefix>', prefix);
    label = strrep(label, '<key>', key);

    if strcmp(label_style, 'plain')
        label = local_latex_label_to_plain(label);
    end
end

function label_style = local_normalize_label_style(label_style_in)
%LOCAL_NORMALIZE_LABEL_STYLE Validate and normalize colorbar label style.

    label_style = lower(strtrim(char(string(label_style_in))));
    if isempty(label_style)
        label_style = 'latex';
    end

    valid_styles = {'latex', 'plain'};
    if ~any(strcmp(label_style, valid_styles))
        error('FORMAT_LABEL:BadLabelStyle', 'LabelStyle must be latex or plain.');
    end
end

function label = local_latex_label_to_plain(label_in)
%LOCAL_LATEX_LABEL_TO_PLAIN Convert the known label templates to plain text.

    label = char(string(label_in));

    replacements = {
        '\Delta', 'Δ';
        '\delta', 'δ';
        '\Theta', 'Θ';
        '\theta', 'θ';
        '\Alpha', 'Α';
        '\alpha', 'α';
        '\Beta', 'Β';
        '\beta', 'β';
        '\Gamma', 'Γ';
        '\gamma', 'γ';
        '\log_{10}', 'log₁₀';
        '\log_10', 'log₁₀';
        '\arcsinh', 'arcsinh';
    };

    label = strrep(label, '$', '');
    label = regexprep(label, '\\(mathrm|mbox)\{([^{}]*)\}', '$2');
    label = regexprep(label, '\\sqrt\{([^{}]*)\}', '√($1)');

    for i = 1:size(replacements, 1)
        label = strrep(label, replacements{i, 1}, replacements{i, 2});
    end

    label = strrep(label, '\,', ' ');
    label = strrep(label, '\ ', ' ');
    label = strrep(label, '~', ' ');
    label = strrep(label, '{', '');
    label = strrep(label, '}', '');
    label = regexprep(label, '\s+', ' ');
    label = strtrim(label);
    label = regexprep(label, '(^|\s)Δ\s+', '$1Δ');

    if ~isempty(regexp(label, '[$\\{}]', 'once'))
        error('FORMAT_LABEL:PlainConversionFailed', ...
            'LabelStyle plain could not safely convert label: %s', char(string(label_in)));
    end
end


function [raw_ylabel_tpl, band_tpl, prefix_tpl] = local_get_maps()
%LOCAL_GET_MAPS Build containers.Map objects once per MATLAB session.

    persistent RAW_YLABEL_TPL BAND_TPL PREFIX_TPL

    if isempty(RAW_YLABEL_TPL)
        RAW_YLABEL_TPL = containers.Map();

        % Mean
        RAW_YLABEL_TPL('aperiod-mean-scalar') = '$<prefix>\,\mathrm{Aperiodic}\,<key>\,\mathrm{power}\,(\mathrm{dB})$';
        RAW_YLABEL_TPL('period-mean-scalar')  = '$<prefix>\,\mathrm{Periodic}\,<key>\,\mathrm{power}\,(\mathrm{dB})$';
        RAW_YLABEL_TPL('raw-mean-scalar')     = '$<prefix>\,\mathrm{Total}\,<key>\,\mathrm{power}\,(\mathrm{dB})$';

        RAW_YLABEL_TPL('params-mean-scalar')  = '$<prefix>\,<key>\,$';

        RAW_YLABEL_TPL('burst-rate-scalar')       = '$<prefix>\,\mathrm{arcsinh}\,<key>\,\mathrm{burst\ rate}\,(\mathrm{Hz})$';
        % RAW_YLABEL_TPL('burst-duration-scalar')   = '$<prefix>\,\log_{10}\,<key>\,\mathrm{burst\ duration}\,(\mathrm{s})$';
        RAW_YLABEL_TPL('burst-duration-scalar')   = '$<prefix>\,\mathrm{ln}\,<key>\,\mathrm{burst\ duration}\,(\mathrm{s})$';
        RAW_YLABEL_TPL('burst-occupation-scalar') = '$<prefix>\,<key>\,\mathrm{burst\ occupation}$';
        % RAW_YLABEL_TPL('burst-mean-scalar')       = '$<prefix>\,\log_{10}\,<key>\,\mathrm{burst\ amplitude}\,(\mathrm{V})$';
        RAW_YLABEL_TPL('burst-mean-scalar')       = '$<prefix>\,\mathrm{ln}\,<key>\,\mathrm{burst\ amplitude}\,(\mathrm{V})$';

        RAW_YLABEL_TPL('coh-mean-scalar')   = '$<prefix>$ Fisher z of $\sqrt{<key>\ \mathrm{coherence}}$';
        RAW_YLABEL_TPL('ciplv-mean-scalar') = '$<prefix>$ $\mathrm{logit}(<key>\ \mathrm{ciPLV})$';
        RAW_YLABEL_TPL('wpli-mean-scalar')  = '$<prefix>$ $\mathrm{logit}(<key>\ \mathrm{wPLI})$';

        RAW_YLABEL_TPL('delta_net_gc-mean-scalar') = '$<prefix>\,<key>\,\mathrm{TRGC}$';
        RAW_YLABEL_TPL('psi-mean-scalar')          = '$<prefix>\,<key>\,\mathrm{PSI}$';
    end

    if isempty(BAND_TPL)
        BAND_TPL = containers.Map();

        BAND_TPL('Delta')     = '\delta';
        BAND_TPL('Theta')     = '\theta';
        BAND_TPL('Alpha')     = '\alpha';
        BAND_TPL('Beta')      = '\beta';
        BAND_TPL('Beta_low')  = '\mathrm{low}\mbox{-}\beta';
        BAND_TPL('Beta_high') = '\mathrm{high}\mbox{-}\beta';
        BAND_TPL('Gamma')     = '\gamma';

        BAND_TPL('Exponent')  = '\mathrm{Exponent}';
        BAND_TPL('Offset')    = '\mathrm{Offset}';
    end

    if isempty(PREFIX_TPL)
        PREFIX_TPL = containers.Map();

        % Prefix modes:
        %   norm -> delta prefix
        %   raw  -> keep a small LaTeX space command (or use '' if you prefer no prefix)
        PREFIX_TPL('norm') = '\Delta';
        PREFIX_TPL('raw')  = '\ ';
    end

    raw_ylabel_tpl = RAW_YLABEL_TPL;
    band_tpl = BAND_TPL;
    prefix_tpl = PREFIX_TPL;
end
