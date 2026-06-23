# Lead-DBS Conda Environment

This document describes the `leaddbs` conda environment used for Python-based helper workflows in this repository. The environment is intended for image I/O, basic data processing, neuroimaging, EEG/MEG analysis with MNE, MNE connectivity analysis, and DTI/Fiber processing with DIPY.

The environment file is stored at:

```bash
/Users/mojackhu/Github/leaddbs/my_helper/env/environment-leaddbs.yml
```

## Package Scope

The environment includes:

- Basic data processing: NumPy, SciPy, pandas, scikit-learn, statsmodels, h5py, openpyxl, tqdm
- Image reading, writing, and processing: Pillow, imageio, OpenCV, scikit-image, matplotlib, seaborn
- Neuroimaging: nibabel, nilearn
- EEG/MEG processing: MNE
- Connectivity analysis: mne-connectivity
- DTI/Fiber processing: DIPY
- Notebook tools: JupyterLab and IPython kernel support

`mrtrix3` is not included in this conda environment. On the current `osx-arm64` platform, `mrtrix3` is not available from the configured conda channels, so the environment uses DIPY as the DTI/Fiber processing library.

## Create Or Update

Create the environment:

```bash
conda env create -f /Users/mojackhu/Github/leaddbs/my_helper/env/environment-leaddbs.yml
```

Update an existing environment:

```bash
conda env update -n leaddbs -f /Users/mojackhu/Github/leaddbs/my_helper/env/environment-leaddbs.yml --prune
```

Activate the environment:

```bash
conda activate leaddbs
```

Register the Jupyter kernel:

```bash
conda run -n leaddbs python -m ipykernel install --user --name leaddbs --display-name "Python (leaddbs)"
```

## Verification

Check that the environment exists:

```bash
conda env list | rg 'leaddbs'
```

Run the import and smoke checks:

```bash
conda run -n leaddbs python - <<'PY'
import tempfile
from pathlib import Path

import cv2
import dipy
import imageio.v3 as iio
import matplotlib
import mne
import mne_connectivity
import nibabel
import nilearn
import numpy as np
import pandas as pd
import scipy
import seaborn
import skimage
import sklearn
import statsmodels
from PIL import Image
from dipy.io import streamline
from dipy.reconst import dti
from dipy import tracking

with tempfile.TemporaryDirectory() as tmpdir:
    path = Path(tmpdir) / "smoke.png"
    data = (np.arange(64, dtype=np.uint8).reshape(8, 8))
    Image.fromarray(data).save(path)
    loaded = iio.imread(path)
    assert loaded.shape == data.shape

print("leaddbs environment smoke check passed")
PY
```

Check that the Jupyter kernel is registered:

```bash
jupyter kernelspec list | rg 'leaddbs'
```
