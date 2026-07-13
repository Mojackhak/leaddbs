function published = mh_vta_publish_atomic(outputPath, producer)
% Publish one missing output through a temporary file in its destination.

outputPath = char(string(outputPath));
if isfile(outputPath)
    published = false;
    return;
end
if ~isa(producer, 'function_handle')
    error('mh_vta_publish_atomic:InvalidProducer', ...
        'producer must be a function handle.');
end
outputDir = fileparts(outputPath);
if ~isfolder(outputDir)
    mkdir(outputDir);
end
temporaryPath = [tempname(outputDir), '.nii.gz'];
cleanup = onCleanup(@() delete_if_present(temporaryPath));
producer(temporaryPath);
if ~isfile(temporaryPath)
    error('mh_vta_publish_atomic:MissingTemporaryOutput', ...
        'Producer did not create its temporary output: %s', temporaryPath);
end
if isfile(outputPath)
    published = false;
    return;
end
[ok, message] = movefile(temporaryPath, outputPath);
if ~ok
    error('mh_vta_publish_atomic:PublishFailed', ...
        'Could not publish %s: %s', outputPath, message);
end
published = true;
clear cleanup;
end

function delete_if_present(path)
if isfile(path)
    delete(path);
end
end
