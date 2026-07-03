function literal = mh_vta_matlab_string_literal(value)
% Return a MATLAB character literal for generated batch expressions.

text = char(string(value));
literal = ['''', strrep(text, '''', ''''''), ''''];
end
