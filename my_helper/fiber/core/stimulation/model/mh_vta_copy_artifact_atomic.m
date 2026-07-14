function copied = mh_vta_copy_artifact_atomic(sourcePath, destinationPath)
% Copy one existing donor artifact without overwriting a destination.

sourcePath = char(string(sourcePath));
destinationPath = char(string(destinationPath));
if isfile(destinationPath) || ~isfile(sourcePath)
    copied = false;
    return;
end
copied = mh_vta_publish_atomic(destinationPath, ...
    @(temporaryPath) copy_to_temporary(sourcePath, temporaryPath));
end

function copy_to_temporary(sourcePath, temporaryPath)
[ok, message] = copyfile(sourcePath, temporaryPath);
if ~ok
    error('mh_vta_copy_artifact_atomic:CopyFailed', ...
        'Could not copy donor artifact: %s', message);
end
end
