function mh_util_make_dir(path)
% Create a directory if it does not already exist.

if ~isfolder(path)
    mkdir(path);
end
end
