function label = mh_fiber_make_stim_label(stimSpec)
% Generate a compact stimulation label from bilateral monopolar sources.

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
            sources(j).contact == sources(i).contact && ...
            abs(sources(j).amp - sources(i).amp) < 1e-9 && ...
            strcmpi(sources(j).unit, sources(i).unit) && ...
            sources(j).pulseWidth == sources(i).pulseWidth && ...
            sources(j).frequency == sources(i).frequency;
    end

    group = sources(same);
    sides = string({group.side});
    sidePrefix = '';
    if any(sides == "L")
        sidePrefix = [sidePrefix, 'L', num2str(sources(i).contact)];
    end
    if any(sides == "R")
        sidePrefix = [sidePrefix, 'R', num2str(sources(i).contact)];
    end

    tokens{end+1} = [sidePrefix, '_', format_amp(sources(i).amp), sources(i).unit]; %#ok<AGROW>
    used(same) = true;
end

label = ['clinical_', strjoin(tokens, '_')];
label = regexprep(label, '\.', 'p');
label = regexprep(label, '[^A-Za-z0-9_+-]+', '_');
label = regexprep(label, '_+', '_');
label = regexprep(label, '^_|_$', '');

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
