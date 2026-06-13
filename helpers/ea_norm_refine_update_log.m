function ea_norm_refine_update_log(options, context)
% Store shared refinement metadata in the normalization method log.

methodLog = options.subj.norm.log.method;
if ~isfile(methodLog)
    return;
end

json = loadjson(methodLog);

json.refine.mode = context.mode;
json.refine.residual_method = context.method;

if isfield(context, 'prior') && isfield(context.prior, 'found') && context.prior.found
    json.refine.prior.forward = context.prior.forward;
    json.refine.prior.inverse = context.prior.inverse;
    json.refine.prior.format = context.prior.format;
end

if isfield(context, 'residual') && isfield(context.residual, 'found') && context.residual.found
    json.refine.residual.forward = context.residual.forward;
    json.refine.residual.inverse = context.residual.inverse;
    json.refine.residual.format = context.residual.format;
end

if isfield(context, 'final') && isfield(context.final, 'format')
    json.transform.format = context.final.format;
    json.transform.forward = context.final.forward;
    json.transform.inverse = context.final.inverse;
else
    json.transform.format = context.finalTransformFormat;
end

savejson('', json, methodLog);
