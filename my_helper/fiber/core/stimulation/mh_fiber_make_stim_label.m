function label = mh_fiber_make_stim_label(stimSpec)
% Generate a compact stimulation label from canonical source contacts.

sources = stimSpec.sources;
used = false(numel(sources), 1);
tokens = {};

for i = 1:numel(sources)
    if used(i)
        continue;
    end

    same = false(numel(sources), 1);
    for j = i:numel(sources)
        same(j) = ~used(j) && ...
            strcmp(contact_signature(sources(j)), contact_signature(sources(i))) && ...
            abs(sources(j).amp - sources(i).amp) < 1e-9 && ...
            strcmpi(sources(j).unit, sources(i).unit) && ...
            sources(j).pulseWidth == sources(i).pulseWidth && ...
            sources(j).frequency == sources(i).frequency;
    end

    group = sources(same);
    sides = string({group.side});
    contactToken = label_contact_token(sources(i));
    sidePrefix = '';
    if any(sides == "L")
        sidePrefix = [sidePrefix, 'L', contactToken];
    end
    if any(sides == "R")
        sidePrefix = [sidePrefix, 'R', contactToken];
    end

    tokens{end+1} = [sidePrefix, '_', format_amp(sources(i).amp), sources(i).unit]; %#ok<AGROW>
    used(same) = true;
end

label = ['clinical_', strjoin(tokens, '_')];
label = regexprep(label, '\.', 'p');
label = mh_util_sanitize_label(label, 'PreservePlus', true);

end

function token = label_contact_token(source)
contacts = source.contacts;
if numel(contacts) == 2 && ...
        isnumeric(contacts(1).contact) && strcmp(contacts(1).polarity, 'cathode') && ...
        strcmp(string(contacts(2).contact), "case") && strcmp(contacts(2).polarity, 'anode')
    token = num2str(contacts(1).contact);
    return;
end
token = contact_signature(source);
token = strrep(token, ':', '');
token = strrep(token, '-', '_');
end

function signature = contact_signature(source)
tokens = strings(numel(source.contacts), 1);
for contactIndex = 1:numel(source.contacts)
    contact = source.contacts(contactIndex);
    identifier = string(contact.contact);
    tokens(contactIndex) = identifier + "-" + ...
        extractBefore(string(contact.polarity), 2) + "-" + string(contact.fraction);
end
signature = char(strjoin(tokens, ':'));
end

function out = format_amp(value)
if abs(value - round(value)) < 1e-9
    out = sprintf('%d', round(value));
else
    out = regexprep(sprintf('%.3f', value), '0+$', '');
    out = regexprep(out, '\.$', '');
end
out = strrep(out, '.', 'p');
end
