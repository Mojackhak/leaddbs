function tests = test_oss_map_left_coordinates_to_right
% Verify exact-transform left-to-right geometry canonicalization.
tests = functiontests(localfunctions);
end

function setupOnce(testCase)
modelDirectory = fullfile(fileparts(mfilename('fullpath')), '..', 'core', ...
    'stimulation', 'model');
addpath(modelDirectory);
testCase.TestData.modelDirectory = modelDirectory;
end

function teardownOnce(testCase)
rmpath(testCase.TestData.modelDirectory);
end

function testMirrorsAndUsesConfiguredTransform(testCase)
global MH_OSS_MAP_CAPTURE
MH_OSS_MAP_CAPTURE = struct();
root = tempname;
mkdir(root);
transformPath = fullfile(root, 'configured_transform.nii.gz');
write_text(transformPath, 'transform');
cleanup = onCleanup(@() cleanup_fixture(root));

settings = struct();
settings.contactLocation = {zeros(2, 3), [1, 2, 3; 4, 5, 6]};
settings.Implantation_coordinate = [zeros(1, 3); 7, 8, 9];
settings.Second_coordinate = [zeros(1, 3); 10, 11, 12];
settings.headMNI = [zeros(1, 3); 13, 14, 15];
settings.yMarkerMNI = [zeros(1, 3); 16, 17, 18];

mapped = mh_oss_map_left_coordinates_to_right( ...
    settings, transformPath, @capture_mapper);

shift = [10, 20, 30];
verifyEqual(testCase, mapped.contactLocation{1}, ...
    [-1, 2, 3; -4, 5, 6] + shift);
verifyEqual(testCase, mapped.Implantation_coordinate(1, :), [-7, 8, 9] + shift);
verifyEqual(testCase, mapped.Second_coordinate(1, :), [-10, 11, 12] + shift);
verifyEqual(testCase, mapped.headMNI(1, :), [-13, 14, 15] + shift);
verifyEqual(testCase, mapped.yMarkerMNI(1, :), [-16, 17, 18] + shift);
verifyEqual(testCase, MH_OSS_MAP_CAPTURE.transform, transformPath);
verifyEqual(testCase, MH_OSS_MAP_CAPTURE.points, ...
    [-1, 2, 3; -4, 5, 6; -7, 8, 9; -10, 11, 12; ...
     -13, 14, 15; -16, 17, 18]);
clear cleanup;
end

function mapped = capture_mapper(points, transformPath)
global MH_OSS_MAP_CAPTURE
MH_OSS_MAP_CAPTURE.points = points;
MH_OSS_MAP_CAPTURE.transform = transformPath;
mapped = points + [10, 20, 30];
end

function write_text(path, content)
[fileId, message] = fopen(path, 'w');
if fileId < 0
    error('test_oss:WriteFailed', 'Could not create %s: %s', path, message);
end
cleanup = onCleanup(@() fclose(fileId));
fprintf(fileId, '%s', content);
clear cleanup;
end

function cleanup_fixture(root)
global MH_OSS_MAP_CAPTURE
MH_OSS_MAP_CAPTURE = struct();
if isfolder(root)
    rmdir(root, 's');
end
end
