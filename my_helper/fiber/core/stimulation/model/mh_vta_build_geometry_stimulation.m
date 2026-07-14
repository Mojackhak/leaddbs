function S = mh_vta_build_geometry_stimulation(task, options, sideIndex)
% Build task-specific Lead-DBS stimulation geometry from cached context.

taskId = char(string(task.task_id));
S = ea_initializeS( ...
    ['canonical-', taskId(1:min(12, numel(taskId)))], options);
S.model = 'SimBio/FieldTrip (see Horn 2017)';
S.sources = 1;
sideCode = index_to_side(sideIndex);
sourceField = [sideCode, 's1'];
S.amplitude{sideIndex} = zeros(1, 4);
S.amplitude{sideIndex}(1) = max(double([task.sources.amplitude]));
S.(sourceField).amp = S.amplitude{sideIndex}(1);
S.(sourceField).va = 1;
S.(sourceField).case.perc = 0;
S.(sourceField).case.pol = 0;
for contactIndex = 1:S.numContacts
    contactField = ['k', num2str(contactIndex)];
    S.(sourceField).(contactField).perc = 0;
    S.(sourceField).(contactField).pol = 0;
end
contacts = [task.sources.contacts];
for index = 1:numel(contacts)
    if ischar(contacts(index).contact) || isstring(contacts(index).contact)
        S.(sourceField).case.perc = 100;
        S.(sourceField).case.pol = polarity_code(contacts(index).polarity);
        continue;
    end
    contactField = ['k', num2str(contacts(index).contact)];
    S.(sourceField).(contactField).perc = 100;
    S.(sourceField).(contactField).pol = polarity_code(contacts(index).polarity);
end
S = ea_activecontacts(S);
end

function side = index_to_side(sideIndex)
if sideIndex == 1
    side = 'R';
else
    side = 'L';
end
end

function code = polarity_code(polarity)
if strcmpi(char(string(polarity)), 'cathode')
    code = 1;
else
    code = 2;
end
end
