from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from evalml.model_understanding import find_confusion_matrix_per_thresholds
from evalml.model_understanding.decision_boundary import (
    _accuracy,
    _balanced_accuracy,
    _f1,
    _find_confusion_matrix_objective_threshold,
    _find_data_between_ranges,
    _precision,
    _recall,
)


@pytest.mark.parametrize(
    "val_list,expected_val",
    [
        ([0, 0, 100, 100], 0.0),
        ([100, 0, 0, 100], 0.5),
        ([50, 50, 50, 50], 0.5),
        ([40, 20, 10, 30], 0.6),
    ],
)
def test_accuracy(val_list, expected_val):
    val = _accuracy(val_list)
    assert val == expected_val


@pytest.mark.parametrize(
    "val_list,expected_val",
    [
        ([0, 0, 100, 100], 0.0),
        ([100, 0, 0, 100], 0.25),
        ([50, 50, 50, 50], 0.5),
        ([40, 20, 10, 30], 13 / 21),
    ],
)
def test_balanced_accuracy(val_list, expected_val):
    val = _balanced_accuracy(val_list)
    assert val == expected_val


@pytest.mark.parametrize(
    "val_list,expected_val",
    [
        ([0, 0, 100, 100], 0.0),
        ([100, 0, 0, 100], 0.5),
        ([50, 50, 50, 50], 0.5),
        ([40, 20, 10, 30], 4 / 7),
    ],
)
def test_recall(val_list, expected_val):
    val = _recall(val_list)
    assert val == expected_val


@pytest.mark.parametrize(
    "val_list,expected_val",
    [
        ([0, 0, 100, 100], 0.0),
        ([100, 0, 0, 100], 1.0),
        ([50, 50, 50, 50], 0.5),
        ([40, 20, 10, 30], 0.8),
    ],
)
def test_precision(val_list, expected_val):
    val = _precision(val_list)
    assert val == expected_val


@pytest.mark.parametrize(
    "val_list,expected_val",
    [
        ([0, 0, 100, 100], 0.0),
        ([100, 0, 0, 100], 2 / 3),
        ([50, 50, 50, 50], 0.5),
        ([40, 20, 10, 30], 2 / 3),
    ],
)
def test_f1(val_list, expected_val):
    val = _f1(val_list)
    assert val == expected_val


def test_find_confusion_matrix_per_threshold_errors(
    dummy_binary_pipeline_class, dummy_multiclass_pipeline_class
):
    bcp = dummy_binary_pipeline_class({})
    mcp = dummy_multiclass_pipeline_class({})
    X = pd.DataFrame()
    y = pd.Series()

    with pytest.raises(
        ValueError, match="Expected a fitted binary classification pipeline"
    ):
        find_confusion_matrix_per_thresholds(bcp, X, y)

    with pytest.raises(
        ValueError, match="Expected a fitted binary classification pipeline"
    ):
        find_confusion_matrix_per_thresholds(mcp, X, y)

    mcp._is_fitted = True
    with pytest.raises(
        ValueError, match="Expected a fitted binary classification pipeline"
    ):
        find_confusion_matrix_per_thresholds(mcp, X, y)


