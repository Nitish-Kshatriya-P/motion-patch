import os
import sqlite3
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from models import (
    Asset,
    Analysis,
    Finding,
    Evidence,
    AssessmentVerdict,
    CoverageRecord,
    WorkflowSession,
    RepairPlan,
    Approval,
    LifecycleState,
    AnalysisStatus,
    AnomalyType,
    Severity,
    BodyPart,
    BVHMetadata,
    AgentSpecification,
    ReviewAction,
    DatasetSplit,
    HumanFeedback,
    FalseAlarmEvaluationResponse,
    GroundTruthExportResponse,
)

DB_PATH = os.path.join(os.path.dirname(__file__), "mocap_studio.db")


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    target_path = db_path if db_path is not None else DB_PATH
    conn = sqlite3.connect(target_path, timeout=5.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db(db_path: Optional[str] = None):
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


def is_uuid_like(val: Optional[str]) -> bool:
    if not val:
        return True
    s = val.lower().removesuffix(".bvh").strip()
    if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", s):
        return True
    if re.fullmatch(r"[0-9a-f]{16,}", s):
        return True
    return False


def generate_session_title(
    filename: Optional[str],
    status: Optional[str],
    diagnostic_summary: Optional[str],
    findings_count: int = 0,
    frame_count: int = 0,
) -> str:
    if filename and not is_uuid_like(filename):
        return filename

    if diagnostic_summary:
        match = re.search(r"-\s*([A-Za-z0-9_]+):\s*frames\s*[\d-]+\s*\(([^,)]+)", diagnostic_summary)
        if match:
            joint = match.group(1)
            anomaly = match.group(2).replace("_", " ").title()
            return f"{joint} {anomaly}"

    if findings_count > 0:
        return f"{findings_count} Kinematic {'Fault' if findings_count == 1 else 'Faults'}"

    if status == "CLEAN" or (status is None and findings_count == 0):
        if frame_count > 0:
            return f"Clean Take ({frame_count}f)"
        return "Clean Motion Take"

    if status == "INCONCLUSIVE":
        if frame_count > 0:
            return f"Inconclusive Scan ({frame_count}f)"
        return "Inconclusive Take"

    return "Motion Capture Take"


def init_db(db_path: Optional[str] = None) -> None:
    with get_db(db_path) as conn:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS assets (
                    asset_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_size_bytes INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    skeleton_signature TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS analyses (
                    analysis_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    skeleton_signature TEXT NOT NULL,
                    parser_version TEXT NOT NULL,
                    detector_version TEXT NOT NULL,
                    analysis_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    up_axis TEXT NOT NULL,
                    detector_status_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (asset_id) REFERENCES assets(asset_id) ON DELETE CASCADE
                );
                """
            )
            try:
                conn.execute("ALTER TABLE analyses ADD COLUMN detector_status_json TEXT NOT NULL DEFAULT '{}';")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE analyses ADD COLUMN diagnostic_summary TEXT NOT NULL DEFAULT '';")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE analyses ADD COLUMN coverage_records_json TEXT NOT NULL DEFAULT '[]';")
            except Exception:
                pass
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS findings (
                    finding_id TEXT NOT NULL,
                    analysis_id TEXT NOT NULL,
                    affected_joint TEXT NOT NULL,
                    affected_body_part TEXT NOT NULL,
                    frame_start INTEGER NOT NULL,
                    frame_end INTEGER NOT NULL,
                    time_start REAL NOT NULL,
                    time_end REAL NOT NULL,
                    anomaly_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_json TEXT NOT NULL,
                    detector_version TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    verdict TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (analysis_id, finding_id),
                    FOREIGN KEY (analysis_id) REFERENCES analyses(analysis_id) ON DELETE CASCADE
                );
                """
            )
            try:
                cursor = conn.execute("PRAGMA table_info(findings);")
                cols = {row[1]: row for row in cursor.fetchall()}
                if "analysis_id" in cols and cols["analysis_id"][5] == 0:
                    conn.execute("CREATE TABLE findings_migrated (finding_id TEXT NOT NULL, analysis_id TEXT NOT NULL, affected_joint TEXT NOT NULL, affected_body_part TEXT NOT NULL, frame_start INTEGER NOT NULL, frame_end INTEGER NOT NULL, time_start REAL NOT NULL, time_end REAL NOT NULL, anomaly_type TEXT NOT NULL, severity TEXT NOT NULL, confidence REAL NOT NULL, evidence_json TEXT NOT NULL, detector_version TEXT NOT NULL, explanation TEXT NOT NULL, verdict TEXT, created_at TEXT NOT NULL, PRIMARY KEY (analysis_id, finding_id), FOREIGN KEY (analysis_id) REFERENCES analyses(analysis_id) ON DELETE CASCADE);")
                    conn.execute("INSERT OR IGNORE INTO findings_migrated SELECT finding_id, analysis_id, affected_joint, affected_body_part, frame_start, frame_end, time_start, time_end, anomaly_type, severity, confidence, evidence_json, detector_version, explanation, NULL, created_at FROM findings;")
                    conn.execute("DROP TABLE findings;")
                    conn.execute("ALTER TABLE findings_migrated RENAME TO findings;")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE findings ADD COLUMN created_at TEXT NOT NULL DEFAULT '';")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE findings ADD COLUMN verdict TEXT;")
            except Exception:
                pass
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_sessions (
                    session_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL,
                    analysis_id TEXT NOT NULL,
                    plan_id TEXT,
                    approval_id TEXT,
                    lifecycle_state TEXT NOT NULL,
                    title TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (asset_id) REFERENCES assets(asset_id) ON DELETE CASCADE,
                    FOREIGN KEY (analysis_id) REFERENCES analyses(analysis_id) ON DELETE CASCADE,
                    FOREIGN KEY (plan_id) REFERENCES repair_plans(plan_id) ON DELETE SET NULL,
                    FOREIGN KEY (approval_id) REFERENCES approvals(approval_id) ON DELETE SET NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS repair_plans (
                    plan_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    analysis_id TEXT NOT NULL,
                    analysis_hash TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    selected_finding_ids_json TEXT NOT NULL,
                    proposed_roster_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    user_prompt TEXT,
                    selected_joints_json TEXT,
                    FOREIGN KEY (session_id) REFERENCES workflow_sessions(session_id) ON DELETE CASCADE,
                    FOREIGN KEY (analysis_id) REFERENCES analyses(analysis_id) ON DELETE CASCADE
                );
                """
            )
            try:
                conn.execute("ALTER TABLE repair_plans ADD COLUMN user_prompt TEXT;")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE repair_plans ADD COLUMN selected_joints_json TEXT;")
            except Exception:
                pass
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    repair_plan_version INTEGER NOT NULL,
                    analysis_hash TEXT NOT NULL,
                    selected_finding_ids_json TEXT NOT NULL,
                    roster_hash TEXT NOT NULL,
                    approved_by TEXT NOT NULL,
                    approved_at TEXT NOT NULL,
                    valid_until TEXT NOT NULL,
                    user_prompt TEXT,
                    selected_joints_json TEXT,
                    FOREIGN KEY (session_id) REFERENCES workflow_sessions(session_id) ON DELETE CASCADE,
                    FOREIGN KEY (plan_id) REFERENCES repair_plans(plan_id) ON DELETE CASCADE
                );
                """
            )
            try:
                conn.execute("ALTER TABLE approvals ADD COLUMN user_prompt TEXT;")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE approvals ADD COLUMN selected_joints_json TEXT;")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE workflow_sessions ADD COLUMN title TEXT;")
            except Exception:
                pass
            try:
                cursor = conn.execute("""
                    SELECT w.session_id, w.title, a.filename, an.status AS analysis_status, an.diagnostic_summary, a.metadata_json,
                           (SELECT COUNT(*) FROM findings f WHERE f.analysis_id = w.analysis_id) AS findings_count
                    FROM workflow_sessions w
                    LEFT JOIN assets a ON w.asset_id = a.asset_id
                    LEFT JOIN analyses an ON w.analysis_id = an.analysis_id;
                """)
                updates = []
                for row in cursor.fetchall():
                    existing_title = row["title"] if "title" in row.keys() else None
                    if not existing_title or is_uuid_like(existing_title):
                        meta = {}
                        if row["metadata_json"]:
                            try:
                                meta = json.loads(row["metadata_json"])
                            except Exception:
                                pass
                        computed_title = generate_session_title(
                            row["filename"],
                            row["analysis_status"],
                            row["diagnostic_summary"],
                            row["findings_count"] or 0,
                            meta.get("frame_count", 0),
                        )
                        updates.append((computed_title, row["session_id"]))
                if updates:
                    conn.executemany("UPDATE workflow_sessions SET title = ? WHERE session_id = ?;", updates)
            except Exception:
                pass
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    uploaded_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES workflow_sessions(session_id) ON DELETE CASCADE,
                    FOREIGN KEY (asset_id) REFERENCES assets(asset_id) ON DELETE CASCADE
                );
                """
            )
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO session_uploads (session_id, asset_id, filename, uploaded_at)
                    SELECT w.session_id, w.asset_id, a.filename, w.created_at
                    FROM workflow_sessions w
                    JOIN assets a ON w.asset_id = a.asset_id
                    WHERE NOT EXISTS (
                        SELECT 1 FROM session_uploads su WHERE su.session_id = w.session_id AND su.asset_id = w.asset_id
                    );
                    """
                )
            except Exception:
                pass
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS human_feedback (
                    feedback_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL,
                    session_id TEXT,
                    analysis_id TEXT,
                    finding_id TEXT,
                    action TEXT NOT NULL,
                    joint TEXT NOT NULL,
                    frame_start INTEGER NOT NULL,
                    frame_end INTEGER NOT NULL,
                    anomaly_type TEXT,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    notes TEXT,
                    annotator TEXT NOT NULL DEFAULT 'human_reviewer',
                    split TEXT NOT NULL DEFAULT 'dev',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (asset_id) REFERENCES assets(asset_id) ON DELETE CASCADE,
                    FOREIGN KEY (session_id) REFERENCES workflow_sessions(session_id) ON DELETE SET NULL,
                    FOREIGN KEY (analysis_id) REFERENCES analyses(analysis_id) ON DELETE SET NULL
                );
                """
            )
            try:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_human_feedback_asset ON human_feedback(asset_id);")
            except Exception:
                pass
            try:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_human_feedback_finding ON human_feedback(finding_id);")
            except Exception:
                pass
            try:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_human_feedback_split ON human_feedback(split);")
            except Exception:
                pass
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    text TEXT,
                    message_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES workflow_sessions(session_id) ON DELETE CASCADE
                );
                """
            )
            try:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, created_at);")
            except Exception:
                pass


