function task = mh_vta_make_compute_task(cfg, stimFolders, sideCode, request)
% Build one atomic VTA compute task for a stimulation label and side.

if nargin < 4 || isempty(request)
    request = struct();
end

sideCode = upper(char(string(sideCode)));
mh_util_side_to_index(sideCode, 'mh_vta_make_compute_task:InvalidSide');

if ~isfield(request, 'modelKey') || strlength(string(request.modelKey)) == 0
    if isfield(cfg, 'vta') && isfield(cfg.vta, 'modelKey')
        request.modelKey = cfg.vta.modelKey;
    else
        request.modelKey = mh_vta_default_model_key();
    end
end
request.stimFolders = stimFolders;
request.sides = {sideCode};

vta = mh_fiber_vta_paths(cfg, stimFolders);

task = struct();
task.stim_label = cfg.stimLabel;
task.patient_name = cfg.patientName;
task.subject_id = cfg.subjectId;
task.side = sideCode;
task.model_key = char(string(request.modelKey));
task.stim_folder_mni = stimFolders.mni;
task.stim_folder_native = stimFolders.native;
task.efield_mni = vta.mni.(sideCode).efieldNii;
task.binary_mni = vta.mni.(sideCode).binaryNii;
task.efield_native = vta.native.(sideCode).efieldNii;
task.binary_native = vta.native.(sideCode).binaryNii;
task.request = request;
end
