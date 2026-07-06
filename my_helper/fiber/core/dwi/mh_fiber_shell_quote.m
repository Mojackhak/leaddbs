function quoted = mh_fiber_shell_quote(path)
% Quote a path or shell argument for POSIX shell commands.

quoted = ['''', strrep(char(string(path)), '''', '''"''"'''), ''''];
end
