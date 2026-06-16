function quoted = mh_fiber_shell_quote(value)
% Quote a path or scalar value for POSIX shell commands.

text = char(string(value));
quoted = ['''', strrep(text, '''', '''"''"'''), ''''];
end
