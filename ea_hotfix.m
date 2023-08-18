function success=ea_hotfix(varargin)
% lead hotfix
success=0;
local = ea_getvsn('local');
web = ea_getvsn('web');

% if local version unknow or outdated, skip applying hotfix
hotfix = 0;
if strcmp(local,web) % local version is the latest release, applicable for hotfix
    hotfix = 1;
end

earoot=ea_getearoot;

updurl = 'https://www.lead-dbs.org/release/download.php';
if hotfix
    try
        disp('*** Updating LEAD. Please do not quit MATLAB.');
        ea_delete([earoot,'tmp',filesep,'hotfix_classic']);
        if ~exist([earoot,'tmp'] ,'dir')
            mkdir([earoot,'tmp']);
        end
        disp('Downloading updated code...');
        try
            webopts=weboptions('Timeout',Inf);
            websave([earoot,'tmp',filesep,'hotfix_classic.zip'],updurl,'id','hotfix_classic',webopts);
        catch
            try
                urlwrite([updurl,'?id=hotfix_classic'],[earoot,'tmp',filesep,'hotfix_classic.zip'],'Timeout',Inf);
            catch
                fprintf(['\nDownload error! You may try to download the file manually from:\n',...
                         '%s\nand then extract it into Lead-DBS installation folder.\n\n'], [updurl,'?id=hotfix_classic']);
                msgbox('Please check the command window for more information.','Download error!','Error')
                return
            end
        end

        disp('Extracting code...');
        try
            unzip([earoot,'tmp',filesep,'hotfix_classic.zip'],[earoot,'tmp',filesep,'hotfix_classic']);
        catch
            system(['unzip -q ',earoot,'tmp',filesep,'hotfix_classic.zip -d ', earoot,'tmp',filesep,'hotfix_classic']);
        end
        delete([earoot,'tmp',filesep,'hotfix_classic.zip']);

        try
            if exist([earoot,'tmp',filesep,'hotfix_classic',filesep,'DELETE'], 'file')
                disp('Deleting outdated code...');
                dels = readlines([earoot,'tmp',filesep,'hotfix_classic',filesep,'DELETE']);
                ea_delete(cellstr(dels));
                delete([earoot,'tmp',filesep,'hotfix_classic',filesep,'DELETE'])
            end
        catch
            disp('Error while deleting some files. You may ignore this.');
        end

        disp('Copying new code...');
        copyfile([earoot,'tmp',filesep,'hotfix_classic',filesep,'*'],earoot,'f');
        disp('Cleaning up...');
        rmdir([earoot,'tmp'],'s')
        disp('Done.');

        disp('Restarting LEAD.');
        close all force
        lead;
        success=1;
        disp('*** Update finished.');
    catch
        info=sprintf(['Patch does not exist or failed to install development version of Lead!\n',...
                      'Please wait for the next release.']);
        disp(info);
        msgbox(info,'Update','Error');
    end
else
    info=sprintf(['Local version is not applicable to install development version of Lead.\n'...
        'Please upgrade to the latest release (v', web,') first!']);
    disp(info);
    msgbox(info,'Update','Help');
end
