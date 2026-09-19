"""Pure-arithmetic tests for score_binary - no I/O, no mocks needed."""

from agent.eval.confusion_matrix import score_binary


def test_perfect_predictor():
    rows = [{"is_bad": True}, {"is_bad": True}, {"is_bad": False}, {"is_bad": False}]
    predict = lambda row: row["is_bad"]  # matches ground truth exactly

    result = score_binary(rows, predict)

    assert result["n"] == 4
    assert result["tp"] == 2
    assert result["fp"] == 0
    assert result["tn"] == 2
    assert result["fn"] == 0
    assert result["true_positive_rate"] == 1.0
    assert result["false_positive_rate"] == 0.0


def test_imperfect_predictor_mixed_errors():
    rows = [
        {"is_bad": True},   # tp
        {"is_bad": True},   # fn (missed)
        {"is_bad": False},  # fp (wrongly flagged)
        {"is_bad": False},  # tn
    ]
    predict = lambda row: row is rows[0] or row is rows[2]

    result = score_binary(rows, predict)

    assert result["tp"] == 1
    assert result["fn"] == 1
    assert result["fp"] == 1
    assert result["tn"] == 1
    assert result["true_positive_rate"] == 0.5
    assert result["false_positive_rate"] == 0.5


def test_no_negatives_gives_none_false_positive_rate():
    rows = [{"is_bad": True}, {"is_bad": True}]
    result = score_binary(rows, lambda row: True)
    assert result["false_positive_rate"] is None
    assert result["true_positive_rate"] == 1.0


def test_no_positives_gives_none_true_positive_rate():
    rows = [{"is_bad": False}, {"is_bad": False}]
    result = score_binary(rows, lambda row: False)
    assert result["true_positive_rate"] is None
    assert result["false_positive_rate"] == 0.0
