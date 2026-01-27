function ea_conda_setproxy(proxy)
arguments
    proxy {mustBeTextScalar} = ''   % proxy to set
end

if isempty(proxy)
    proxy = inputdlg('Set proxy for conda and pip', '', 1, {'http://127.0.0.1:7897'}); % clash default
    proxy = proxy{1};
else
    return;
end

ea_cprintf('*Comments', 'Set proxy for pip...\n');
ea_conda.run(['pip config set global.proxy ' proxy]);
ea_cprintf('*Comments', 'Set proxy for conda...\n');
ea_conda.run(['conda config --set proxy_servers.http ' proxy]);
ea_conda.run(['conda config --set proxy_servers.https ' proxy]);
ea_cprintf('*Comments', 'Set proxy for git...\n');
ea_conda.run(['git config --global http.proxy '  proxy]);
ea_conda.run(['git config --global https.proxy ' proxy]);