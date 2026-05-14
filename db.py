"""数据库初始化和工具函数 — 支持 SQLite（本地）和 PostgreSQL（Render）"""
import os
import re
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'class.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# 通过环境变量切换数据库：Render 上设 DATABASE_URL=postgresql://...
DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()

# 预定义学期列表
SEMESTER_DEFS = [
    ('七上', 0, 1),
    ('七下', 0, 2),
    ('八上', 1, 1),
    ('八下', 1, 2),
    ('九上', 2, 1),
    ('九下', 2, 2),
]

# ── SQL 兼容层 ────────────────────────────────────────
# SQLite → PostgreSQL 语法转换规则
_PG_SQL_REPLACEMENTS = [
    (r'`', r''),                                  # 移除反引号
    (r'\?', r'%s'),                               # 参数占位符
    (r"datetime\('now','localtime'\)", r'NOW()'), # 时间函数
    (r'last_insert_rowid\(\)', r'lastval()'),     # 自增ID
    (r'\bINTEGER PRIMARY KEY AUTOINCREMENT\b', r'SERIAL PRIMARY KEY'),
    (r'\bAUTOINCREMENT\b', r'SERIAL'),
    (r'\bINSERT OR IGNORE INTO\b', r'INSERT INTO'),
]

# 需要补加 ON CONFLICT DO NOTHING 的语句
_PG_INSERT_OR_IGNORE_RE = re.compile(r'\bINSERT OR IGNORE\b', re.IGNORECASE)


def _to_pg_sql(sql):
    """将 SQLite SQL 转换为 PostgreSQL 兼容语法"""
    original = sql
    # 替换 INSERT OR IGNORE（必须第一个执行，因为要判断 original）
    had_ignore = _PG_INSERT_OR_IGNORE_RE.search(original)
    for pattern, repl in _PG_SQL_REPLACEMENTS:
        sql = re.sub(pattern, repl, sql, flags=re.IGNORECASE)
    # INSERT OR IGNORE → 末尾加 ON CONFLICT DO NOTHING
    if had_ignore and 'ON CONFLICT DO NOTHING' not in sql.upper():
        sql = sql.rstrip(';') + ' ON CONFLICT DO NOTHING'
    return sql


# ── 数据库连接包装器 ──────────────────────────────────

