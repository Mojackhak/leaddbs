function tests = test_vta_canonical_options_contract
% Validate fixed internal options used by the canonical VTA backend.

tests = functiontests(localfunctions);
end

function setupOnce(testCase)
repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(fullfile(repoDir, 'my_helper', 'fiber')));
testCase.TestData.repoDir = repoDir;
end

function testCanonicalGeometryUsesPatientAtlasMaskSurface(testCase)
options = struct( ...
    'prefs', struct( ...
        'vat', struct('gm', 'atlas'), ...
        'machine', struct('vatsettings', struct())), ...
    'atlasset', 'legacy-atlas');
task = struct('model', struct( ...
    'atlas_set', 'Custom_Ewert_Zhang_Middlebrooks', ...
    'gray_matter_s_per_m', 0.33, ...
    'white_matter_s_per_m', 0.14));

configured = mh_vta_configure_canonical_options(options, task);

verifyEqual(testCase, string(configured.atlasset), ...
    "Custom_Ewert_Zhang_Middlebrooks");
verifyEqual(testCase, string(configured.prefs.vat.gm), "mask");
settings = configured.prefs.machine.vatsettings;
verifyEqual(testCase, settings.horn_useatlas, 1);
verifyEqual(testCase, string(settings.horn_atlasset), ...
    "Custom_Ewert_Zhang_Middlebrooks");
verifyEqual(testCase, settings.horn_cgm, 0.33, 'AbsTol', 1e-12);
verifyEqual(testCase, settings.horn_cwm, 0.14, 'AbsTol', 1e-12);
verifyEqual(testCase, settings.horn_removeElectrode, 1);
end
