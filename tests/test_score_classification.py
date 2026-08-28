"""Pure-arithmetic tests for score_classification.py's predict_label/score/compute_roc_auc -
no I/O, no mocks needed. See docs/test_case_catalog.md (U2-U4) for the case list this
covers."""

from agent.eval.score_classification import predict_label, score, compute_roc_auc


def test_predict_label_boundary_is_inclusive():
    row = {"candidate_feed_name": "Revenue Trend", "candidate_similarity": "0.5"}
    assert predict_label(row, threshold=0.5) == "Revenue Trend"


def test_predict_label_below_threshold_is_none():
    row = {"candidate_feed_name": "Revenue Trend", "candidate_similarity": "0.49"}
    assert predict_label(row, threshold=0.5) == "none"


def test_predict_label_missing_similarity_is_none():
    row = {"candidate_feed_name": "Revenue Trend", "candidate_similarity": None}
    assert predict_label(row, threshold=0.1) == "none"


def test_predict_label_uses_rows_own_threshold_when_none_given():
    row = {"candidate_feed_name": "Revenue Trend", "candidate_similarity": "0.6", "candidate_threshold": "0.7"}
    assert predict_label(row) == "none"  # 0.6 < row's own 0.7
    assert predict_label(row, threshold=0.5) == "Revenue Trend"  # override beats row's own


def _row(correct_feed, candidate_feed_name, candidate_similarity, candidate_threshold="0.5"):
    return {
        "correct_feed": correct_feed,
        "candidate_feed_name": candidate_feed_name,
        "candidate_similarity": candidate_similarity,
        "candidate_threshold": candidate_threshold,
    }


def test_score_precision_recall_false_skip_rate():
    rows = [
        _row("A", "A", "0.9"),      # tp
        _row("B", "B", "0.6"),      # tp
        _row("C", "D", "0.9"),      # fp, wrong_feed (relevant, predicted the wrong feed)
        _row("E", "E", "0.3"),      # false_skip (relevant, similarity below threshold)
        _row("none", "F", "0.9"),   # fp, but NOT wrong_feed (correct_feed was "none")
    ]

    result = score(rows, threshold=None)

    assert result["n"] == 5
    assert result["n_relevant"] == 4
    assert result["tp"] == 2
    assert result["fp"] == 2
    assert result["wrong_feed_count"] == 1
    assert result["false_skip_count"] == 1
    assert result["fn"] == 2
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5
    assert result["false_skip_rate"] == 0.25


def test_compute_roc_auc_perfect_separation():
    rows = [
        _row("Revenue Trend", "Revenue Trend", "0.9"),
        _row("Revenue Trend", "Revenue Trend", "0.8"),
        _row("none", "Scandal", "0.5"),
        _row("none", "Scandal", "0.3"),
    ]

    result = compute_roc_auc(rows)

    assert result["auc"] == 1.0
    assert result["best_threshold"] == 0.8
    assert result["best_threshold_metrics"] == {"tpr": 1.0, "fpr": 0.0}


def test_compute_roc_auc_imperfect_separation_with_missing_candidate():
    rows = [
        _row("Revenue Trend", "Revenue Trend", "0.6"),
        _row("Revenue Trend", "Growth", "0.55"),
        _row("none", "Scandal", "0.7"),
        _row("none", "Scandal", "0.3"),
        _row("Growth", None, None),  # no candidate at all - scores 0.0, can never be accepted
    ]

    result = compute_roc_auc(rows)

    assert result["auc"] == 0.75
    assert result["best_threshold"] == 0.6
    assert result["best_threshold_metrics"] == {"tpr": 1.0, "fpr": 0.25}


def test_compute_roc_auc_degenerate_when_no_positives_or_no_negatives():
    all_irrelevant = [_row("none", "Scandal", "0.9"), _row("none", "Scandal", "0.1")]
    result = compute_roc_auc(all_irrelevant)
    assert result == {"auc": None, "best_threshold": None, "best_threshold_metrics": None, "roc_points": []}