@patch("evalml.pipelines.BinaryClassificationPipeline.fit")
@patch("evalml.pipelines.BinaryClassificationPipeline.predict_proba")
@patch(
    "evalml.model_understanding.decision_boundary._find_confusion_matrix_objective_threshold"
)
@patch("evalml.model_understanding.decision_boundary._find_data_between_ranges")
def test_find_confusion_matrix_per_threshold_args_pass_through(
    mock_ranges, mock_threshold, mock_pred_proba, mock_fit, dummy_binary_pipeline_class
):
    n_bins = 100
    X = pd.DataFrame()
    y = pd.Series([0] * 500 + [1] * 500)
    bcp = dummy_binary_pipeline_class({})
    bcp._is_fitted = True

    # set return predicted proba
    preds = [0.1] * 250 + [0.8] * 500 + [0.6] * 250
    pred_proba = pd.DataFrame({0: [1 - v for v in preds], 1: preds})
    mock_pred_proba.return_value = pred_proba

    # set the output for the thresholding private method
    obj_dict = {
        "accuracy": [[0.5, 0.5], "some function"],
        "balanced_accuracy": [[0.5, 0.25], "some function"],
    }
    conf_matrix = [[0, 100, 280, 0] for i in range(n_bins)]
    mock_threshold.return_value = (conf_matrix, obj_dict)

    # set the output for data between ranges
    range_result = [[range(5)] for i in range(n_bins)]
    mock_ranges.return_value = range_result

    # calculate the expected output results
    bins = [i / n_bins for i in range(n_bins + 1)]
    expected_pos_skew, pos_range = np.histogram(pred_proba.iloc[:, -1][500:], bins=bins)
    expected_neg_skew, _ = np.histogram(pred_proba.iloc[:, -1][:500], bins=bins)
    expected_result_df = pd.DataFrame(
        {
            "pos_bins": expected_pos_skew,
            "neg_bins": expected_neg_skew,
            "confusion_matrix": conf_matrix,
            "data_in_bins": range_result,
        },
        index=pos_range[:-1],
    )
    final_obj_dict = {"accuracy": [0.5, 0.5], "balanced_accuracy": [0.5, 0.25]}

    returned_result = find_confusion_matrix_per_thresholds(bcp, X, y, n_bins)
    call_args = mock_threshold.call_args
    assert all(call_args[0][0] == expected_pos_skew)
    assert all(call_args[0][1] == expected_neg_skew)
    assert all(call_args[0][2] == pos_range)

    assert isinstance(returned_result, tuple)
    pd.testing.assert_frame_equal(returned_result[0], expected_result_df)
    assert returned_result[1] == final_obj_dict


@patch("evalml.pipelines.BinaryClassificationPipeline.fit")
@patch("evalml.pipelines.BinaryClassificationPipeline.predict_proba")
@pytest.mark.parametrize("n_bins", [100, 10, None])
def test_find_confusion_matrix_per_threshold_n_bins(
    mock_pred_proba, mock_fit, n_bins, dummy_binary_pipeline_class
):
    X = pd.DataFrame()
    y = pd.Series([0] * 1200 + [1] * 800)
    bcp = dummy_binary_pipeline_class({})
    bcp._is_fitted = True
    top_k = 5

    # set return predicted proba
    preds = [0.1] * 400 + [0.8] * 400 + [0.6] * 400 + [0.4] * 400 + [0.5] * 400
    pred_proba = pd.DataFrame({0: [1 - v for v in preds], 1: preds})
    mock_pred_proba.return_value = pred_proba

    # calculate the expected output results
    returned_result = find_confusion_matrix_per_thresholds(
        bcp, X, y, n_bins, top_k=top_k
    )
    assert isinstance(returned_result, tuple)
    if n_bins is not None:
        assert len(returned_result[0]) == n_bins
    assert returned_result[0].columns.tolist() == [
        "pos_bins",
        "neg_bins",
        "confusion_matrix",
        "data_in_bins",
    ]
    assert sum(returned_result[0]["pos_bins"]) == 800
    assert sum(returned_result[0]["neg_bins"]) == 1200
    assert all([len(v) <= top_k for v in returned_result[0]["data_in_bins"]])
    assert all([len(v) == 4 for v in returned_result[0]["confusion_matrix"]])
    assert isinstance(returned_result[1], dict)
    assert set(returned_result[1].keys()) == {
        "accuracy",
        "balanced_accuracy",
        "precision",
        "recall",
        "f1",
    }


@patch("evalml.pipelines.BinaryClassificationPipeline.fit")
@patch("evalml.pipelines.BinaryClassificationPipeline.predict_proba")
@pytest.mark.parametrize("top_k", [-1, 4])
@pytest.mark.parametrize("n_bins", [100, None])
def test_find_confusion_matrix_per_threshold_k_(
    mock_pred_proba, mock_fit, n_bins, top_k, dummy_binary_pipeline_class
):
    X = pd.DataFrame()
    y = pd.Series([0] * 1200 + [1] * 800)
    bcp = dummy_binary_pipeline_class({})
    bcp._is_fitted = True

    # set return predicted proba
    preds = [0.1] * 400 + [0.8] * 400 + [0.6] * 400 + [0.4] * 400 + [0.5] * 400
    pred_proba = pd.DataFrame({0: [1 - v for v in preds], 1: preds})
    mock_pred_proba.return_value = pred_proba

    # calculate the expected output results
    returned_result = find_confusion_matrix_per_thresholds(
        bcp, X, y, n_bins=n_bins, top_k=top_k
    )
    assert isinstance(returned_result, tuple)
    if n_bins is not None:
        assert len(returned_result[0]) == n_bins
    n_bins = len(returned_result[0])
    if top_k == -1:
        assert sum([len(v) for v in returned_result[0]["data_in_bins"]]) == 2000
    else:
        assert (
            sum([len(v) for v in returned_result[0]["data_in_bins"]]) <= top_k * n_bins
        )