def insert_asset(conn: sqlite3.Connection, asset: Asset) -> None:
    conn.execute(
        """
        INSERT INTO assets (
            asset_id, filename, file_path, file_size_bytes, content_hash, skeleton_signature, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            asset.asset_id,
            asset.filename,
            asset.file_path,
            asset.file_size_bytes,
            asset.content_hash,
            asset.skeleton_signature,
            asset.metadata.model_dump_json(),
            asset.created_at,
        ),
    )


def get_asset(conn: sqlite3.Connection, asset_id: str) -> Optional[Asset]:
    cursor = conn.execute("SELECT * FROM assets WHERE asset_id = ?;", (asset_id,))
    row = cursor.fetchone()
    if not row:
        return None
    meta_dict = json.loads(row["metadata_json"])
    return Asset(
        asset_id=row["asset_id"],
        filename=row["filename"],
        file_path=row["file_path"],
        file_size_bytes=row["file_size_bytes"],
        content_hash=row["content_hash"],
        skeleton_signature=row["skeleton_signature"],
        metadata=BVHMetadata(**meta_dict),
        created_at=row["created_at"],
    )


def invalidate_stale_approvals_for_asset(
    conn: sqlite3.Connection, asset_id: str, new_analysis_id: Optional[str] = None
) -> int:
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        "SELECT session_id, analysis_id, plan_id, approval_id, lifecycle_state FROM workflow_sessions WHERE asset_id = ?;",
        (asset_id,),
    )
    sessions = cursor.fetchall()
    invalidated_count = 0
    for s in sessions:
        sess_id = s["session_id"]
        old_analysis = s["analysis_id"]
        if new_analysis_id and old_analysis == new_analysis_id:
            continue
        if s["approval_id"] or s["plan_id"] or s["lifecycle_state"] in (LifecycleState.APPROVED.value, LifecycleState.AWAITING_APPROVAL.value):
            conn.execute(
                """
                UPDATE workflow_sessions
                SET plan_id = NULL, approval_id = NULL, lifecycle_state = ?, updated_at = ?
                WHERE session_id = ?;
                """,
                (LifecycleState.REVIEWING_FINDINGS.value, now_iso, sess_id),
            )
            invalidated_count += 1
        if s["plan_id"]:
            conn.execute(
                "UPDATE repair_plans SET status = 'SUPERSEDED' WHERE plan_id = ? AND status IN ('PENDING', 'APPROVED');",
                (s["plan_id"],),
            )
    conn.execute(
        """
        UPDATE repair_plans
        SET status = 'SUPERSEDED'
        WHERE analysis_id IN (
            SELECT analysis_id FROM analyses WHERE asset_id = ? AND (? IS NULL OR analysis_id != ?)
        ) AND status IN ('PENDING', 'APPROVED');
        """,
        (asset_id, new_analysis_id, new_analysis_id),
    )
    return invalidated_count


def insert_analysis(conn: sqlite3.Connection, analysis: Analysis) -> None:
    cov_json = json.dumps(
        [
            rec.model_dump() if hasattr(rec, "model_dump") else (dict(rec) if isinstance(rec, dict) else rec)
            for rec in analysis.coverage_records
        ],
        sort_keys=True,
    )
    try:
        conn.execute(
            """
            INSERT INTO analyses (
                analysis_id, asset_id, content_hash, skeleton_signature, parser_version, detector_version, analysis_hash, status, up_axis, detector_status_json, diagnostic_summary, coverage_records_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                analysis.analysis_id,
                analysis.asset_id,
                analysis.content_hash,
                analysis.skeleton_signature,
                analysis.parser_version,
                analysis.detector_version,
                analysis.analysis_hash,
                analysis.status.value,
                analysis.up_axis,
                json.dumps(analysis.detector_status, sort_keys=True),
                analysis.diagnostic_summary or "",
                cov_json,
                analysis.created_at,
            ),
        )
    except sqlite3.OperationalError:
        conn.execute(
            """
            INSERT INTO analyses (
                analysis_id, asset_id, content_hash, skeleton_signature, parser_version, detector_version, analysis_hash, status, up_axis, detector_status_json, diagnostic_summary, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                analysis.analysis_id,
                analysis.asset_id,
                analysis.content_hash,
                analysis.skeleton_signature,
                analysis.parser_version,
                analysis.detector_version,
                analysis.analysis_hash,
                analysis.status.value,
                analysis.up_axis,
                json.dumps(analysis.detector_status, sort_keys=True),
                analysis.diagnostic_summary or "",
                analysis.created_at,
            ),
        )
    for f in analysis.findings:
        verdict_val = f.verdict.value if (f.verdict and hasattr(f.verdict, "value")) else (str(f.verdict) if f.verdict else None)
        if hasattr(f.evidence, "to_dict"):
            ev_data = f.evidence.to_dict()
        elif hasattr(f.evidence, "model_dump"):
            ev_data = f.evidence.model_dump()
        elif isinstance(f.evidence, dict):
            ev_data = dict(f.evidence)
        else:
            ev_data = {}
        ev_json = json.dumps(ev_data, sort_keys=True)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO findings (
                    finding_id, analysis_id, affected_joint, affected_body_part, frame_start, frame_end, time_start, time_end,
                    anomaly_type, severity, confidence, evidence_json, detector_version, explanation, verdict, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    f.finding_id,
                    analysis.analysis_id,
                    f.affected_joint,
                    f.affected_body_part,
                    f.frame_start,
                    f.frame_end,
                    f.time_start,
                    f.time_end,
                    f.anomaly_type.value,
                    f.severity.value,
                    f.confidence,
                    ev_json,
                    f.detector_version,
                    f.explanation,
                    verdict_val,
                    f.created_at if f.created_at else analysis.created_at,
                ),
            )
        except sqlite3.OperationalError:
            conn.execute(
                """
                INSERT OR REPLACE INTO findings (
                    finding_id, analysis_id, affected_joint, affected_body_part, frame_start, frame_end, time_start, time_end,
                    anomaly_type, severity, confidence, evidence_json, detector_version, explanation, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    f.finding_id,
                    analysis.analysis_id,
                    f.affected_joint,
                    f.affected_body_part,
                    f.frame_start,
                    f.frame_end,
                    f.time_start,
                    f.time_end,
                    f.anomaly_type.value,
                    f.severity.value,
                    f.confidence,
                    ev_json,
                    f.detector_version,
                    f.explanation,
                    f.created_at if f.created_at else analysis.created_at,
                ),
            )
    invalidate_stale_approvals_for_asset(conn, analysis.asset_id, analysis.analysis_id)


