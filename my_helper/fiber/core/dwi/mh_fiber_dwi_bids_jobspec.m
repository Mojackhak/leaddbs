function jobSpec = mh_fiber_dwi_bids_jobspec(studyRoot, subjectId, varargin)
% Build one Lead-DBS/BIDS DWI processing job specification.

parser = inputParser;
parser.FunctionName = 'mh_fiber_dwi_bids_jobspec';
parser.addRequired('studyRoot', @(x) ischar(x) || isstring(x));
parser.addRequired('subjectId', @(x) ischar(x) || isstring(x));
parser.addParameter('Session', 'preop', @(x) ischar(x) || isstring(x));
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
sourceBase = char(string(opts.SourceBase));
session = normalize_session(opts.Session);

paths = resolve_subject_paths(studyRoot, subjectId, derivativesRoot, ...
    coregistrationTag, sourceBase, session);
jobSpec = struct();
jobSpec.subjectId = subjectId;
jobSpec.session = session;
jobSpec.sourceBase = paths.rawBase;
jobSpec.studyRoot = studyRoot;
jobSpec.derivativesRoot = derivativesRoot;
jobSpec.anchorModality = anchorModality;
jobSpec.coregistrationTag = coregistrationTag;
jobSpec.paths = paths;
jobSpec.anchorAnat = resolve_anchor_anat(paths.subjectDir, anchorModality, ...
    allowT1Fallback, paths.sessionLabel);
jobSpec.t1Anat = resolve_optional_t1(paths.subjectDir, requireT1, paths.sessionLabel);
jobSpec.normalizationForward = resolve_anchor_to_mni_transform(paths.subjectDir, paths.patientName);
end

function paths = resolve_subject_paths(studyRoot, subjectId, derivativesRoot, coregistrationTag, sourceBase, session)
patientName = ['sub-', subjectId];
sessionLabel = ['ses-', session];
subjectDir = fullfile(derivativesRoot, patientName);
rawDwiDir = fullfile(studyRoot, 'rawdata', patientName, sessionLabel, 'dwi');
dwiDir = fullfile(subjectDir, 'preprocessing', 'dwi');
coregDir = fullfile(subjectDir, 'coregistration', coregistrationTag);
qcDir = fullfile(subjectDir, 'qc', qc_tag_from_coreg_tag(coregistrationTag));

rawBase = resolve_raw_dwi_base(rawDwiDir, patientName, sessionLabel, sourceBase);
outputBase = [patientName, '_', sessionLabel, '_dwi'];
paths = struct();
paths.subjectId = subjectId;
paths.patientName = patientName;
paths.session = session;
paths.sessionLabel = sessionLabel;
paths.rawBase = rawBase;
paths.outputBase = outputBase;
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
paths.dwi = fullfile(dwiDir, [outputBase, '.nii']);
paths.json = fullfile(dwiDir, [outputBase, '.json']);
paths.bval = fullfile(dwiDir, [outputBase, '.bval']);
paths.bvec = fullfile(dwiDir, [outputBase, '.bvec']);
paths.b0 = fullfile(dwiDir, [outputBase, '_b0.nii']);
paths.fakeB0Coreg = fullfile(paths.coregAnatDir, ...
    [patientName, '_', sessionLabel, '_space-anchorNative_desc-preproc_B0.nii']);
paths.fa = fullfile(dwiDir, [outputBase, '_fa.nii']);
paths.faOnAnchor = '';
paths.brainMask = fullfile(dwiDir, 'brainmask.nii');
paths.trackingMask = fullfile(dwiDir, 'trackingmask.nii');
end

function rawBase = resolve_raw_dwi_base(rawDwiDir, patientName, sessionLabel, sourceBase)
sourceBase = char(string(sourceBase));
defaultBase = [patientName, '_', sessionLabel, '_dwi'];
gzFiles = dir(fullfile(rawDwiDir, '*_dwi.nii.gz'));
niiFiles = dir(fullfile(rawDwiDir, '*_dwi.nii'));
gzFiles = gzFiles(~startsWith({gzFiles.name}, '._'));
niiFiles = niiFiles(~startsWith({niiFiles.name}, '._'));

candidateNames = [{gzFiles.name}, {niiFiles.name}];
if numel(candidateNames) > 1
    error('mh_fiber_dwi_bids_jobspec:AmbiguousRawDwi', ...
        'Expected one raw DWI NIfTI in %s, found %d files.', ...
        rawDwiDir, numel(candidateNames));
end
if ~isempty(sourceBase)
    rawBase = sourceBase;
    return;
end
if isempty(candidateNames)
    rawBase = defaultBase;
    return;
end
rawBase = strip_dwi_nii_extension(candidateNames{1});
end

function base = strip_dwi_nii_extension(fileName)
base = char(string(fileName));
if endsWith(base, '.nii.gz')
    base = extractBefore(base, strlength(base) - strlength('.nii.gz') + 1);
elseif endsWith(base, '.nii')
    base = extractBefore(base, strlength(base) - strlength('.nii') + 1);
end
base = char(base);
end

function anchorAnat = resolve_anchor_anat(subjectDir, anchorModality, allowT1Fallback, sessionLabel)
anatDir = fullfile(subjectDir, 'coregistration', 'anat');
patterns = anchor_patterns(anchorModality, sessionLabel);
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
    anchorAnat = resolve_anchor_anat(subjectDir, 'T1w', false, sessionLabel);
    return;
end
error('No anchorNative %s found in %s', anchorModality, anatDir);
end

function t1Anat = resolve_optional_t1(subjectDir, requireT1, sessionLabel)
try
    t1Anat = resolve_anchor_anat(subjectDir, 'T1w', false, sessionLabel);
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

function patterns = anchor_patterns(anchorModality, sessionLabel)
patterns = { ...
    ['*_', sessionLabel, '_*space-anchorNative_desc-preproc*acq-iso*', anchorModality, '.nii'], ...
    ['*_', sessionLabel, '_*space-anchorNative_desc-preproc*acq-ax*', anchorModality, '.nii'], ...
    ['*_', sessionLabel, '_*space-anchorNative_desc-preproc*_', anchorModality, '.nii'], ...
    ['*_', sessionLabel, '_*', anchorModality, '.nii']};
end

function session = normalize_session(session)
session = strtrim(char(string(session)));
if startsWith(session, 'ses-')
    error('mh_fiber_dwi_bids_jobspec:InvalidSession', ...
        'Session must not include the ses- prefix: %s', session);
end
if isempty(regexp(session, '^[A-Za-z0-9][A-Za-z0-9._-]*$', 'once'))
    error('mh_fiber_dwi_bids_jobspec:InvalidSession', ...
        'Session contains unsupported BIDS label characters: %s', session);
end
end

function qcTag = qc_tag_from_coreg_tag(coregTag)
if strcmp(coregTag, 'dwi')
    qcTag = 'dwi_registration';
else
    suffix = regexprep(coregTag, '^dwi', '');
    qcTag = ['dwi_registration', suffix];
end
end
