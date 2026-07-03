function path = mh_fiber_vta_efield_path(subjectDir, patientName, stimLabel, sideCode, varargin)
% Return a standard VTA e-field NIfTI path for one stimulation label and side.

parser = inputParser;
parser.FunctionName = 'mh_fiber_vta_efield_path';
parser.addParameter('Space', 'mni', @(x) ischar(x) || isstring(x));
parser.addParameter('Model', 'SimBio/FieldTrip (see Horn 2017)', @(x) ischar(x) || isstring(x));
parser.parse(varargin{:});
opts = parser.Results;

sideCode = upper(char(string(sideCode)));
mh_util_side_to_index(sideCode, 'mh_fiber_vta_efield_path:InvalidSide');

stimFolders = struct();
stimFolders.mni = fullfile(char(string(subjectDir)), 'stimulations', ea_nt(0), char(string(stimLabel)));
stimFolders.native = fullfile(char(string(subjectDir)), 'stimulations', 'native', char(string(stimLabel)));

cfg = struct();
cfg.patientName = char(string(patientName));
cfg.vta = struct('model', char(string(opts.Model)));

vta = mh_fiber_vta_paths(cfg, stimFolders);
space = lower(char(string(opts.Space)));
if ~isfield(vta, space)
    error('mh_fiber_vta_efield_path:InvalidSpace', 'Unsupported VTA output space: %s', space);
end
path = vta.(space).(sideCode).efieldNii;
end
