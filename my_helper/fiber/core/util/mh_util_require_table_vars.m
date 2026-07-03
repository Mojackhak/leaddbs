function mh_util_require_table_vars(tableIn, requiredVars, errorId, messageFormat)
% Require table variables, reporting the first missing variable.

requiredVars = cellstr(string(requiredVars));
for i = 1:numel(requiredVars)
    if ~ismember(requiredVars{i}, tableIn.Properties.VariableNames)
        error(char(string(errorId)), char(string(messageFormat)), requiredVars{i});
    end
end
end
