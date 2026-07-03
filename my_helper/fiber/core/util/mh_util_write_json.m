function mh_util_write_json(path, data, errorId)
% Write a struct or table-compatible value as pretty JSON when available.

if nargin < 3 || strlength(string(errorId)) == 0
    errorId = 'mh_util_write_json:CannotWriteJson';
end

fid = fopen(path, 'w');
if fid < 0
    error(errorId, 'Cannot write JSON: %s', path);
end
cleanup = onCleanup(@() fclose(fid));

try
    text = jsonencode(data, PrettyPrint=true);
catch
    try
        text = jsonencode(data, PrettyPrint = true);
    catch
        text = jsonencode(data);
    end
end
fprintf(fid, '%s\n', text);
end
