function tests = test_oss_boundary_contract
% Verify direct OSS boundary construction without legacy stimulation parsing.
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

function testVoltageCaseReturn(testCase)
request = base_request(4, 'voltage', 'continuous');
request.sources = source('case-source', 'voltage', 3, ...
    [contact(1, 'cathode', 1), contact('case', 'anode', 1)]);
locations = [1, 0, 0; 2, 0, 0; 3, 0, 0; 4, 0, 0];

[Phi, currentControl, caseGrounding, center, active] = ...
    mh_oss_assemble_boundary(request, locations);

verifyEqual(testCase, Phi(1), -3);
verifyTrue(testCase, all(isnan(Phi(2:end))));
verifyEqual(testCase, currentControl, 0);
verifyEqual(testCase, caseGrounding, 1);
verifyEqual(testCase, center, [1, 0, 0]);
verifyEqual(testCase, active, 1);
end

function testVoltageElectrodeReturn(testCase)
request = base_request(4, 'voltage', 'continuous');
request.sources = source('electrode-source', 'voltage', 4, ...
    [contact(1, 'cathode', 1), contact(2, 'anode', 1)]);
locations = [0, 0, 0; 2, 0, 0; 4, 0, 0; 6, 0, 0];

[Phi, currentControl, caseGrounding, center, active] = ...
    mh_oss_assemble_boundary(request, locations);

verifyEqual(testCase, Phi(1:2), [-2, 2]);
verifyTrue(testCase, all(isnan(Phi(3:end))));
verifyEqual(testCase, currentControl, 0);
verifyEqual(testCase, caseGrounding, 0);
verifyEqual(testCase, center, [1, 0, 0]);
verifyEqual(testCase, active, [1, 2]);
end

function testVoltageMultipolarContactsUseFullAmplitude(testCase)
request = base_request(4, 'voltage', 'continuous');
request.sources = source('multipolar-source', 'voltage', 3, ...
    [contact(1, 'cathode', 1), contact(2, 'cathode', 1), ...
     contact('case', 'anode', 1)]);

[Phi, currentControl, caseGrounding, ~, active] = ...
    mh_oss_assemble_boundary(request, zeros(4, 3));

verifyEqual(testCase, Phi(1:2), [-3, -3]);
verifyTrue(testCase, all(isnan(Phi(3:end))));
verifyEqual(testCase, currentControl, 0);
verifyEqual(testCase, caseGrounding, 1);
verifyEqual(testCase, active, [1, 2]);
end

function testRejectsFractionalVoltageContact(testCase)
request = base_request(4, 'voltage', 'continuous');
request.sources = source('fractional-source', 'voltage', 3, ...
    [contact(1, 'cathode', 0.5), contact(2, 'cathode', 0.5), ...
     contact('case', 'anode', 1)]);

verifyError(testCase, ...
    @() mh_oss_assemble_boundary(request, zeros(4, 3)), ...
    'mh_oss:InvalidVoltageFraction');
end

function testCurrentSourcesAreSimultaneous(testCase)
request = base_request(5, 'current', 'continuous');
first = source('first', 'current', 4, ...
    [contact(1, 'cathode', 0.25), contact(2, 'cathode', 0.75), ...
     contact(3, 'anode', 1)]);
second = source('second', 'current', 2, ...
    [contact(4, 'cathode', 1), contact('case', 'anode', 1)]);
request.sources = [first, second];
locations = [(1:5)', zeros(5, 2)];

[Phi, currentControl, caseGrounding, center, active] = ...
    mh_oss_assemble_boundary(request, locations);

verifyEqual(testCase, Phi(1:4), [-1, -3, 4, -2]);
verifyTrue(testCase, isnan(Phi(5)));
verifyEqual(testCase, currentControl, 1);
verifyEqual(testCase, caseGrounding, 1);
verifyEqual(testCase, center, [2.7, 0, 0], 'AbsTol', 1e-12);
verifyEqual(testCase, active, 1:4);
end

function testRejectsMixedVoltageTopology(testCase)
request = base_request(4, 'voltage', 'continuous');
request.sources = [source('case-source', 'voltage', 2, ...
    [contact(1, 'cathode', 1), contact('case', 'anode', 1)]), ...
    source('electrode-source', 'voltage', 2, ...
    [contact(2, 'cathode', 1), contact(3, 'anode', 1)])];

verifyError(testCase, ...
    @() mh_oss_assemble_boundary(request, zeros(4, 3)), ...
    'mh_oss:MixedReturnTopology');
end

function testRejectsReusedNumericContact(testCase)
request = base_request(4, 'current', 'continuous');
request.sources = [source('first', 'current', 1, ...
    [contact(1, 'cathode', 1), contact('case', 'anode', 1)]), ...
    source('second', 'current', 1, ...
    [contact(1, 'cathode', 1), contact(2, 'anode', 1)])];

verifyError(testCase, ...
    @() mh_oss_assemble_boundary(request, zeros(4, 3)), ...
    'mh_oss:ReusedNumericContact');
end

function testRejectsCathodicCaseForCurrentControl(testCase)
request = base_request(4, 'current', 'continuous');
request.sources = source('invalid-case-source', 'current', 1, ...
    [contact('case', 'cathode', 1), contact(1, 'anode', 1)]);

verifyError(testCase, ...
    @() mh_oss_assemble_boundary(request, zeros(4, 3)), ...
    'mh_oss:InvalidCaseReturn');
end

function testRejectsInconsistentSourceSettings(testCase)
request = base_request(4, 'current', 'continuous');
request.sources = source('source', 'current', 1, ...
    [contact(1, 'cathode', 1), contact('case', 'anode', 1)]);
request.sources.frequency_hz = 131;

verifyError(testCase, ...
    @() mh_oss_assemble_boundary(request, zeros(4, 3)), ...
    'mh_oss:InconsistentSourceSettings');
end

function testAlternatingRequiresOneSource(testCase)
request = base_request(4, 'current', 'alternating');
one = source('one', 'current', 1, ...
    [contact(1, 'cathode', 1), contact('case', 'anode', 1)]);
two = source('two', 'current', 1, ...
    [contact(2, 'cathode', 1), contact(3, 'anode', 1)]);
request.sources = [one, two];

verifyError(testCase, ...
    @() mh_oss_assemble_boundary(request, zeros(4, 3)), ...
    'mh_oss:InvalidBoundary');
end

function request = base_request(contactCount, mode, deliveryMode)
request = struct( ...
    'contact_count', contactCount, ...
    'control_mode', mode, ...
    'delivery_mode', deliveryMode, ...
    'frequency_hz', 130, ...
    'pulse_width_us', 60, ...
    'sources', struct([]));
end

function value = source(identifier, mode, amplitude, contacts)
value = struct( ...
    'source_id', identifier, ...
    'control_mode', mode, ...
    'amplitude', amplitude, ...
    'frequency_hz', 130, ...
    'pulse_width_us', 60, ...
    'contacts', contacts);
end

function value = contact(identifier, polarity, fraction)
value = struct('contact', identifier, 'polarity', polarity, ...
    'fraction', fraction);
end
