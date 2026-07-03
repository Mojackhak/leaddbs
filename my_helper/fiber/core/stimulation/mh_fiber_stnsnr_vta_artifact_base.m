function baseLabel = mh_fiber_stnsnr_vta_artifact_base(patientName, phase, protocol, sideCode, thresholdLabel, varargin)
% Build a stable STN/SNr VTA coverage artifact basename.

parser = inputParser;
parser.FunctionName = 'mh_fiber_stnsnr_vta_artifact_base';
parser.addParameter('Target', '', @(x) ischar(x) || isstring(x));
parser.parse(varargin{:});
opts = parser.Results;

if strlength(string(opts.Target)) == 0
    rawLabel = sprintf('%s_phase-%s_protocol-%s_hemi-%s_thr-%s', ...
        char(string(patientName)), char(string(phase)), char(string(protocol)), ...
        char(string(sideCode)), char(string(thresholdLabel)));
else
    rawLabel = sprintf('%s_phase-%s_protocol-%s_hemi-%s_target-%s_thr-%s', ...
        char(string(patientName)), char(string(phase)), char(string(protocol)), ...
        char(string(sideCode)), char(string(opts.Target)), char(string(thresholdLabel)));
end

baseLabel = mh_util_sanitize_label(rawLabel);
end