def get_analysis(conn: sqlite3.Connection, analysis_id: str) -> Optional[Analysis]:
    cursor = conn.execute("SELECT * FROM analyses WHERE analysis_id = ?;", (analysis_id,))
    row = cursor.fetchone()
    if not row:
        return None
    f_cursor = conn.execute("SELECT * FROM findings WHERE analysis_id = ? ORDER BY frame_start ASC, frame_end ASC, affected_joint ASC, finding_id ASC;", (analysis_id,))
    findings = []
    for f_row in f_cursor.fetchall():
        verdict_val = f_row["verdict"] if ("verdict" in f_row.keys() and f_row["verdict"]) else None
        verdict_obj = AssessmentVerdict(verdict_val) if verdict_val else None
        raw_ev = json.loads(f_row["evidence_json"]) if f_row["evidence_json"] else {}
        try:
            ev_obj = Evidence(**raw_ev) if isinstance(raw_ev, dict) else raw_ev
        except Exception:
            ev_obj = raw_ev
        findings.append(
            Finding(
                finding_id=f_row["finding_id"],
                analysis_id=f_row["analysis_id"],
                affected_joint=f_row["affected_joint"],
                affected_body_part=BodyPart(f_row["affected_body_part"]),
                frame_start=f_row["frame_start"],
                frame_end=f_row["frame_end"],
                time_start=f_row["time_start"],
                time_end=f_row["time_end"],
                anomaly_type=AnomalyType(f_row["anomaly_type"]),
                severity=Severity(f_row["severity"]),
                confidence=f_row["confidence"],
                evidence=ev_obj,
                detector_version=f_row["detector_version"],
                explanation=f_row["explanation"],
                verdict=verdict_obj,
                created_at=f_row["created_at"] if "created_at" in f_row.keys() and f_row["created_at"] else row["created_at"],
            )
        )
    det_status: Dict[str, str] = {}
    if "detector_status_json" in row.keys() and row["detector_status_json"]:
        try:
            det_status = json.loads(row["detector_status_json"])
        except Exception:
            det_status = {}
    cov_records: List[CoverageRecord] = []
    if "coverage_records_json" in row.keys() and row["coverage_records_json"]:
        try:
            cov_records = [CoverageRecord(**item) for item in json.loads(row["coverage_records_json"])]
        except Exception:
            cov_records = []
    diag_summary = row["diagnostic_summary"] if "diagnostic_summary" in row.keys() and row["diagnostic_summary"] else None
    return Analysis(
        analysis_id=row["analysis_id"],
        asset_id=row["asset_id"],
        content_hash=row["content_hash"],
        skeleton_signature=row["skeleton_signature"],
        parser_version=row["parser_version"],
        detector_version=row["detector_version"],
        analysis_hash=row["analysis_hash"],
        status=AnalysisStatus(row["status"]),
        up_axis=row["up_axis"],
        findings=findings,
        detector_status=det_status,
        coverage_records=cov_records,
        diagnostic_summary=diag_summary,
        created_at=row["created_at"],
    )


