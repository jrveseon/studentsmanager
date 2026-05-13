"""数据库初始化和工具函数"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'class.db')

# 确保 data 目录存在（部署到 Render 等平台时需要）
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# 预定义学期列表（按入学年份自动计算）
SEMESTER_DEFS = [
    ('七上', 0, 1),  # (名称, 年偏移, 学期序号)
    ('七下', 0, 2),
    ('八上', 1, 1),
    ('八下', 1, 2),
    ('九上', 2, 1),
    ('九下', 2, 2),
]


def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript('''
    -- 届次表（每届独立管理）
    CREATE TABLE IF NOT EXISTS cohorts (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        grade       TEXT NOT NULL,         -- 届次，如 "2028"
        class_no    TEXT NOT NULL,         -- 班号，如 "11"
        display_name TEXT,                 -- 显示名，如 "2028届11班"
        notes       TEXT,
        is_active   INTEGER DEFAULT 1,     -- 是否在管理中
        created_at  TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(grade, class_no)
    );

    -- 学期表（属于某个届次）
    CREATE TABLE IF NOT EXISTS semesters (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        cohort_id   INTEGER NOT NULL REFERENCES cohorts(id) ON DELETE CASCADE,
        name        TEXT NOT NULL,         -- "七上"、"七下"、"八上" 等
        sort_order  INTEGER NOT NULL DEFAULT 0,  -- 排序序号
        year_range  TEXT,                  -- "2028-2029" 等
        is_current  INTEGER DEFAULT 0,     -- 是否当前学期
        notes       TEXT,
        created_at  TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(cohort_id, name)
    );

    -- 当前活跃届次和学期（全局设置）
    CREATE TABLE IF NOT EXISTS settings (
        key   TEXT PRIMARY KEY,
        value TEXT
    );

    CREATE TABLE IF NOT EXISTS students (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        cohort_id   INTEGER NOT NULL REFERENCES cohorts(id) ON DELETE CASCADE,
        student_no  TEXT NOT NULL,
        name        TEXT NOT NULL,
        gender      TEXT,
        birth_date  TEXT,
        ethnicity   TEXT,
        id_number   TEXT,
        group_name  TEXT,
        group_order INTEGER,
        phone       TEXT,
        parent_phone TEXT,
        address     TEXT,
        household_type TEXT,       -- 户口类别
        household_loc TEXT,        -- 户口所在地
        father      TEXT,          -- 父亲姓名
        father_work TEXT,          -- 父亲工作单位
        father_phone TEXT,         -- 父亲电话
        mother      TEXT,          -- 母亲姓名
        mother_work TEXT,          -- 母亲工作单位
        mother_phone TEXT,         -- 母亲电话
        notes       TEXT,
        is_active   INTEGER DEFAULT 1,
        created_at  TEXT DEFAULT (datetime('now','localtime')),
        updated_at  TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(cohort_id, student_no)
    );

    CREATE TABLE IF NOT EXISTS score_exams (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        cohort_id   INTEGER NOT NULL REFERENCES cohorts(id) ON DELETE CASCADE,
        semester_id INTEGER REFERENCES semesters(id) ON DELETE SET NULL,
        name        TEXT NOT NULL,
        exam_type   TEXT NOT NULL,
        exam_date   TEXT,
        notes       TEXT,
        created_at  TEXT DEFAULT (datetime('now','localtime'))
    );

    CREATE TABLE IF NOT EXISTS score_items (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_id     INTEGER NOT NULL REFERENCES score_exams(id) ON DELETE CASCADE,
        student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
        subject     TEXT NOT NULL,
        score       REAL,
        class_rank  INTEGER,
        UNIQUE(exam_id, student_id, subject)
    );

    CREATE TABLE IF NOT EXISTS weekly_points (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
        semester_id INTEGER REFERENCES semesters(id) ON DELETE SET NULL,
        week_num    INTEGER NOT NULL,
        score       REAL NOT NULL,
        source      TEXT,
        notes       TEXT,
        created_at  TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(student_id, week_num, semester_id)
    );

    CREATE TABLE IF NOT EXISTS events (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
        event_type  TEXT NOT NULL,
        title       TEXT NOT NULL,
        description TEXT,
        event_date  TEXT NOT NULL,
        severity    TEXT,
        follow_up   TEXT,
        created_at  TEXT DEFAULT (datetime('now','localtime'))
    );

    CREATE INDEX IF NOT EXISTS idx_students_cohort ON students(cohort_id);
    CREATE INDEX IF NOT EXISTS idx_semesters_cohort ON semesters(cohort_id);
    CREATE INDEX IF NOT EXISTS idx_score_exams_cohort ON score_exams(cohort_id);
    CREATE INDEX IF NOT EXISTS idx_score_exams_semester ON score_exams(semester_id);
    CREATE INDEX IF NOT EXISTS idx_score_items_exam ON score_items(exam_id);
    CREATE INDEX IF NOT EXISTS idx_score_items_student ON score_items(student_id);
    CREATE INDEX IF NOT EXISTS idx_weekly_points_student ON weekly_points(student_id);
    CREATE INDEX IF NOT EXISTS idx_weekly_points_semester ON weekly_points(semester_id);
    CREATE INDEX IF NOT EXISTS idx_weekly_points_week ON weekly_points(week_num, semester_id);
    CREATE INDEX IF NOT EXISTS idx_events_student ON events(student_id);
    CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date);
    ''')

    # 迁移：已有数据库添加新列
    try:
        conn.execute("ALTER TABLE students ADD COLUMN household_type TEXT")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE students ADD COLUMN household_loc TEXT")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE students ADD COLUMN father TEXT")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE students ADD COLUMN father_work TEXT")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE students ADD COLUMN father_phone TEXT")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE students ADD COLUMN mother TEXT")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE students ADD COLUMN mother_work TEXT")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE students ADD COLUMN mother_phone TEXT")
    except Exception:
        pass

    conn.commit()
    conn.close()


def create_default_semesters(db, cohort_id, grade):
    """为新届次创建6个默认学期
    届次是毕业年份，入学年份 = 届次 - 3
    例如：2028届 → 入学2025年 → 七上 2025-2026
    """
    try:
        grade_year = int(grade) - 3  # 届次是毕业年份，往前推3年
    except (ValueError, TypeError):
        grade_year = 2025

    for i, (name, year_offset, term) in enumerate(SEMESTER_DEFS):
        start_year = grade_year + year_offset
        end_year = start_year + 1
        year_range = f'{start_year}-{end_year}'
        db.execute("""
            INSERT OR IGNORE INTO semesters (cohort_id, name, sort_order, year_range)
            VALUES (?, ?, ?, ?)
        """, (cohort_id, name, i, year_range))
    db.commit()


def get_active_cohort_id(db):
    """获取当前活跃届次ID"""
    row = db.execute("SELECT value FROM settings WHERE key = 'active_cohort_id'").fetchone()
    if row and row['value']:
        try:
            return int(row['value'])
        except (ValueError, TypeError):
            pass
    return None


def set_active_cohort_id(db, cohort_id):
    """设置当前活跃届次"""
    db.execute("""
        INSERT INTO settings (key, value) VALUES ('active_cohort_id', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (str(cohort_id),))
    db.commit()


def get_active_semester_id(db):
    """获取当前活跃学期ID"""
    row = db.execute("SELECT value FROM settings WHERE key = 'active_semester_id'").fetchone()
    if row and row['value']:
        try:
            return int(row['value'])
        except (ValueError, TypeError):
            pass
    return None


def set_active_semester_id(db, semester_id):
    """设置当前活跃学期"""
    db.execute("""
        INSERT INTO settings (key, value) VALUES ('active_semester_id', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (str(semester_id),))
    db.commit()


def dict_from_row(row):
    """将 sqlite3.Row 转为 dict"""
    if row is None:
        return None
    return dict(row)


def dicts_from_rows(rows):
    """将多行转为 dict 列表"""
    return [dict(r) for r in rows]


if __name__ == '__main__':
    init_db()
    print(f"Database initialized at: {DB_PATH}")
