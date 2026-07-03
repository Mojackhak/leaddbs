function out = mh_util_rmfield_safe(in, fields)
% Remove struct fields that are present and ignore missing fields.

out = in;
present = fields(isfield(out, fields));
if ~isempty(present)
    out = rmfield(out, present);
end
end
