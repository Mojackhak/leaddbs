function value = mh_util_get_field(s, fieldName, fallback)
% Return a struct field value or a fallback when the field is absent.

if isfield(s, fieldName)
    value = s.(fieldName);
else
    value = fallback;
end
end
