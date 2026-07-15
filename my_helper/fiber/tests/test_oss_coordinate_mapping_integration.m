function tests = test_oss_coordinate_mapping_integration
% Compare canonical OSS point mapping with the Lead-DBS reference helper.
tests = functiontests(localfunctions);
end

function testMatchesEaFlipLrNonlinearForAsymmetricPoints(testCase)
testDirectory = fileparts(mfilename('fullpath'));
repositoryRoot = fileparts(fileparts(fileparts(testDirectory)));
modelDirectory = fullfile(repositoryRoot, 'my_helper', 'fiber', 'core', ...
    'stimulation', 'model');
transformPath = fullfile(repositoryRoot, 'templates', 'space', ...
    'MNI152NLin2009bAsym', 'fliplr', 'InverseComposite.nii.gz');
assumeTrue(testCase, isfile(transformPath));
addpath(modelDirectory);
cleanup = onCleanup(@() rmpath(modelDirectory));

contacts = [-10.5, -16.25, -2.0; -11.75, -19.5, -5.25];
implantation = [-9.25, -14.0, 1.5];
second = [-12.5, -22.0, -7.0];
head = [-8.75, -11.5, 4.0];
yMarker = [-13.0, -17.75, 0.25];
allPoints = [contacts; implantation; second; head; yMarker];

settings = struct();
settings.contactLocation = {zeros(size(contacts)), contacts};
settings.Implantation_coordinate = [zeros(1, 3); implantation];
settings.Second_coordinate = [zeros(1, 3); second];
settings.headMNI = [zeros(1, 3); head];
settings.yMarkerMNI = [zeros(1, 3); yMarker];

mapped = mh_oss_map_left_coordinates_to_right( ...
    settings, transformPath);
actual = [mapped.contactLocation{1}; ...
    mapped.Implantation_coordinate(1, :); ...
    mapped.Second_coordinate(1, :); ...
    mapped.headMNI(1, :); ...
    mapped.yMarkerMNI(1, :)];
expected = ea_flip_lr_nonlinear(allPoints);

verifyEqual(testCase, actual, expected, 'AbsTol', 1e-4);
clear cleanup;
end
