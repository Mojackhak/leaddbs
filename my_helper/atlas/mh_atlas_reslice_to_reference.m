function mh_atlas_reslice_to_reference(inputPath, referencePath, outputPath)
% Reslice a mask to a reference image grid using nearest-neighbor MRtrix regrid.

inputPath = char(string(inputPath));
referencePath = char(string(referencePath));
outputPath = char(string(outputPath));

if ~isfile(inputPath)
    error('mh_atlas_reslice_to_reference:MissingInput', 'Input does not exist: %s', inputPath);
end
if ~isfile(referencePath)
    error('mh_atlas_reslice_to_reference:MissingReference', 'Reference does not exist: %s', referencePath);
end

outDir = fileparts(outputPath);
if ~isfolder(outDir)
    mkdir(outDir);
end

cmd = sprintf('mrgrid %s regrid %s -template %s -interp nearest -force -quiet', ...
    shell_quote(inputPath), shell_quote(outputPath), shell_quote(referencePath));
[status, output] = system(cmd);
if status ~= 0
    error('mh_atlas_reslice_to_reference:CommandFailed', ...
        'Command failed:\n%s\n\n%s', cmd, output);
end
end

function q = shell_quote(path)
path = char(string(path));
q = ['''', strrep(path, '''', '''"''"'''), ''''];
end
