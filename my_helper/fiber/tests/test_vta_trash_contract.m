function tests = test_vta_trash_contract
% Contract tests for recoverable canonical VTA replacement.

tests = functiontests(localfunctions);
end

function setupOnce(testCase)
repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(fullfile(repoDir, 'my_helper', 'fiber')));
end

function testFileMovesWithoutChangingContents(testCase)
root = tempname;
trashRoot = fullfile(root, 'trash');
mkdir(root);
cleanup = onCleanup(@() cleanup_root(root));
source = fullfile(root, 'headmodel.mat');
fid = fopen(source, 'w');
assert(fid > 0);
fileCleanup = onCleanup(@() fclose(fid));
fwrite(fid, uint8(1:32), 'uint8');
clear fileCleanup;
expectedHash = mh_fiber_file_sha256(source);

destination = mh_vta_move_path_to_trash(source, 'TrashRoot', trashRoot);

verifyFalse(testCase, isfile(source));
verifyTrue(testCase, isfile(destination));
verifyEqual(testCase, mh_fiber_file_sha256(destination), expectedHash);
verifyTrue(testCase, startsWith(destination, trashRoot));
end

function testMissingPathIsNoOp(testCase)
destination = mh_vta_move_path_to_trash([tempname '.missing']);
verifyEqual(testCase, destination, '');
end

function testRepeatedMovesUseDistinctDestinations(testCase)
root = tempname;
trashRoot = fullfile(root, 'trash');
mkdir(root);
cleanup = onCleanup(@() cleanup_root(root));
first = fullfile(root, 'same-name.mat');
secondRoot = fullfile(root, 'other');
mkdir(secondRoot);
second = fullfile(secondRoot, 'same-name.mat');
write_bytes(first, uint8(1:4));
write_bytes(second, uint8(5:8));

firstDestination = mh_vta_move_path_to_trash( ...
    first, 'TrashRoot', trashRoot);
secondDestination = mh_vta_move_path_to_trash( ...
    second, 'TrashRoot', trashRoot);

verifyNotEqual(testCase, firstDestination, secondDestination);
verifyEqual(testCase, read_bytes(firstDestination), uint8((1:4)'));
verifyEqual(testCase, read_bytes(secondDestination), uint8((5:8)'));
end

function write_bytes(path, values)
fid = fopen(path, 'w');
assert(fid > 0);
cleanup = onCleanup(@() fclose(fid));
fwrite(fid, values, 'uint8');
end

function values = read_bytes(path)
fid = fopen(path, 'r');
assert(fid > 0);
cleanup = onCleanup(@() fclose(fid));
values = fread(fid, inf, '*uint8');
end

function cleanup_root(root)
if isfolder(root)
    rmdir(root, 's');
end
end