class Database:
    """统一数据库接口，同时支持 SQLite 和 PostgreSQL"""

    def __init__(self):
        self._is_pg = bool(DATABASE_URL)
        self._last_insert_id = None
        if self._is_pg:
            self._init_pg()
        else:
            self._init_sqlite()

    def _init_sqlite(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")

    def _init_pg(self):
        import psycopg2
        import psycopg2.extras
        self.conn = psycopg2.connect(DATABASE_URL)
        self.conn.autocommit = True
        self._pg_cursor_factory = psycopg2.extras.RealDictCursor

    def execute(self, sql, params=None):
        if self._is_pg:
            sql = _to_pg_sql(sql)
            upper = sql.strip().upper()
            c = self.conn.cursor(cursor_factory=self._pg_cursor_factory)

            # SELECT lastval() → 返回储存的上次插入ID
            if upper == 'SELECT LASTVAL()' or upper.startswith('SELECT LASTVAL()'):
                fake = self.conn.cursor(cursor_factory=self._pg_cursor_factory)
                fake.execute(f"SELECT {self._last_insert_id or 0} AS id")
                return fake

            # INSERT 自动追加 RETURNING id（仅针对有 id 列的表）
            if upper.startswith('INSERT') and 'RETURNING' not in upper:
                m = re.search(r'INSERT\s+INTO\s+(\w+)', sql, re.IGNORECASE)
                if m and m.group(1) not in ('settings',):
                    sql = sql.rstrip(';') + ' RETURNING id'

            try:
                c.execute(sql, params or ())
            except Exception as e:
                # 记录失败SQL用于调试
                sql_preview = sql[:200].replace('\n', ' ')
                raise Exception(f'{e} | SQL: {sql_preview} | PARAMS: {params}')

            # 捕获 INSERT 返回的 ID
            if upper.startswith('INSERT'):
                try:
                    row = c.fetchone()
                    if row:
                        self._last_insert_id = row['id']
                except Exception:
                    pass

            return c
        else:
            if isinstance(params, (list, tuple)) and len(params) == 0:
                params = None
            return self.conn.execute(sql, params or ())

    def executescript(self, script):
        """SQLite 的 executescript 兼容：PostgreSQL 按语句拆分执行"""
        if self._is_pg:
            # 按分号拆分 SQL 语句，逐条执行
            for stmt in script.split(';'):
                stmt = stmt.strip()
                if stmt and not stmt.startswith('--'):
                    self.execute(stmt)
        else:
            self.conn.executescript(script)

    def commit(self):
        if not self._is_pg:
            self.conn.commit()

    def insert_id(self):
        """返回最后一次 INSERT 产生的自增 ID（兼容 SQLite 和 PostgreSQL）"""
        if self._is_pg:
            return self._last_insert_id
        c = self.conn.execute("SELECT last_insert_rowid()")
        return c.fetchone()[0]

    def close(self):
        self.conn.close()


# ── 公开 API ──────────────────────────────────────────

def get_db():
    return Database()


def init_db():
    """初始化数据库表"""
    db = get_db()
    db.executescript('''
    CREATE TABLE IF NOT EXISTS cohorts (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        grade       TEXT NOT NULL,
        class_no    TEXT NOT NULL,
        display_name TEXT,
        notes       TEXT,
        is_active   INTEGER DEFAULT 1,
        created_at  TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(grade, class_no)
    );

    CREATE TABLE IF NOT EXISTS semesters (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        cohort_id   INTEGER NOT NULL REFERENCES cohorts(id) ON DELETE CASCADE,
        name        TEXT NOT NULL,
        sort_order  INTEGER NOT NULL DEFAULT 0,
        year_range  TEXT,
        is_current  INTEGER DEFAULT 0,
        notes       TEXT,
        created_at  TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(cohort_id, name)
    );

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
        household_type TEXT,
        household_loc TEXT,
        father      TEXT,
        father_work TEXT,
        father_phone TEXT,
        mother      TEXT,
        mother_work TEXT,
        mother_phone TEXT,
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

    # 向后兼容：尝试补充旧数据库缺失的列
    for col in ('household_type', 'household_loc', 'father', 'father_work',
                'father_phone', 'mother', 'mother_work', 'mother_phone'):
        try:
            db.execute(f"ALTER TABLE students ADD COLUMN {col} TEXT")
        except Exception:
            pass

    db.commit()
    db.close()


def create_default_semesters(db, cohort_id, grade):
    """为新届次创建默认学期"""
    try:
        grade_year = int(grade) - 3
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
    row = db.execute("SELECT value FROM settings WHERE key = 'active_cohort_id'").fetchone()
    if row and row['value']:
        try:
            return int(row['value'])
        except (ValueError, TypeError):
            pass
    return None


def set_active_cohort_id(db, cohort_id):
    db.execute("""
        INSERT INTO settings (key, value) VALUES ('active_cohort_id', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (str(cohort_id),))
    db.commit()


def get_active_semester_id(db):
    row = db.execute("SELECT value FROM settings WHERE key = 'active_semester_id'").fetchone()
    if row and row['value']:
        try:
            return int(row['value'])
        except (ValueError, TypeError):
            pass
    return None


def set_active_semester_id(db, semester_id):
    db.execute("""
        INSERT INTO settings (key, value) VALUES ('active_semester_id', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (str(semester_id),))
    db.commit()


def dict_from_row(row):
    if row is None:
        return None
    return dict(row)


def dicts_from_rows(rows):
    return [dict(r) for r in rows]
