"""I4 (docs/test_case_catalog.md): every real eval_type string must be accepted by
eval_runs' DB check constraint. This is exactly the bug hit live this session -
insight_quality/research_order were added as eval types in code before the DB
constraint was widened to allow them, and it only surfaced via a manual smoke test.
This test would have caught it immediately."""

from db.queries import insert_eval_run

REAL_EVAL_TYPES = ["classification", "generation", "insight_quality", "guardrails", "research_order", "live_sample"]


def test_every_real_eval_type_is_accepted_by_the_db_constraint(client):
    inserted_ids = []
    try:
        for eval_type in REAL_EVAL_TYPES:
            row = insert_eval_run(eval_type, {"note": "integration test row"})
            inserted_ids.append(row["id"])
    finally:
        for row_id in inserted_ids:
            client.table("eval_runs").delete().eq("id", row_id).execute()

    assert len(inserted_ids) == len(REAL_EVAL_TYPES)
