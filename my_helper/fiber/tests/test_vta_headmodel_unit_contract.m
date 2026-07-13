function tests = test_vta_headmodel_unit_contract
% Validate canonical mesh/volume coordinate units before FEM execution.

tests = functiontests(localfunctions);
end

function setupOnce(testCase)
repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(fullfile(repoDir, 'my_helper', 'fiber')));
testCase.TestData.repoDir = repoDir;
end

function testAcceptsDoubleCoordinatesWithoutUnitField(testCase)
[vol, mesh] = valid_fixture('double', false);
mh_vta_validate_canonical_headmodel_units(vol, mesh);
verifyTrue(testCase, true);
end

function testAcceptsSingleCoordinatesWithMillimeterUnit(testCase)
[vol, mesh] = valid_fixture('single', true);
mh_vta_validate_canonical_headmodel_units(vol, mesh);
verifyTrue(testCase, true);
end

function testRejectsVolumeCoordinatesStoredInMillimeters(testCase)
[vol, mesh] = valid_fixture('double', true);
vol.pos = double(mesh.pnt);
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, mesh), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
end

function testRejectsPresentNonMillimeterUnit(testCase)
[vol, mesh] = valid_fixture('double', true);
mesh.unit = 'm';
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, mesh), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
end

function testRejectsJointlyMisScaledCoordinatesOutsideRange(testCase)
mesh = struct('pnt', [0, 0, 0; 3000, 0, 0], 'unit', 'mm');
vol = struct('pos', double(mesh.pnt) / 1000);
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, mesh), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
end

function testRejectsNonfiniteCoordinates(testCase)
[vol, mesh] = valid_fixture('double', true);
vol.pos(1, 1) = Inf;
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, mesh), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
end

function testRejectsCoordinateShapeAndNodeCountMismatch(testCase)
[vol, mesh] = valid_fixture('double', true);
invalidShape = mesh;
invalidShape.pnt = zeros(2, 2);
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, invalidShape), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
fewerNodes = mesh;
fewerNodes.pnt = fewerNodes.pnt(1:2, :);
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, fewerNodes), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
end

function testRejectsNonscalarVolumeStruct(testCase)
[vol, mesh] = valid_fixture('double', true);
vol = repmat(vol, 1, 2);
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, mesh), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
end

function testRejectsNonscalarMeshStruct(testCase)
[vol, mesh] = valid_fixture('double', true);
mesh = repmat(mesh, 1, 2);
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, mesh), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
end

function testAcceptsMismatchExactlyAtTolerance(testCase)
[vol, mesh] = valid_fixture('double', true);
vol.pos(1, 1) = vol.pos(1, 1) + 1e-6;
mh_vta_validate_canonical_headmodel_units(vol, mesh);
verifyTrue(testCase, true);
end

function testRejectsMismatchAboveTolerance(testCase)
[vol, mesh] = valid_fixture('double', true);
vol.pos(1, 1) = vol.pos(1, 1) + 1.0001e-6;
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, mesh), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
end

function testAcceptsPositionSlightlyBelowAbsoluteBound(testCase)
vol = struct('pos', [2 - 1e-6, 0, 0]);
mesh = struct('pnt', vol.pos * 1000, 'unit', 'mm');
mh_vta_validate_canonical_headmodel_units(vol, mesh);
verifyTrue(testCase, true);
end

function testRejectsPositionExactlyAtAbsoluteBound(testCase)
vol = struct('pos', [2, 0, 0]);
mesh = struct('pnt', vol.pos * 1000, 'unit', 'mm');
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, mesh), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
end

function [vol, mesh] = valid_fixture(precision, includeUnit)
pointsMm = cast([0, 0, 0; 10, -20, 30; -40, 50, -60], precision);
mesh = struct('pnt', pointsMm);
if includeUnit
    mesh.unit = 'mm';
end
vol = struct('pos', cast(double(pointsMm) / 1000, precision));
end