@pytest.mark.parametrize(
    "ranges", [[i / 10 for i in range(11)], [i / 50 for i in range(51)]]
)
@pytest.mark.parametrize("top_k", [-1, 5])
def test_find_data_between_ranges(top_k, ranges):
    data = pd.Series([(i % 100) / 100 for i in range(10000)])
    res = _find_data_between_ranges(data, ranges, top_k)
    lens = 10000 / (len(ranges) - 1) if top_k == -1 else top_k
    assert all([len(v) == lens for v in res])
    total_len = sum([len(v) for v in res])
    # check that the values are all unique here
    res = np.ravel(res)
    assert len(set(res)) == total_len


@pytest.mark.parametrize(
    "pos_skew",
    [
        [0, 0, 2, 3, 5, 10, 20, 20, 20, 20],
        [2, 1, 5, 15, 17, 20, 20, 20, 0, 0],
        [0, 0, 5, 5, 15, 15, 40, 20, 0, 0],
        [20, 20, 0, 5, 10, 5, 0, 0, 20, 20],
    ],
)
@pytest.mark.parametrize(
    "neg_skew",
    [
        [20, 30, 15, 15, 10, 5, 3, 2, 0, 0],
        [0, 0, 15, 15, 10, 5, 30, 20, 5, 0],
        [0, 0, 0, 15, 10, 25, 20, 10, 10, 10],
    ],
)
def test_find_confusion_matrix_objective_threshold(pos_skew, neg_skew):
    # test a variety of bin skews
    ranges = [i / 10 for i in range(11)]
    conf_mat_list, obj_dict = _find_confusion_matrix_objective_threshold(
        pos_skew, neg_skew, ranges
    )
    total_pos, total_neg = 100, 100
    pos, neg = 0, 0
    objective_dict = {
        "accuracy": [[0, 0], _accuracy],
        "balanced_accuracy": [[0, 0], _balanced_accuracy],
        "precision": [[0, 0], _precision],
        "recall": [[0, 0], _recall],
        "f1": [[0, 0], _f1],
    }
    expected_conf_mat = []
    for i, range_val in enumerate(ranges[:-1]):
        pos += pos_skew[i]
        neg += neg_skew[i]
        tp = total_pos - pos
        fp = total_neg - neg
        cm = [tp, neg, fp, pos]
        assert sum(cm) == 200
        expected_conf_mat.append(cm)

        for k, v in objective_dict.items():
            obj_val = v[1](cm)
            if obj_val > v[0][0]:
                v[0][0] = obj_val
                v[0][1] = range_val

    assert conf_mat_list == expected_conf_mat
    assert obj_dict == objective_dict


@pytest.mark.parametrize("top_k", [3, -1])
def test_find_confusion_matrix_per_threshold(
    top_k, logistic_regression_binary_pipeline_class, X_y_binary
):
    bcp = logistic_regression_binary_pipeline_class({})
    X, y = X_y_binary
    bcp.fit(X, y)
    res_df, obj_dict = find_confusion_matrix_per_thresholds(
        bcp, X, y, n_bins=10, top_k=top_k
    )
    assert len(res_df) == 10
    if top_k == 3:
        assert sum([len(s) for s in res_df["data_in_bins"]]) <= 30
    else:
        assert sum([len(s) for s in res_df["data_in_bins"]]) == len(y)
    assert all([sum(v) == 100 for v in res_df["confusion_matrix"]])
    assert len(obj_dict) == 5


def test_find_confusion_matrix_encode(
    logistic_regression_binary_pipeline_class, X_y_binary
):
    bcp = logistic_regression_binary_pipeline_class({})
    bcp_new = logistic_regression_binary_pipeline_class({})
    X, y = X_y_binary
    y_new = pd.Series(["Value_1" if s == 1 else "Value_0" for s in y])
    bcp.fit(X, y)
    bcp_new.fit(X, y_new)
    res_df, obj_dict = find_confusion_matrix_per_thresholds(bcp, X, y)
    res_df_new, obj_dict_new = find_confusion_matrix_per_thresholds(bcp_new, X, y_new)
    pd.testing.assert_frame_equal(res_df, res_df_new)
    assert obj_dict == obj_dict_new
