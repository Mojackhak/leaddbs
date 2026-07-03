function categories = mh_coverage_classify_membership(vtaMask, regionMasks)
% Partition VTA voxels by membership in an arbitrary set of region masks.

regionCount = numel(regionMasks);
if regionCount < 1
    error('mh_coverage_classify_membership:MissingRegions', ...
        'At least one region mask is required.');
end

categoryCount = 2^regionCount;
names = cell(categoryCount, 1);
fieldNames = cell(categoryCount, 1);
denominators = nan(categoryCount, 1);
categoryImg = zeros(size(vtaMask), 'uint16');

for combo = 1:(categoryCount - 1)
    comboMask = vtaMask;
    denomMask = true(size(vtaMask));
    comboNames = {};
    for r = 1:regionCount
        inCombo = bitget(combo, r) == 1;
        if inCombo
            comboMask = comboMask & regionMasks(r).mask;
            denomMask = denomMask & regionMasks(r).mask;
            comboNames{end+1} = regionMasks(r).name; %#ok<AGROW>
        else
            comboMask = comboMask & ~regionMasks(r).mask;
            denomMask = denomMask & ~regionMasks(r).mask;
        end
    end
    if numel(comboNames) == 1
        name = [comboNames{1}, '_only'];
    else
        name = strjoin(comboNames, '_');
    end
    fieldName = matlab.lang.makeValidName(mh_util_sanitize_label(name));
    names{combo} = name;
    fieldNames{combo} = fieldName;
    denominators(combo) = nnz(denomMask);
    categories.(fieldName) = comboMask;
    categoryImg(comboMask) = uint16(combo);
end

outsideMask = vtaMask;
for r = 1:regionCount
    outsideMask = outsideMask & ~regionMasks(r).mask;
end
outsideIdx = categoryCount;
names{outsideIdx} = 'Outside';
fieldNames{outsideIdx} = 'Outside';
categories.Outside = outsideMask;
categoryImg(outsideMask) = uint16(outsideIdx);

categories.names = names;
categories.field_names = fieldNames;
categories.denominators = denominators;
categories.categoryImg = categoryImg;
categories.region_names = {regionMasks.name}';
end
