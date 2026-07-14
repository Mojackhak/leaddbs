function path = mh_vta_canonical_leaf_path(task, space)
% Reconstruct one canonical output leaf from a static task definition.

space = char(string(space));
root = fullfile(char(string(task.subject_dir)), 'stimulations', space, ...
    ['phase-', char(string(task.phase_id))], ...
    ['program-', char(string(task.program_id))], ...
    ['electrode-', char(string(task.electrode_id))], ...
    ['frequency-group-', char(string(task.frequency_group_id))]);
switch char(string(task.kind))
    case 'continuous_joint'
        path = fullfile(root, 'delivery-continuous', 'joint');
    case 'alternating_source'
        if numel(task.sources) ~= 1
            error('mh_vta:InvalidCanonicalTask', ...
                'alternating_source tasks must contain exactly one source.');
        end
        path = fullfile(root, 'delivery-alternating', 'sources', ...
            ['source-', char(string(task.sources(1).source_id))]);
    case 'alternating_group_peak'
        path = fullfile(root, 'delivery-alternating', 'derived', 'group-peak');
    otherwise
        error('mh_vta:InvalidCanonicalTask', 'Unsupported task kind.');
end
end
