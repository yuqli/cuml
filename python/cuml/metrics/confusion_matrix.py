#
# Copyright (c) 2020, NVIDIA CORPORATION.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

# cython: profile=False
# distutils: language = c++
# cython: embedsignature = True
# cython: language_level = 3

import numpy as np
import cupy as cp

from cuml.utils import input_to_cuml_array
from cuml.utils.memory_utils import with_cupy_rmm
from cuml.metrics.utils import sorted_unique_labels
from cuml.prims.label import make_monotonic


@with_cupy_rmm
def confusion_matrix(y_true, y_pred,
                     labels=None,
                     sample_weight=None,
                     normalize=None):
    """Compute confusion matrix to evaluate the accuracy of a classification.

    Parameters
    ----------
    y_true : array-like (device or host) shape = (n_samples,)
        or (n_samples, n_outputs)
        Ground truth (correct) target values.
    y_pred : array-like (device or host) shape = (n_samples,)
        or (n_samples, n_outputs)
        Estimated target values.
    labels : array-like (device or host) shape = (n_classes,), optional
        List of labels to index the matrix. This may be used to reorder or
        select a subset of labels. If None is given, those that appear at least
        once in y_true or y_pred are used in sorted order.
    sample_weight : array-like (device or host) shape = (n_samples,), optional
        Sample weights.
    normalize : string in [‘true’, ‘pred’, ‘all’]
        Normalizes confusion matrix over the true (rows), predicted (columns)
        conditions or all the population. If None, confusion matrix will not be
        normalized.

    Returns
    -------
    C : array-like (device or host) shape = (n_classes, n_classes)
        Confusion matrix.
    """
    y_true, n_rows, n_cols, dtype = \
        input_to_cuml_array(y_true, check_dtype=[cp.int32, cp.int64])
    y_true = y_true.to_output('cupy')

    y_pred, _, _, _ = \
        input_to_cuml_array(y_pred, check_dtype=dtype,
                            check_rows=n_rows, check_cols=n_cols)
    y_pred = y_pred.to_output('cupy')

    if labels is None:
        labels = sorted_unique_labels(y_true, y_pred)
        n_labels = len(labels)
    else:
        labels, n_labels, _, _ = \
            input_to_cuml_array(labels, check_dtype=dtype, check_cols=1)
    if sample_weight is None:
        sample_weight = cp.ones(n_rows, dtype=dtype)
    else:
        sample_weight, _, _, _ = \
            input_to_cuml_array(sample_weight, check_dtype=dtype,
                                check_rows=n_rows, check_cols=n_cols)
        sample_weight = sample_weight.to_output('cupy')
    print(1)

    if normalize not in ['true', 'pred', 'all', None]:
        raise ValueError("normalize must be one of {'true', 'pred', "
                         "'all', None}")

    y_true, _ = make_monotonic(y_true, labels, copy=True)
    y_pred, _ = make_monotonic(y_pred, labels, copy=True)

    # intersect y_pred, y_true with labels, eliminate items not in labels
    ind = cp.logical_and(y_pred < n_labels, y_true < n_labels)
    y_pred = y_pred[ind]
    y_true = y_true[ind]
    sample_weight = sample_weight[ind]

    # Choosing accumulator dtype to always have high precision
    dtype = np.int64 if dtype.kind in {'i', 'u', 'b'} else np.float64

    cm = cp.sparse.coo_matrix((sample_weight, (y_true, y_pred)),
                              shape=(n_labels, n_labels),
                              dtype=dtype).toarray()

    with np.errstate(all='ignore'):
        if normalize == 'true':
            cm = cp.divide(cm, cm.sum(axis=1, keepdims=True))
        elif normalize == 'pred':
            cm = cp.divide(cm, cm.sum(axis=0, keepdims=True))
        elif normalize == 'all':
            cm = cp.divide(cm, cm.sum())
        cm = cp.nan_to_num(cm)

    return cm