def insert_workflow_session(conn: sqlite3.Connection, session: WorkflowSession) -> None:
    try:
        conn.execute(
            """
            INSERT INTO workflow_sessions (
                session_id, asset_id, analysis_id, plan_id, approval_id, lifecycle_state, title, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                session.session_id,
                session.asset_id,
                session.analysis_id,
                session.plan_id,
                session.approval_id,
                session.lifecycle_state.value,
                session.title,
                session.created_at,
                session.updated_at,
            ),
        )
    except sqlite3.OperationalError:
        conn.execute(
            """
            INSERT INTO workflow_sessions (
                session_id, asset_id, analysis_id, plan_id, approval_id, lifecycle_state, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                session.session_id,
                session.asset_id,
                session.analysis_id,
                session.plan_id,
                session.approval_id,
                session.lifecycle_state.value,
                session.created_at,
                session.updated_at,
            ),
        )


def get_workflow_session(conn: sqlite3.Connection, session_id: str) -> Optional[WorkflowSession]:
    cursor = conn.execute("SELECT * FROM workflow_sessions WHERE session_id = ?;", (session_id,))
    row = cursor.fetchone()
    if not row:
        return None
    return WorkflowSession(
        session_id=row["session_id"],
        asset_id=row["asset_id"],
        analysis_id=row["analysis_id"],
        plan_id=row["plan_id"],
        approval_id=row["approval_id"],
        lifecycle_state=LifecycleState(row["lifecycle_state"]),
        title=row["title"] if "title" in row.keys() else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def update_workflow_session_title(conn: sqlite3.Connection, session_id: str, title: str) -> None:
    try:
        conn.execute("ALTER TABLE workflow_sessions ADD COLUMN title TEXT;")
    except Exception:
        pass
    conn.execute(
        "UPDATE workflow_sessions SET title = ? WHERE session_id = ?;",
        (title, session_id),
    )
    conn.commit()


def update_session_state(
    conn: sqlite3.Connection, session_id: str, new_state: LifecycleState, updated_at: str
) -> None:
    conn.execute(
        "UPDATE workflow_sessions SET lifecycle_state = ?, updated_at = ? WHERE session_id = ?;",
        (new_state.value, updated_at, session_id),
    )


def insert_repair_plan(conn: sqlite3.Connection, plan: RepairPlan) -> None:
    roster_data = [item.model_dump() for item in plan.proposed_roster]
    conn.execute(
        """
        INSERT INTO repair_plans (
            plan_id, session_id, analysis_id, analysis_hash, version, selected_finding_ids_json, proposed_roster_json, status, created_at, expires_at, user_prompt, selected_joints_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            plan.plan_id,
            plan.session_id,
            plan.analysis_id,
            plan.analysis_hash,
            plan.version,
            json.dumps(plan.selected_finding_ids),
            json.dumps(roster_data),
            plan.status,
            plan.created_at,
            plan.expires_at,
            plan.user_prompt,
            json.dumps(plan.selected_joints) if plan.selected_joints is not None else None,
        ),
    )


def get_repair_plan(conn: sqlite3.Connection, plan_id: str) -> Optional[RepairPlan]:
    cursor = conn.execute("SELECT * FROM repair_plans WHERE plan_id = ?;", (plan_id,))
    row = cursor.fetchone()
    if not row:
        return None
    roster_raw = json.loads(row["proposed_roster_json"])
    roster = [AgentSpecification(**item) for item in roster_raw]
    user_prompt = row["user_prompt"] if "user_prompt" in row.keys() else None
    selected_joints_raw = row["selected_joints_json"] if "selected_joints_json" in row.keys() else None
    selected_joints = json.loads(selected_joints_raw) if selected_joints_raw else None
    return RepairPlan(
        plan_id=row["plan_id"],
        session_id=row["session_id"],
        analysis_id=row["analysis_id"],
        analysis_hash=row["analysis_hash"],
        version=row["version"],
        selected_finding_ids=json.loads(row["selected_finding_ids_json"]),
        user_prompt=user_prompt,
        selected_joints=selected_joints,
        proposed_roster=roster,
        status=row["status"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
    )


def approve_plan_transaction(
    conn: sqlite3.Connection, approval: Approval, updated_at: str
) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO approvals (
                approval_id, session_id, plan_id, repair_plan_version, analysis_hash,
                selected_finding_ids_json, roster_hash, approved_by, approved_at, valid_until,
                user_prompt, selected_joints_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                approval.approval_id,
                approval.session_id,
                approval.plan_id,
                approval.repair_plan_version,
                approval.analysis_hash,
                json.dumps(approval.selected_finding_ids),
                approval.roster_hash,
                approval.approved_by,
                approval.approved_at,
                approval.valid_until,
                approval.user_prompt,
                json.dumps(approval.selected_joints) if approval.selected_joints is not None else None,
            ),
        )
        conn.execute(
            "UPDATE repair_plans SET status = 'APPROVED' WHERE plan_id = ?;",
            (approval.plan_id,),
        )
        conn.execute(
            """
            UPDATE workflow_sessions
            SET lifecycle_state = 'APPROVED', approval_id = ?, plan_id = ?, updated_at = ?
            WHERE session_id = ?;
            """,
            (approval.approval_id, approval.plan_id, updated_at, approval.session_id),
        )


def reject_plan_transaction(
    conn: sqlite3.Connection, session_id: str, plan_id: str, updated_at: str
) -> None:
    with conn:
        conn.execute(
            "UPDATE repair_plans SET status = 'REJECTED' WHERE plan_id = ?;",
            (plan_id,),
        )
        conn.execute(
            """
            UPDATE workflow_sessions
            SET lifecycle_state = 'REVIEWING_FINDINGS', updated_at = ?
            WHERE session_id = ?;
            """,
            (updated_at, session_id),
        )


def get_approval(conn: sqlite3.Connection, approval_id: str) -> Optional[Approval]:
    cursor = conn.execute("SELECT * FROM approvals WHERE approval_id = ?;", (approval_id,))
    row = cursor.fetchone()
    if not row:
        return None
    user_prompt = row["user_prompt"] if "user_prompt" in row.keys() else None
    selected_joints_raw = row["selected_joints_json"] if "selected_joints_json" in row.keys() else None
    selected_joints = json.loads(selected_joints_raw) if selected_joints_raw else None
    return Approval(
        approval_id=row["approval_id"],
        session_id=row["session_id"],
        plan_id=row["plan_id"],
        repair_plan_version=row["repair_plan_version"],
        analysis_hash=row["analysis_hash"],
        selected_finding_ids=json.loads(row["selected_finding_ids_json"]),
        user_prompt=user_prompt,
        selected_joints=selected_joints,
        roster_hash=row["roster_hash"],
        approved_by=row["approved_by"],
        approved_at=row["approved_at"],
        valid_until=row["valid_until"],
    )


def list_workflow_sessions(conn: sqlite3.Connection, limit: int = 50) -> List[Dict[str, Any]]:
    base_query = """
    SELECT 
        w.session_id,
        w.asset_id,
        w.analysis_id,
        w.plan_id,
        w.approval_id,
        w.lifecycle_state,
        w.created_at,
        w.updated_at,
        a.filename,
        a.metadata_json,
        an.status AS analysis_status,
        an.diagnostic_summary,
        an.asset_id AS original_asset_id,
        (SELECT COUNT(*) FROM findings f WHERE f.analysis_id = w.analysis_id) AS findings_count
    FROM workflow_sessions w
    LEFT JOIN assets a ON w.asset_id = a.asset_id
    LEFT JOIN analyses an ON w.analysis_id = an.analysis_id
    ORDER BY w.created_at DESC
    LIMIT ?;
    """
    try:
        cursor = conn.execute("""
            SELECT 
                w.session_id,
                w.asset_id,
                w.analysis_id,
                w.plan_id,
                w.approval_id,
                w.lifecycle_state,
                w.title,
                w.created_at,
                w.updated_at,
                a.filename,
                a.metadata_json,
                an.status AS analysis_status,
                an.diagnostic_summary,
                an.asset_id AS original_asset_id,
                (SELECT COUNT(*) FROM findings f WHERE f.analysis_id = w.analysis_id) AS findings_count
            FROM workflow_sessions w
            LEFT JOIN assets a ON w.asset_id = a.asset_id
            LEFT JOIN analyses an ON w.analysis_id = an.analysis_id
            ORDER BY w.created_at DESC
            LIMIT ?;
        """, (limit,))
    except sqlite3.OperationalError:
        cursor = conn.execute(base_query, (limit,))

    results = []
    for row in cursor.fetchall():
        meta = {}
        try:
            if row["metadata_json"]:
                meta = json.loads(row["metadata_json"])
        except Exception:
            pass
        orig_id = row["original_asset_id"] or row["asset_id"]
        rep_id = row["asset_id"] if row["lifecycle_state"] == "COMPLETED" and row["asset_id"] != orig_id else None
        session_title = row["title"] if "title" in row.keys() and row["title"] else None
        if not session_title or is_uuid_like(session_title):
            session_title = generate_session_title(
                row["filename"],
                row["analysis_status"],
                row["diagnostic_summary"] if "diagnostic_summary" in row.keys() else None,
                row["findings_count"] or 0,
                meta.get("frame_count", 0),
            )
        results.append({
            "session_id": row["session_id"],
            "asset_id": row["asset_id"],
            "original_asset_id": orig_id,
            "repaired_asset_id": rep_id,
            "analysis_id": row["analysis_id"],
            "plan_id": row["plan_id"],
            "approval_id": row["approval_id"],
            "lifecycle_state": row["lifecycle_state"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "title": session_title,
            "filename": row["filename"] or "Unknown",
            "duration_seconds": meta.get("duration_seconds", 0.0),
            "frame_count": meta.get("frame_count", 0),
            "findings_count": row["findings_count"] or 0,
            "status": row["analysis_status"] or "UNKNOWN",
            "diagnostic_summary": row["diagnostic_summary"] if "diagnostic_summary" in row.keys() else None,
        })
    return results


def count_session_uploads(conn: sqlite3.Connection, session_id: str) -> int:
    cursor = conn.execute(
        "SELECT COUNT(*) FROM session_uploads WHERE session_id = ?;",
        (session_id,),
    )
    row = cursor.fetchone()
    return int(row[0]) if row else 0


def insert_session_upload(
    conn: sqlite3.Connection,
    session_id: str,
    asset_id: str,
    filename: str,
    uploaded_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO session_uploads (session_id, asset_id, filename, uploaded_at)
        VALUES (?, ?, ?, ?);
        """,
        (session_id, asset_id, filename, uploaded_at),
    )


def list_session_uploads(conn: sqlite3.Connection, session_id: str) -> List[Dict[str, Any]]:
    cursor = conn.execute(
        """
        SELECT id, session_id, asset_id, filename, uploaded_at
        FROM session_uploads
        WHERE session_id = ?
        ORDER BY id ASC;
        """,
        (session_id,),
    )
    return [
        {
            "id": row["id"],
            "session_id": row["session_id"],
            "asset_id": row["asset_id"],
            "filename": row["filename"],
            "uploaded_at": row["uploaded_at"],
        }
        for row in cursor.fetchall()
    ]


def insert_human_feedback(conn: sqlite3.Connection, feedback: HumanFeedback) -> None:
    action_val = feedback.action.value if hasattr(feedback.action, "value") else str(feedback.action)
    conn.execute(
        """
        INSERT OR REPLACE INTO human_feedback (
            feedback_id, asset_id, session_id, analysis_id, finding_id,
            action, joint, frame_start, frame_end, anomaly_type,
            confidence, notes, annotator, split, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            feedback.feedback_id,
            feedback.asset_id,
            feedback.session_id,
            feedback.analysis_id,
            feedback.finding_id,
            action_val,
            feedback.joint,
            feedback.frame_start,
            feedback.frame_end,
            feedback.anomaly_type,
            feedback.confidence,
            feedback.notes,
            feedback.annotator,
            feedback.split,
            feedback.created_at,
            feedback.updated_at,
        ),
    )


def get_human_feedback(conn: sqlite3.Connection, feedback_id: str) -> Optional[HumanFeedback]:
    cursor = conn.execute("SELECT * FROM human_feedback WHERE feedback_id = ?;", (feedback_id,))
    row = cursor.fetchone()
    if not row:
        return None
    return HumanFeedback(
        feedback_id=row["feedback_id"],
        asset_id=row["asset_id"],
        session_id=row["session_id"],
        analysis_id=row["analysis_id"],
        finding_id=row["finding_id"],
        action=ReviewAction(row["action"]),
        joint=row["joint"],
        frame_start=row["frame_start"],
        frame_end=row["frame_end"],
        anomaly_type=row["anomaly_type"],
        confidence=float(row["confidence"]) if "confidence" in row.keys() and row["confidence"] is not None else 1.0,
        notes=row["notes"],
        annotator=row["annotator"] if "annotator" in row.keys() and row["annotator"] else "human_reviewer",
        split=row["split"] if "split" in row.keys() and row["split"] else "dev",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def list_human_feedback(
    conn: sqlite3.Connection,
    asset_id: Optional[str] = None,
    session_id: Optional[str] = None,
    analysis_id: Optional[str] = None,
    action: Optional[str] = None,
    split: Optional[str] = None,
) -> List[HumanFeedback]:
    query = "SELECT * FROM human_feedback WHERE 1=1"
    params = []
    if asset_id:
        query += " AND asset_id = ?"
        params.append(asset_id)
    if session_id:
        query += " AND session_id = ?"
        params.append(session_id)
    if analysis_id:
        query += " AND analysis_id = ?"
        params.append(analysis_id)
    if action:
        query += " AND action = ?"
        params.append(action)
    if split:
        norm_split = split.lower().replace("_", "-")
        query += " AND (split = ? OR split = ?)"
        params.append(norm_split)
        params.append(norm_split.replace("-", "_"))
    query += " ORDER BY frame_start ASC, joint ASC, created_at ASC;"
    cursor = conn.execute(query, tuple(params))
    results = []
    for row in cursor.fetchall():
        results.append(
            HumanFeedback(
                feedback_id=row["feedback_id"],
                asset_id=row["asset_id"],
                session_id=row["session_id"],
                analysis_id=row["analysis_id"],
                finding_id=row["finding_id"],
                action=ReviewAction(row["action"]),
                joint=row["joint"],
                frame_start=row["frame_start"],
                frame_end=row["frame_end"],
                anomaly_type=row["anomaly_type"],
                confidence=float(row["confidence"]) if "confidence" in row.keys() and row["confidence"] is not None else 1.0,
                notes=row["notes"],
                annotator=row["annotator"] if "annotator" in row.keys() and row["annotator"] else "human_reviewer",
                split=row["split"] if "split" in row.keys() and row["split"] else "dev",
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        )
    return results


def delete_human_feedback(conn: sqlite3.Connection, feedback_id: str) -> bool:
    cursor = conn.execute("DELETE FROM human_feedback WHERE feedback_id = ?;", (feedback_id,))
    return cursor.rowcount > 0


def export_ground_truth_splits(
    conn: sqlite3.Connection, split_filter: Optional[str] = None
) -> Dict[str, Any]:
    norm_filter = split_filter.lower().replace("_", "-") if split_filter else None
    cursor = conn.execute("SELECT DISTINCT asset_id FROM human_feedback;")
    asset_ids = [row["asset_id"] for row in cursor.fetchall()]
    clips: Dict[str, Any] = {}
    for aid in asset_ids:
        asset = get_asset(conn, aid)
        if not asset:
            continue
        all_fb = list_human_feedback(conn, asset_id=aid)
        clip_split = "dev"
        for fb in all_fb:
            if fb.split:
                clip_split = fb.split.lower().replace("_", "-")
                break
        if norm_filter and norm_filter != "all" and clip_split != norm_filter:
            continue
        confirmed_defective = []
        confirmed_acceptable: Dict[str, List[List[int]]] = {}
        transition_uncertain: Dict[str, List[List[int]]] = {}
        originating_joints: List[str] = []
        for fb in all_fb:
            if fb.action in (ReviewAction.CONFIRM, ReviewAction.MARK_MISSED):
                if fb.joint not in originating_joints:
                    originating_joints.append(fb.joint)
                confirmed_defective.append(
                    {
                        "joint": fb.joint,
                        "role": "originating",
                        "frames_0_based": [fb.frame_start, fb.frame_end],
                        "frames_1_based": [fb.frame_start + 1, fb.frame_end + 1],
                        "anomaly_type": fb.anomaly_type or "ANOMALY",
                        "description": fb.notes or f"Human annotation {fb.action.value}",
                        "action": fb.action.value,
                    }
                )
            elif fb.action == ReviewAction.REJECT:
                if fb.joint not in confirmed_acceptable:
                    confirmed_acceptable[fb.joint] = []
                confirmed_acceptable[fb.joint].append([fb.frame_start, fb.frame_end])
            elif fb.action == ReviewAction.MARK_UNCERTAIN:
                if fb.joint not in transition_uncertain:
                    transition_uncertain[fb.joint] = []
                transition_uncertain[fb.joint].append([fb.frame_start, fb.frame_end])
        clip_entry = {
            "asset_id": asset.asset_id,
            "filename": asset.filename,
            "sha256": asset.content_hash,
            "split": clip_split,
            "frame_count": asset.metadata.frame_count if asset.metadata else 0,
            "frame_time": asset.metadata.frame_time if asset.metadata else 0.033333,
            "originating_joints": originating_joints,
            "confirmed_defective": confirmed_defective,
            "confirmed_acceptable": confirmed_acceptable,
            "transition_uncertain": transition_uncertain,
            "unreviewed": {},
        }
        clips[asset.filename] = clip_entry
    return {
        "manifest_version": "1.0.0",
        "split": split_filter or "all",
        "total_clips": len(clips),
        "clips": clips,
    }


def evaluate_false_alarms(
    conn: sqlite3.Connection, asset_id: str, analysis_id: Optional[str] = None
) -> Dict[str, Any]:
    target_analysis_id = analysis_id
    if not target_analysis_id:
        cursor = conn.execute(
            "SELECT analysis_id FROM analyses WHERE asset_id = ? ORDER BY created_at DESC LIMIT 1;",
            (asset_id,),
        )
        row = cursor.fetchone()
        if row:
            target_analysis_id = row["analysis_id"]

    analysis = get_analysis(conn, target_analysis_id) if target_analysis_id else None
    findings = analysis.findings if analysis else []
    all_feedbacks = list_human_feedback(conn, asset_id=asset_id)

    feedback_by_finding = {fb.finding_id: fb for fb in all_feedbacks if fb.finding_id}
    uncertain_feedbacks = [fb for fb in all_feedbacks if fb.action == ReviewAction.MARK_UNCERTAIN]
    rejected_feedbacks = [fb for fb in all_feedbacks if fb.action == ReviewAction.REJECT]
    confirmed_feedbacks = [
        fb for fb in all_feedbacks if fb.action in (ReviewAction.CONFIRM, ReviewAction.MARK_MISSED)
    ]
    missed_feedbacks = [fb for fb in all_feedbacks if fb.action == ReviewAction.MARK_MISSED]

    total_detections = len(findings)
    confirmed_detections = 0
    rejected_detections = 0
    uncertain_detections = 0
    excluded_uncertain_frames = 0
    evaluated_findings = []

    for f in findings:
        f_s, f_e = f.frame_start, f.frame_end
        j_unc = [u for u in uncertain_feedbacks if u.joint == f.affected_joint]
        finding_uncertain_frames = 0
        for frm in range(f_s, f_e + 1):
            if any(u.frame_start <= frm <= u.frame_end for u in j_unc):
                finding_uncertain_frames += 1
        excluded_uncertain_frames += finding_uncertain_frames

        fb = feedback_by_finding.get(f.finding_id)
        status = "UNREVIEWED"
        if fb:
            if fb.action == ReviewAction.CONFIRM:
                status = "CONFIRMED"
                confirmed_detections += 1
            elif fb.action == ReviewAction.REJECT:
                status = "REJECTED_FALSE_ALARM"
                rejected_detections += 1
            elif fb.action == ReviewAction.MARK_UNCERTAIN:
                status = "UNCERTAIN_EXCLUDED"
                uncertain_detections += 1
        else:
            overlaps_uncertain = any(
                max(f_s, u.frame_start) <= min(f_e, u.frame_end) for u in j_unc
            )
            overlaps_confirmed = any(
                c.joint == f.affected_joint and max(f_s, c.frame_start) <= min(f_e, c.frame_end)
                for c in confirmed_feedbacks
            )
            overlaps_rejected = any(
                r.joint == f.affected_joint and max(f_s, r.frame_start) <= min(f_e, r.frame_end)
                for r in rejected_feedbacks
            )
            if overlaps_uncertain and not overlaps_confirmed:
                status = "UNCERTAIN_EXCLUDED"
                uncertain_detections += 1
            elif overlaps_confirmed:
                status = "CONFIRMED"
                confirmed_detections += 1
            elif overlaps_rejected:
                status = "REJECTED_FALSE_ALARM"
                rejected_detections += 1
            elif rejected_feedbacks or confirmed_feedbacks:
                status = "FALSE_ALARM"
                rejected_detections += 1

        evaluated_findings.append(
            {
                "finding_id": f.finding_id,
                "joint": f.affected_joint,
                "interval": [f_s, f_e],
                "status": status,
                "excluded_uncertain_frames": finding_uncertain_frames,
            }
        )

    missed_detections = 0
    for m in missed_feedbacks:
        detected = any(
            f.affected_joint == m.joint and max(f.frame_start, m.frame_start) <= min(f.frame_end, m.frame_end)
            for f in findings
        )
        if not detected:
            missed_detections += 1

    false_alarms = rejected_detections
    tp = confirmed_detections
    fp = false_alarms
    fn = missed_detections

    precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else (1.0 if not findings else 0.0)
    recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else (1.0 if not missed_feedbacks else 0.0)

    return {
        "asset_id": asset_id,
        "analysis_id": target_analysis_id,
        "total_detections": total_detections,
        "confirmed_detections": confirmed_detections,
        "rejected_detections": rejected_detections,
        "uncertain_detections": uncertain_detections,
        "missed_detections": missed_detections,
        "false_alarms": false_alarms,
        "excluded_uncertain_frames": excluded_uncertain_frames,
        "precision": precision,
        "recall": recall,
        "details": {
            "evaluated_findings": evaluated_findings,
            "uncertain_intervals": [
                {"joint": u.joint, "interval": [u.frame_start, u.frame_end]}
                for u in uncertain_feedbacks
            ],
            "missed_intervals": [
                {"joint": m.joint, "interval": [m.frame_start, m.frame_end]}
                for m in missed_feedbacks
            ],
        },
    }


def save_chat_message(conn: sqlite3.Connection, session_id: str, message: Dict[str, Any]) -> None:
    msg_id = message.get("id") or f"msg-{uuid.uuid4().hex[:12]}"
    sender = message.get("sender", "assistant")
    timestamp = message.get("timestamp") or datetime.now(timezone.utc).isoformat()
    text = message.get("text", "")
    message_json = json.dumps(message)
    conn.execute(
        """
        INSERT INTO chat_messages (id, session_id, sender, timestamp, text, message_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            text = excluded.text,
            message_json = excluded.message_json,
            timestamp = excluded.timestamp;
        """,
        (msg_id, session_id, sender, timestamp, text, message_json, timestamp),
    )


def save_chat_messages(conn: sqlite3.Connection, session_id: str, messages: List[Dict[str, Any]]) -> None:
    for m in messages:
        if isinstance(m, dict):
            save_chat_message(conn, session_id, m)


def get_chat_messages(conn: sqlite3.Connection, session_id: str) -> List[Dict[str, Any]]:
    cursor = conn.execute(
        "SELECT message_json FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC;",
        (session_id,),
    )
    result = []
    for row in cursor.fetchall():
        try:
            result.append(json.loads(row["message_json"]))
        except Exception:
            pass
    return result


def delete_session_messages(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute("DELETE FROM chat_messages WHERE session_id = ?;", (session_id,))
