"""Memory-bounded nearest-neighbor resampling for integer label images."""

from __future__ import annotations

import nibabel as nib
import numpy as np
from scipy.ndimage import affine_transform

from .errors import ResamplingError


def _integer_data(image: nib.spatialimages.SpatialImage) -> np.ndarray:
    data = np.asanyarray(image.dataobj)
    if data.ndim != 3:
        raise ResamplingError("label images must be three-dimensional")
    if not np.all(np.isfinite(data)) or not np.all(data == np.rint(data)):
        raise ResamplingError("source labeling must contain finite integer values")
    minimum = int(np.min(data))
    maximum = int(np.max(data))
    if minimum < 0 or maximum > np.iinfo(np.uint16).max:
        raise ResamplingError("label IDs must fit unsigned 16-bit storage")
    return data.astype(np.uint16, copy=False)


def resample_integer_labels(
    source: nib.spatialimages.SpatialImage,
    reference: nib.spatialimages.SpatialImage,
) -> nib.Nifti1Image:
    """Resample one integer label image onto an exact reference grid."""

    source_data = _integer_data(source)
    if len(reference.shape) != 3:
        raise ResamplingError("reference image must be three-dimensional")
    target_to_source = np.linalg.inv(source.affine) @ reference.affine
    output = affine_transform(
        source_data,
        matrix=target_to_source[:3, :3],
        offset=target_to_source[:3, 3],
        output_shape=tuple(int(item) for item in reference.shape),
        output=np.uint16,
        order=0,
        mode="constant",
        cval=0,
        prefilter=False,
    )
    source_ids = set(int(item) for item in np.unique(source_data))
    output_ids = set(int(item) for item in np.unique(output))
    if not output_ids.issubset(source_ids):
        raise ResamplingError("nearest-neighbor resampling created an unknown label ID")
    header = reference.header.copy()
    header.set_data_dtype(np.uint16)
    result = nib.Nifti1Image(output, reference.affine, header=header)
    qform, qcode = reference.get_qform(coded=True)
    sform, scode = reference.get_sform(coded=True)
    result.set_qform(qform if qform is not None else reference.affine, code=int(qcode))
    result.set_sform(sform if sform is not None else reference.affine, code=int(scode))
    return result
