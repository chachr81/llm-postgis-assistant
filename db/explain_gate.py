# db/explain_gate.py
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from db.engine import engine

def explain_summary(sql: str) -> dict:
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("SET statement_timeout TO '5s';")
            plan_json = conn.execute(text(f"EXPLAIN (FORMAT JSON) {sql}")).scalar()
        plan = plan_json[0].get("Plan", {}) if isinstance(plan_json, list) else {}
        return {
            "node": plan.get("Node Type"),
            "startup_cost": plan.get("Startup Cost"),
            "total_cost": plan.get("Total Cost"),
            "plan_rows": plan.get("Plan Rows"),
            "plan_width": plan.get("Plan Width"),
        }
    except SQLAlchemyError as e:
        return {"error": str(e.__cause__ or e)}

def too_expensive(plan: dict) -> tuple[bool, str]:
    if not plan or "total_cost" not in plan:
        return False, ""
    total = plan.get("total_cost") or 0
    if total and total > 5_000_000:
        return True, f"total_cost={total}"
    return False, ""
