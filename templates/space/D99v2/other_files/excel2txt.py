import pandas as pd

a = pd.read_excel(r"F:\GitHub\anipose_m\Mojackhak\leaddbs\templates\space\D99v2\other_files\D99_hemi_Suppl_Table_1.xlsx", sheet_name="Sheet1")
a['Name'] = (
    a['Name1'].fillna('') + '_' + a['Name2'].fillna('') + '_' + a['Name3'].fillna('')
).str.strip('_')
a['Name'] = (
    a['Name'].fillna('') + '_' + a['Side'].fillna('')).str.strip('_')
a['Name'] = a['Name'].str.replace(' ', '_')
a.iloc[:,[0,5]].to_csv(r"F:\GitHub\anipose_m\Mojackhak\leaddbs\templates\space\D99v2\other_files\D99_hemi_v2.0_labels.txt", sep=' ', index=False, header=False, escapechar=' ')