function jobSpec = mh_fiber_dwi_bids_jobspec(studyRoot, subjectId, varargin)
% Build one Lead-DBS/BIDS DWI processing job specification.

parser = inputParser;
parser.FunctionName = 'mh_fiber_dwi_bids_jobspec';
parser.addRequired('studyRoot', @(x) ischar(x) || isstring(x));
parser.addRequired('subjectId', @(x) ischar(x) || isstring(x));
parser.addParameter('DerivativesRoot', '', @(x) ischar(x) || isstring(x));
parser.addParameter('CoregistrationTag', 'dwi_t2', @(x) ischar(x) || isstring(x));
parser.addParameter('AnchorModality', 'T2w', @(x) ischar(x) || isstring(x));
parser.addParameter('AllowT1Fallback', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('SourceBase', '', @(x) ischar(x) || isstring(x));
parser.addParameter('RequireT1', false, @(x) islogical(x) || isnumeric(x));
parser.parse(studyRoot, subjectId, varargin{:});
opts = parser.Results;

studyRoot = char(string(studyRoot));
subjectId = char(string(subjectId));
derivativesRoot = char(string(opts.DerivativesRoot));
if isempty(derivativesRoot)
    derivativesRoot = fullfile(studyRoot, 'derivatives', 'leaddbs');
end

coregistrationTag = char(string(opts.CoregistrationTag));
anchorModality = normalize_anchor_modality(opts.AnchorModality);
allowT1Fallback = logical(opts.AllowT1Fallback);
requireT1 = logical(opts.RequireT1);

paths = resolve_subject_paths(studyRoot, subjectId, derivativesRoot, coregistrationTag);
jobSpec = struct();
jobSpec.subjectId = subjectId;
jobSpec.sourceBase = char(string(opts.SourceBase));
jobSpec.studyRoot = studyRoot;
jobSpec.derivativesRoot = derivativesRoot;
jobSpec.anchorModality = anchorModality;
jobSpec.coregistrationTag = coregistrationTag;
jobSpec.paths = paths;
jobSpec.anchorAnat = resolve_anchor_anat(paths.subjectDir, anchorModality, allowT1Fallback);
jobSpec.t1Anat = resolve_optional_t1(paths.subjectDir, requireT1);
jobSpec.normalizationForward = resolve_anchor_to_mni_transform(paths.subjectDir, paths.patientName);
end

function paths = resolve_subject_paths(studyRoot, subjectId, derivativesRoot, coregistrationTag)
patientName = ['sub-', subjectId];
subjectDir = fullfile(derivativesRoot, patientName);
rawDwiDir = fullfile(studyRoot, 'rawdata', patientName, 'ses-preop', 'dwi');
dwiDir = fullfile(subjectDir, 'preprocessing', 'dwi');
coregDir = fullfile(subjectDir, 'coregistration', coregistrationTag);
qcDir = fullfile(subjectDir, 'qc', qc_tag_from_coreg_tag(coregistrationTag));

rawBase = [patientName, '_ses-preop_dwi'];
paths = struct();
paths.subjectId = subjectId;
paths.patientName = patientName;
paths.subjectDir = subjectDir;
paths.rawDwiDir = rawDwiDir;
paths.rawDwiGz = fullfile(rawDwiDir, [rawBase, '.nii.gz']);
paths.rawDwiNii = fullfile(rawDwiDir, [rawBase, '.nii']);
paths.rawJson = fullfile(rawDwiDir, [rawBase, '.json']);
paths.rawBval = fullfile(rawDwiDir, [rawBase, '.bval']);
paths.rawBvec = fullfile(rawDwiDir, [rawBase, '.bvec']);
paths.dwiDir = dwiDir;
paths.coregDir = coregDir;
paths.coregAnatDir = fullfile(subjectDir, 'coregistration', 'anat');
paths.coregTag = coregistrationTag;
paths.qcDir = qcDir;
paths.dwi = fullfile(dwiDir, [rawBase, '.nii']);
paths.json = fullfile(dwiDir, [rawBase, '.json']);
paths.bval = fullfile(dwiDir, [rawBase, '.bval']);
paths.bvec = fullfile(dwiDir, [rawBase, '.bvec']);
paths.b0 = fullfile(dwiDir, [rawBase, '_b0.nii']);
paths.fakeB0Coreg = fullfile(paths.coregAnatDir, ...
    [patientName, '_ses-preop_space-anchorNative_desc-preproc_B0.nii']);
paths.fa = fullfile(dwiDir, [rawBase, '_fa.nii']);
paths.faOnAnchor = '';
paths.brainMask = fullfile(dwiDir, 'brainmask.nii');
paths.trackingMask = fullfile(dwiDir, 'trackingmask.nii');
end

function anchorAnat = resolve_anchor_anat(subjectDir, anchorModality, allowT1Fallback)
anatDir = fullfile(subjectDir, 'coregistration', 'anat');
patterns = anchor_patterns(anchorModality);
for p = 1:numel(patterns)
    d = dir(fullfile(anatDir, patterns{p}));
    d = d(~startsWith({d.name}, '._'));
    if ~isempty(d)
        [~, order] = sort({d.name});
        d = d(order);
        anchorAnat = fullfile(d(1).folder, d(1).name);
        return;
    end
end
if allowT1Fallback && ~strcmp(anchorModality, 'T1w')
    anchorAnat = resolve_anchor_anat(subjectDir, 'T1w', false);
    return;
end
error('No anchorNative %s found in %s', anchorModality, anatDir);
end

function t1Anat = resolve_optional_t1(subjectDir, requireT1)
try
    t1Anat = resolve_anchor_anat(subjectDir, 'T1w', false);
catch ME
    if requireT1
        rethrow(ME);
    end
    t1Anat = '';
end
end

function transformPath = resolve_anchor_to_mni_transform(subjectDir, patientName)
transformPath = fullfile(subjectDir, 'normalization', 'transformations', ...
    [patientName, '_from-anchorNative_to-MNI152NLin2009bAsym_desc-ants.nii.gz']);
if ~isfile(transformPath)
    d = dir(fullfile(subjectDir, 'normalization', 'transformations', ...
        '*from-anchorNative_to-MNI152NLin2009bAsym_desc-ants.nii.gz'));
    d = d(~startsWith({d.name}, '._'));
    if ~isempty(d)
        transformPath = fullfile(d(1).folder, d(1).name);
    end
end
if ~isfile(transformPath)
    transformPath = '';
end
end

function anchorModality = normalize_anchor_modality(anchorModality)
anchorModality = char(string(anchorModality));
switch lower(anchorModality)
    case {'t1', 't1w'}
        anchorModality = 'T1w';
    case {'t2', 't2w'}
        anchorModality = 'T2w';
    otherwise
        error('Unsupported AnchorModality: %s. Use T1w or T2w.', anchorModality);
end
end

function patterns = anchor_patterns(anchorModality)
patterns = { ...
    ['*space-anchorNative_desc-preproc*acq-iso*', anchorModality, '.nii'], ...
    ['*space-anchorNative_desc-preproc*acq-ax*', anchorModality, '.nii'], ...
    ['*space-anchorNative_desc-preproc*_', anchorModality, '.nii'], ...
    ['*', anchorModality, '.nii']};
end

function qcTag = qc_tag_from_coreg_tag(coregTag)
if strcmp(coregTag, 'dwi')
    qcTag = 'dwi_registration';
else
    suffix = regexprep(coregTag, '^dwi', '');
    qcTag = ['dwi_registration', suffix];
end
end
