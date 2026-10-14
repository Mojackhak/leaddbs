function ea_check_localization_method(options, method)
% Reject automatic reconstruction methods that cannot represent mixed models.
if ~ismember(method, {'TRAC/CORE (Horn 2015)', 'Refined TRAC/CORE', 'PaCER (Husch 2017)'})
    return;
end
if isfield(options, 'elmodels') && ~isempty(options.elmodels)
    models = options.elmodels;
elseif isfield(options, 'subj') && isfield(options.subj, 'recon') && isfile(options.subj.recon.recon)
    saved = load(options.subj.recon.recon, 'reco');
    models = {saved.reco.props.elmodel};
else
    models = {options.elmodel};
end
models = cellfun(@(model) strrep(model, 'St. Jude', 'Abbott'), models, 'UniformOutput', false);
if numel(models) > 2 || numel(unique(models)) > 1 || any(options.sides > 2)
    error('LeadDBS:UnsupportedMultiElectrodeMethod', ...
        '%s does not support this electrode configuration. Use Manual, Slicer (Manual), or LeGUI import.', method);
end
end
