function ea_checkOSSDBSInstallv2

% OSS-DBS v2 deployment

% Check conda installation
if ~ea_conda.is_installed
    ea_cprintf('*Comments', 'Initializing conda...\n');
    ea_conda.install;
    ea_cprintf('*Comments', 'Done...\n');
end

% optional: provide the local path to OSS-DBSv2 in OSS-DBSv2.yml if rep is not avaialble

% install OSS-DBS v2 in the virtual environment
env = ea_conda_env('OSS-DBSv2');
if ~env.is_up_to_date
    ea_cprintf('*Comments', 'Updating OSS-DBS v2 conda environment...\n');
    env.force_create;
    ea_cprintf('*Comments', 'Done.\n');
end

if ispc
    [status, cmdout] = system('neuron --version');
    if status || ~contains(cmdout, '8.2.3+')
        ea_cprintf('*Comments', 'Installing NEURON 8.2.3 for Windows...\n');
        installer = fullfile(ea_prefsdir, 'temp', 'nrn-8.2.3.exe');
        ea_mkdir(fileparts(installer));
        try
            websave(installer, 'https://github.com/neuronsimulator/nrn/releases/download/8.2.3/nrn-8.2.3.w64-mingw-py-37-38-39-310-311-setup.exe');
        catch ME
            ea_error(['Failed to download NEURON installer for Windows:\n', ME.message], simpleStack=true);
        end
        installFolder = fullfile(ea_prefsdir, 'neuron');
        ea_delete(installFolder);
        try
            system(['start /b /wait "Install NEURON"', path_helper(installer), ' /S /D=', path_helper(installFolder)]);
        catch ME
            ea_error(['Failed to install NEURON for Windows:\n', ME.message], simpleStack=true);
        end
        ea_delete(installer);
        setenv('PATH', [getenv('PATH'), ';', fullfile(installFolder, 'bin')]);
    end
else
    [status, cmdout] = env.system('python -c ''import neuron;print(neuron.__version__)''');
    if status || ~strcmp(cmdout, '8.2.3+')
        ea_cprintf('*Comments', 'Install NEURON 8.2.3...\n');
        env.system('pip3 install neuron==8.2.3');
    end
end

% set installed flag
prefs = ea_prefs;
vatsettings = prefs.machine.vatsettings;
vatsettings.oss_dbs.installed = 1;
ea_setprefs('vatsettings', vatsettings);


% Handle space in path on Windows
function path = path_helper(path)
parts = strsplit(path, filesep);
for i=1:length(parts)
    if contains(parts{i}, ' ')
        parts{i} = ['"' parts{i} '"'];
    end
end
path = strjoin(parts, filesep);

