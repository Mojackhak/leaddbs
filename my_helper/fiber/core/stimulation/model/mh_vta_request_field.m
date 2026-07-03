function value = mh_vta_request_field(request, fieldName, fallback)
% Return a VTA request field value or an explicit fallback.

if isstruct(request) && isfield(request, fieldName)
    value = request.(fieldName);
else
    value = fallback;
end
end
