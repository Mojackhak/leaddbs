function tableOut = mh_util_force_string_vars(tableOut, stringVars)
% Convert selected table variables to string when they are present.

for i = 1:numel(stringVars)
    if ismember(stringVars{i}, tableOut.Properties.VariableNames)
        tableOut.(stringVars{i}) = string(tableOut.(stringVars{i}));
    end
end
end
