function tableOut = mh_util_cell_rows_to_table(rows, variableNames, stringVars)
% Convert accumulated cell rows to a table and string-normalize selected columns.

if nargin < 3
    stringVars = {};
end

if isempty(rows)
    tableOut = table();
    return;
end

variableNames = cellstr(string(variableNames));
tableOut = cell2table(rows, 'VariableNames', variableNames);
tableOut = mh_util_force_string_vars(tableOut, stringVars);
end
