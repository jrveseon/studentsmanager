"""班级管理系统 - Flask 主应用"""
import os
import json
import uuid
from datetime import datetime, date
from flask import Flask, render_template, request, jsonify, g, session, send_from_directory
from db import (get_db, init_db, dict_from_row, dicts_from_rows,
                get_active_cohort_id, set_active_cohort_id,
                get_active_semester_id, set_active_semester_id,
                create_default_semesters)

app = Flask(__name__)
app.config['DATABASE'] = os.path.join(os.path.dirname(__file__), 'data', 'class.db')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.secret_key = os.environ.get('FLASK_SECRET', 'sun-class-manager-2024-default-key')

# 确保数据库初始化（gunicorn 导入时触发，不依赖 __main__）
init_db()


def get_cohort_info():
    cid = get_active_cohort_id(g.db)
    if cid:
        row = g.db.execute("SELECT * FROM cohorts WHERE id = ?", (cid,)).fetchone()
        if row:
            return dict_from_row(row)
    return None


def get_semester_info():
    sid = get_active_semester_id(g.db)
    if sid:
        row = g.db.execute("SELECT * FROM semesters WHERE id = ?", (sid,)).fetchone()
        if row:
            return dict_from_row(row)
    return None


def require_cohort():
    return get_active_cohort_id(g.db)


def require_semester():
    return get_active_semester_id(g.db)


def restore_from_session():
    """从 Flask session 恢复届次/学期（解决 Render 等平台数据库重置问题）"""
    cid = session.get('active_cohort_id')
    sid = session.get('active_semester_id')
    if cid:
        db_cid = get_active_cohort_id(g.db)
        if not db_cid:
            # 数据库被重置了，尝试从 session 恢复
            row = g.db.execute("SELECT id FROM cohorts WHERE id = ?", (cid,)).fetchone()
            if row:
                set_active_cohort_id(g.db, cid)
    if sid:
        db_sid = get_active_semester_id(g.db)
        if not db_sid:
            row = g.db.execute("SELECT id FROM semesters WHERE id = ?", (sid,)).fetchone()
            if row:
                set_active_semester_id(g.db, sid)


# ── 连接管理 ───────────────────────────────────────────
@app.before_request
def before_request():
    g.db = get_db()
    # 从 session 恢复届次/学期信息（应对 Render 等平台数据库重置）
    restore_from_session()


@app.teardown_request
def teardown_request(exception):
    db = getattr(g, 'db', None)
    if db is not None:
        db.close()


@app.context_processor
def inject_context():
    try:
        cohort = get_cohort_info()
        semester = get_semester_info()
        cohorts = dicts_from_rows(g.db.execute(
            "SELECT * FROM cohorts WHERE is_active = 1 ORDER BY grade DESC, class_no"
        ).fetchall())
        semesters = []
        if cohort:
            semesters = dicts_from_rows(g.db.execute(
                "SELECT * FROM semesters WHERE cohort_id = ? ORDER BY sort_order", (cohort['id'],)
            ).fetchall())
        return {'cohort': cohort, 'cohorts': cohorts, 'semester': semester, 'semesters': semesters}
    except Exception:
        return {'cohort': None, 'cohorts': [], 'semester': None, 'semesters': []}


# ── 页面路由 ───────────────────────────────────────────
@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/ai')
def ai_chat_page():
    return render_template('ai.html')

@app.route('/students')
def students_page():
    return render_template('students.html')

@app.route('/students/<int:sid>')
def student_detail_page(sid):
    return render_template('student_detail.html', student_id=sid)

@app.route('/points')
def points_page():
    return render_template('points.html')

@app.route('/scores')
def scores_page():
    return render_template('scores.html')

@app.route('/events')
def events_page():
    return render_template('events.html')

@app.route('/import')
def import_page():
    return render_template('import.html')


@app.route('/import/template/<name>')
def download_import_template(name):
    """下载导入模板"""
    template_dir = os.path.join(os.path.dirname(__file__), 'static', 'templates')
    files = {
        'students': '学生信息导入模板.xlsx',
        'points': '量化积分导入模板.xlsx',
        'scores': '考试成绩导入模板.xlsx',
    }
    if name not in files:
        return '模板不存在', 404
    return send_from_directory(template_dir, files[name], as_attachment=True)

@app.route('/settings')
def settings_page():
    return render_template('settings.html')


# ── 通用设置 API ───────────────────────────────────────
@app.route('/api/settings', methods=['GET'])
def get_all_settings_api():
    """获取所有设置（AI配置等全局设置）"""
    rows = g.db.execute("SELECT key, value FROM settings").fetchall()
    return jsonify({r['key']: r['value'] for r in rows})


@app.route('/api/settings', methods=['POST'])
def save_settings_api():
    """保存设置"""
    data = request.json
    for key, value in data.items():
        g.db.execute("""
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, str(value)))
    g.db.commit()
    return jsonify({'ok': True})


# ── 届次 API ───────────────────────────────────────────
@app.route('/api/cohorts', methods=['GET'])
def get_cohorts():
    rows = g.db.execute("SELECT * FROM cohorts WHERE is_active = 1 ORDER BY grade DESC, class_no").fetchall()
    return jsonify(dicts_from_rows(rows))


@app.route('/api/cohorts/archived', methods=['GET'])
def get_archived_cohorts():
    rows = g.db.execute("SELECT * FROM cohorts WHERE is_active = 0 ORDER BY grade DESC, class_no").fetchall()
    return jsonify(dicts_from_rows(rows))


@app.route('/api/cohorts/<int:cid>/restore', methods=['POST'])
def restore_cohort(cid):
    g.db.execute("UPDATE cohorts SET is_active = 1 WHERE id = ?", (cid,))
    g.db.commit()
    return jsonify({'ok': True})


@app.route('/api/cohorts', methods=['POST'])
def create_cohort():
    data = request.json
    grade = data.get('grade', '').strip()
    class_no = data.get('class_no', '').strip()
    if not grade or not class_no:
        return jsonify({'ok': False, 'error': '届次和班号必填'}), 400
    display_name = f'{grade}届{class_no}班'
    try:
        g.db.execute("""
            INSERT INTO cohorts (grade, class_no, display_name, notes)
            VALUES (?, ?, ?, ?)
        """, (grade, class_no, display_name, data.get('notes', '')))
        g.db.commit()
        cid = g.db.insert_id()
        # 自动创建6个学期
        create_default_semesters(g.db, cid, grade)
        cnt = g.db.execute("SELECT COUNT(*) as c FROM cohorts").fetchone()['c']
        if cnt == 1:
            set_active_cohort_id(g.db, cid)
            # 自动选第一个学期
            first_sem = g.db.execute("SELECT id FROM semesters WHERE cohort_id = ? ORDER BY sort_order LIMIT 1", (cid,)).fetchone()
            if first_sem:
                set_active_semester_id(g.db, first_sem['id'])
        return jsonify({'ok': True, 'id': cid})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


@app.route('/api/cohorts/<int:cid>', methods=['PUT'])
def update_cohort(cid):
    data = request.json
    fields = ['grade', 'class_no', 'display_name', 'notes', 'is_active']
    sets, params = [], []
    for f in fields:
        if f in data:
            sets.append(f"{f} = ?")
            params.append(data[f])
    if not sets:
        return jsonify({'ok': False, 'error': '无更新内容'}), 400
    params.append(cid)
    g.db.execute(f"UPDATE cohorts SET {', '.join(sets)} WHERE id = ?", params)
    g.db.commit()
    return jsonify({'ok': True})


@app.route('/api/cohorts/<int:cid>', methods=['DELETE'])
def delete_cohort(cid):
    permanent = request.args.get('permanent', '').lower() in ('1', 'true', 'yes')
    if permanent:
        # 硬删除：需要先关联合法学生的数据
        db = g.db
        db.execute("DELETE FROM events WHERE student_id IN (SELECT id FROM students WHERE cohort_id = ?)", (cid,))
        db.execute("DELETE FROM weekly_points WHERE student_id IN (SELECT id FROM students WHERE cohort_id = ?)", (cid,))
        db.execute("DELETE FROM score_items WHERE student_id IN (SELECT id FROM students WHERE cohort_id = ?)", (cid,))
        exam_ids = db.execute("SELECT id FROM score_exams WHERE cohort_id = ?", (cid,)).fetchall()
        for e in exam_ids:
            db.execute("DELETE FROM score_items WHERE exam_id = ?", (e['id'],))
        db.execute("DELETE FROM score_exams WHERE cohort_id = ?", (cid,))
        db.execute("DELETE FROM semesters WHERE cohort_id = ?", (cid,))
        db.execute("DELETE FROM students WHERE cohort_id = ?", (cid,))
        db.execute("DELETE FROM cohorts WHERE id = ?", (cid,))
    else:
        # 软删除（归档）
        g.db.execute("UPDATE cohorts SET is_active = 0 WHERE id = ?", (cid,))
    active_id = get_active_cohort_id(g.db)
    if active_id == cid:
        row = g.db.execute("SELECT id FROM cohorts WHERE is_active = 1 ORDER BY grade DESC LIMIT 1").fetchone()
        if row:
            set_active_cohort_id(g.db, row['id'])
        else:
            g.db.execute("DELETE FROM settings WHERE key IN ('active_cohort_id','active_semester_id')")
    g.db.commit()
    return jsonify({'ok': True})


@app.route('/api/cohorts/active', methods=['GET'])
def get_active_cohort():
    info = get_cohort_info()
    return jsonify({'ok': bool(info), 'cohort': info})


@app.route('/api/cohorts/active', methods=['POST'])
def switch_active_cohort():
    try:
        data = request.json
        cid = data.get('cohort_id')
        if not cid:
            return jsonify({'ok': False, 'error': '缺少cohort_id'}), 400
        row = g.db.execute("SELECT * FROM cohorts WHERE id = ?", (cid,)).fetchone()
        if not row:
            return jsonify({'ok': False, 'error': '届次不存在'}), 404
        set_active_cohort_id(g.db, cid)
        session['active_cohort_id'] = cid
        first_sem = g.db.execute("SELECT id FROM semesters WHERE cohort_id = ? ORDER BY sort_order LIMIT 1", (cid,)).fetchone()
        if first_sem:
            set_active_semester_id(g.db, first_sem['id'])
            session['active_semester_id'] = first_sem['id']
        return jsonify({'ok': True, 'cohort': dict_from_row(row)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


# ── 学期 API ───────────────────────────────────────────
@app.route('/api/semesters', methods=['GET'])
def get_semesters():
    cid = require_cohort()
    if not cid:
        return jsonify([])
    rows = g.db.execute(
        "SELECT * FROM semesters WHERE cohort_id = ? ORDER BY sort_order", (cid,)
    ).fetchall()
    return jsonify(dicts_from_rows(rows))


@app.route('/api/semesters/active', methods=['GET'])
def get_active_semester():
    info = get_semester_info()
    return jsonify({'ok': bool(info), 'semester': info})


@app.route('/api/semesters/active', methods=['POST'])
def switch_active_semester():
    try:
        data = request.json
        sid = data.get('semester_id')
        if not sid:
            return jsonify({'ok': False, 'error': '缺少semester_id'}), 400
        row = g.db.execute("SELECT * FROM semesters WHERE id = ?", (sid,)).fetchone()
        if not row:
            return jsonify({'ok': False, 'error': '学期不存在'}), 404
        set_active_semester_id(g.db, sid)
        session['active_semester_id'] = sid
        return jsonify({'ok': True, 'semester': dict_from_row(row)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


@app.route('/api/semesters/<int:sid>', methods=['PUT'])
def update_semester(sid):
    data = request.json
    fields = ['name', 'year_range', 'notes', 'is_current']
    sets, params = [], []
    for f in fields:
        if f in data:
            sets.append(f"{f} = ?")
            params.append(data[f])
    if not sets:
        return jsonify({'ok': False, 'error': '无更新内容'}), 400
    params.append(sid)
    g.db.execute(f"UPDATE semesters SET {', '.join(sets)} WHERE id = ?", params)
    g.db.commit()
    return jsonify({'ok': True})


# ── 学生 API ───────────────────────────────────────────
@app.route('/api/students', methods=['GET'])
def get_students():
    cid = require_cohort()
    if not cid:
        return jsonify([])
    search = request.args.get('search', '').strip()
    group = request.args.get('group', '').strip()
    active = request.args.get('active', '1')
    query = "SELECT * FROM students WHERE cohort_id = ?"
    params = [cid]
    if active:
        query += " AND is_active = ?"
        params.append(int(active))
    if search:
        query += " AND (name LIKE ? OR student_no LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%'])
    if group:
        query += " AND group_name = ?"
        params.append(group)
    query += " ORDER BY CAST(student_no AS INTEGER), student_no"
    return jsonify(dicts_from_rows(g.db.execute(query, params).fetchall()))


@app.route('/api/students', methods=['POST'])
def create_student():
    cid = require_cohort()
    if not cid:
        return jsonify({'ok': False, 'error': '请先选择届次'}), 400
    data = request.json
    try:
        g.db.execute("""
            INSERT INTO students (cohort_id, student_no, name, gender, birth_date, ethnicity,
                id_number, group_name, group_order, phone, parent_phone, address,
                household_type, household_loc, father, father_work, father_phone,
                mother, mother_work, mother_phone, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?)
        """, (cid, data['student_no'], data['name'], data.get('gender'),
              data.get('birth_date'), data.get('ethnicity'), data.get('id_number'),
              data.get('group_name'), data.get('group_order'),
              data.get('phone'), data.get('parent_phone'),
              data.get('address'),
              data.get('household_type'), data.get('household_loc'),
              data.get('father'), data.get('father_work'), data.get('father_phone'),
              data.get('mother'), data.get('mother_work'), data.get('mother_phone'),
              data.get('notes')))
        g.db.commit()
        return jsonify({'ok': True, 'id': g.db.insert_id()})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


@app.route('/api/students/<int:sid>', methods=['GET'])
def get_student(sid):
    row = g.db.execute("SELECT * FROM students WHERE id = ?", (sid,)).fetchone()
    if not row:
        return jsonify({'error': '未找到'}), 404
    return jsonify(dict_from_row(row))


@app.route('/api/students/<int:sid>', methods=['PUT'])
def update_student(sid):
    data = request.json
    fields = ['student_no', 'name', 'gender', 'birth_date', 'ethnicity',
              'id_number', 'group_name', 'group_order', 'phone', 'parent_phone',
              'address', 'household_type', 'household_loc',
              'father', 'father_work', 'father_phone',
              'mother', 'mother_work', 'mother_phone',
              'notes', 'is_active']
    sets, params = [], []
    for f in fields:
        if f in data:
            sets.append(f"{f} = ?")
            params.append(data[f])
    if not sets:
        return jsonify({'ok': False, 'error': '无更新内容'}), 400
    sets.append("updated_at = datetime('now','localtime')")
    params.append(sid)
    g.db.execute(f"UPDATE students SET {', '.join(sets)} WHERE id = ?", params)
    g.db.commit()
    return jsonify({'ok': True})


@app.route('/api/students/<int:sid>', methods=['DELETE'])
def delete_student(sid):
    g.db.execute("UPDATE students SET is_active = 0, updated_at = datetime('now','localtime') WHERE id = ?", (sid,))
    g.db.commit()
    return jsonify({'ok': True})


@app.route('/api/students/batch/delete', methods=['POST'])
def batch_delete_students():
    """批量删除（软删除）"""
    data = request.json
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'ok': False, 'error': '请选择学生'}), 400
    placeholders = ','.join(['?'] * len(ids))
    g.db.execute(f"UPDATE students SET is_active = 0, updated_at = datetime('now','localtime') WHERE id IN ({placeholders})", ids)
    g.db.commit()
    return jsonify({'ok': True, 'count': len(ids)})


@app.route('/api/students/batch/group', methods=['POST'])
def batch_set_group():
    """批量设置小组"""
    data = request.json
    ids = data.get('ids', [])
    group_name = data.get('group_name', '').strip()
    if not ids:
        return jsonify({'ok': False, 'error': '请选择学生'}), 400
    if not group_name:
        return jsonify({'ok': False, 'error': '请填写小组名称'}), 400
    placeholders = ','.join(['?'] * len(ids))
    g.db.execute(f"UPDATE students SET group_name = ?, updated_at = datetime('now','localtime') WHERE id IN ({placeholders})", [group_name] + ids)
    g.db.commit()
    return jsonify({'ok': True, 'count': len(ids)})


@app.route('/api/groups', methods=['GET'])
def get_groups():
    cid = require_cohort()
    if not cid:
        return jsonify([])
    rows = g.db.execute(
        "SELECT DISTINCT group_name FROM students WHERE cohort_id = ? AND group_name IS NOT NULL AND is_active = 1 ORDER BY group_name",
        (cid,)
    ).fetchall()
    return jsonify([r['group_name'] for r in rows])


# ── 积分 API（改用 semester_id）──────────────────────────
@app.route('/api/points', methods=['GET'])
def get_points():
    cid = require_cohort()
    if not cid:
        return jsonify([])
    semester_id = request.args.get('semester_id', '')
    week = request.args.get('week', '')
    student_id = request.args.get('student_id', '')
    query = """
        SELECT wp.*, s.name, s.student_no, s.group_name, sm.name as semester_name
        FROM weekly_points wp
        JOIN students s ON wp.student_id = s.id
        LEFT JOIN semesters sm ON wp.semester_id = sm.id
        WHERE s.cohort_id = ?
    """
    params = [cid]
    if semester_id:
        query += " AND wp.semester_id = ?"
        params.append(int(semester_id))
    if week:
        query += " AND wp.week_num = ?"
        params.append(int(week))
    if student_id:
        query += " AND wp.student_id = ?"
        params.append(int(student_id))
    query += " ORDER BY wp.week_num DESC, s.student_no"
    return jsonify(dicts_from_rows(g.db.execute(query, params).fetchall()))


@app.route('/api/points/summary', methods=['GET'])
def get_points_summary():
    """入学以来总分（跨所有学期）"""
    cid = require_cohort()
    if not cid:
        return jsonify({'students': []})
    rows = g.db.execute("""
        SELECT s.id, s.student_no, s.name, s.group_name,
               COALESCE(SUM(wp.score), 0) as total_score,
               COUNT(DISTINCT wp.semester_id || '-' || wp.week_num) as week_count
        FROM students s
        LEFT JOIN weekly_points wp ON s.id = wp.student_id
        WHERE s.cohort_id = ? AND s.is_active = 1
        GROUP BY s.id ORDER BY total_score DESC, s.student_no
    """, (cid,)).fetchall()
    result = dicts_from_rows(rows)
    for i, r in enumerate(result):
        r['rank'] = i + 1
    return jsonify({'students': result})


@app.route('/api/points/semester_summary', methods=['GET'])
def get_points_semester_summary():
    """某学期积分汇总"""
    cid = require_cohort()
    if not cid:
        return jsonify({'semester_id': '', 'students': []})
    semester_id = request.args.get('semester_id', '')
    if not semester_id:
        sid = get_active_semester_id(g.db)
        semester_id = str(sid) if sid else ''
    rows = g.db.execute("""
        SELECT s.id, s.student_no, s.name, s.group_name,
               COALESCE(SUM(wp.score), 0) as total_score,
               COUNT(wp.id) as week_count
        FROM students s
        LEFT JOIN weekly_points wp ON s.id = wp.student_id AND wp.semester_id = ?
        WHERE s.cohort_id = ? AND s.is_active = 1
        GROUP BY s.id ORDER BY total_score DESC, s.student_no
    """, (int(semester_id), cid)).fetchall() if semester_id else []
    result = dicts_from_rows(rows) if semester_id else []
    for i, r in enumerate(result):
        r['rank'] = i + 1
    return jsonify({'semester_id': semester_id, 'students': result})


@app.route('/api/points/weekly_summary', methods=['GET'])
def get_points_weekly_summary():
    """某周积分汇总"""
    cid = require_cohort()
    if not cid:
        return jsonify({'semester_id': '', 'week': 0, 'students': []})
    semester_id = request.args.get('semester_id', '')
    week = request.args.get('week', '')
    if not semester_id:
        sid = get_active_semester_id(g.db)
        semester_id = str(sid) if sid else ''
    if not semester_id:
        return jsonify({'semester_id': '', 'week': 0, 'students': []})
    if not week:
        row = g.db.execute("""
            SELECT MAX(wp.week_num) as w FROM weekly_points wp
            JOIN students s ON wp.student_id = s.id
            WHERE s.cohort_id = ? AND wp.semester_id = ?
        """, (cid, int(semester_id))).fetchone()
        week = str(row['w']) if row and row['w'] else '0'
    rows = g.db.execute("""
        SELECT s.id, s.student_no, s.name, s.group_name,
               COALESCE(wp.score, 0) as week_score
        FROM students s
        LEFT JOIN weekly_points wp ON s.id = wp.student_id AND wp.semester_id = ? AND wp.week_num = ?
        WHERE s.cohort_id = ? AND s.is_active = 1
        ORDER BY week_score DESC, s.student_no
    """, (int(semester_id), int(week), cid)).fetchall()
    result = dicts_from_rows(rows)
    for i, r in enumerate(result):
        r['rank'] = i + 1
    return jsonify({'semester_id': semester_id, 'week': int(week), 'students': result})


@app.route('/api/points', methods=['POST'])
def save_points():
    data = request.json
    semester_id = data.get('semester_id') or get_active_semester_id(g.db)
    week_num = data['week_num']
    records = data['records']
    if not semester_id:
        return jsonify({'ok': False, 'error': '请先选择学期'}), 400
    for rec in records:
        g.db.execute("""
            INSERT INTO weekly_points (student_id, week_num, semester_id, score, source, notes)
            VALUES (?, ?, ?, ?, 'manual', ?)
            ON CONFLICT(student_id, week_num, semester_id)
            DO UPDATE SET score = excluded.score, notes = excluded.notes
        """, (rec['student_id'], week_num, semester_id, rec['score'], rec.get('notes', '')))
    g.db.commit()
    return jsonify({'ok': True, 'count': len(records)})


@app.route('/api/points/parse_file', methods=['POST'])
def parse_points_file():
    cid = require_cohort()
    if not cid:
        return jsonify({'ok': False, 'error': '请先选择届次'}), 400
    from import_data import parse_points_excel
    if 'file' not in request.files:
        return jsonify({'ok': False, 'error': '未上传文件'}), 400
    f = request.files['file']
    semester = request.form.get('semester', '')
    ext = f.filename.rsplit('.', 1)[-1].lower()
    tmp_path = os.path.join(os.path.dirname(__file__), 'data', '_tmp_parse.' + ext)
    f.save(tmp_path)
    try:
        records = parse_points_excel(tmp_path, semester)
        students = g.db.execute(
            "SELECT id, name FROM students WHERE cohort_id = ? AND is_active = 1", (cid,)
        ).fetchall()
        student_map = {s['name']: s['id'] for s in students}
        result, unmatched = [], []
        for rec in records:
            sid = student_map.get(rec['name'])
            if sid:
                for week_num, score in rec['weeks'].items():
                    if score is not None:
                        result.append({'student_id': sid, 'name': rec['name'], 'week_num': week_num, 'score': score})
            else:
                unmatched.append(rec['name'])
        weeks = sorted(set(r['week_num'] for r in result)) if result else []
        return jsonify({
            'ok': True, 'records': result, 'weeks': weeks, 'unmatched': unmatched,
            'total_names': len(records), 'matched_names': len(records) - len(unmatched)
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.route('/api/points/weeks', methods=['GET'])
def get_point_weeks():
    cid = require_cohort()
    if not cid:
        return jsonify([])
    semester_id = request.args.get('semester_id', '')
    query = """
        SELECT DISTINCT wp.week_num, wp.semester_id, sm.name as semester_name
        FROM weekly_points wp
        JOIN students s ON wp.student_id = s.id
        LEFT JOIN semesters sm ON wp.semester_id = sm.id
        WHERE s.cohort_id = ?
    """
    params = [cid]
    if semester_id:
        query += " AND wp.semester_id = ?"
        params.append(int(semester_id))
    query += " ORDER BY wp.semester_id DESC, wp.week_num DESC"
    return jsonify(dicts_from_rows(g.db.execute(query, params).fetchall()))


@app.route('/api/points/trend', methods=['GET'])
def get_points_trend():
    cid = require_cohort()
    student_ids = request.args.get('student_ids', '')
    semester_id = request.args.get('semester_id', '')
    if not student_ids:
        return jsonify([])
    ids = [int(x) for x in student_ids.split(',') if x.strip()]
    ph = ','.join(['?'] * len(ids))
    query = f"""
        SELECT wp.student_id, s.name, wp.week_num, wp.score, sm.name as semester_name
        FROM weekly_points wp
        JOIN students s ON wp.student_id = s.id
        LEFT JOIN semesters sm ON wp.semester_id = sm.id
        WHERE wp.student_id IN ({ph}) AND s.cohort_id = ?
    """
    params = ids[:] + [cid]
    if semester_id:
        query += " AND wp.semester_id = ?"
        params.append(int(semester_id))
    query += " ORDER BY wp.semester_id, wp.week_num"
    return jsonify(dicts_from_rows(g.db.execute(query, params).fetchall()))


@app.route('/api/points/group_summary', methods=['GET'])
def get_group_summary():
    cid = require_cohort()
    if not cid:
        return jsonify([])
    semester_id = request.args.get('semester_id', '')
    if not semester_id:
        sid = get_active_semester_id(g.db)
        semester_id = str(sid) if sid else ''
    if not semester_id:
        return jsonify([])
    rows = g.db.execute("""
        SELECT s.group_name,
               COALESCE(SUM(wp.score), 0) as total_score,
               ROUND(COALESCE(AVG(wp.score), 0), 1) as avg_score,
               COUNT(DISTINCT s.id) as member_count
        FROM students s
        LEFT JOIN weekly_points wp ON s.id = wp.student_id AND wp.semester_id = ?
        WHERE s.cohort_id = ? AND s.is_active = 1 AND s.group_name IS NOT NULL
        GROUP BY s.group_name ORDER BY total_score DESC
    """, (int(semester_id), cid)).fetchall()
    return jsonify(dicts_from_rows(rows))


# ── 成绩 API（改用 semester_id）──────────────────────────
@app.route('/api/exams', methods=['GET'])
def get_exams():
    cid = require_cohort()
    if not cid:
        return jsonify([])
    semester_id = request.args.get('semester_id', '')
    query = "SELECT se.*, sm.name as semester_name FROM score_exams se LEFT JOIN semesters sm ON se.semester_id = sm.id WHERE se.cohort_id = ?"
    params = [cid]
    if semester_id:
        query += " AND se.semester_id = ?"
        params.append(int(semester_id))
    query += " ORDER BY se.exam_date DESC, se.id DESC"
    return jsonify(dicts_from_rows(g.db.execute(query, params).fetchall()))


@app.route('/api/exams', methods=['POST'])
def create_exam():
    cid = require_cohort()
    if not cid:
        return jsonify({'ok': False, 'error': '请先选择届次'}), 400
    data = request.json
    semester_id = data.get('semester_id') or get_active_semester_id(g.db)
    g.db.execute("""
        INSERT INTO score_exams (cohort_id, semester_id, name, exam_type, exam_date, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (cid, semester_id, data['name'], data['exam_type'], data.get('exam_date'), data.get('notes')))
    g.db.commit()
    return jsonify({'ok': True, 'id': g.db.insert_id()})


@app.route('/api/exams/<int:eid>', methods=['DELETE'])
def delete_exam(eid):
    g.db.execute("DELETE FROM score_exams WHERE id = ?", (eid,))
    g.db.commit()
    return jsonify({'ok': True})


@app.route('/api/scores', methods=['GET'])
def get_scores():
    exam_id = request.args.get('exam_id', '')
    student_id = request.args.get('student_id', '')
    query = """
        SELECT si.*, s.name, s.student_no, s.group_name, se.name as exam_name, se.exam_type
        FROM score_items si
        JOIN students s ON si.student_id = s.id
        JOIN score_exams se ON si.exam_id = se.id WHERE 1=1
    """
    params = []
    if exam_id:
        query += " AND si.exam_id = ?"
        params.append(int(exam_id))
    if student_id:
        query += " AND si.student_id = ?"
        params.append(int(student_id))
    query += " ORDER BY s.student_no, si.subject"
    return jsonify(dicts_from_rows(g.db.execute(query, params).fetchall()))


@app.route('/api/scores/ranking', methods=['GET'])
def get_score_ranking():
    exam_id = request.args.get('exam_id', '')
    if not exam_id:
        return jsonify([])
    rows = g.db.execute("""
        SELECT s.id as student_id, s.student_no, s.name, s.group_name,
               SUM(si.score) as total_score, COUNT(si.subject) as subject_count
        FROM score_items si JOIN students s ON si.student_id = s.id
        WHERE si.exam_id = ? GROUP BY s.id ORDER BY total_score DESC
    """, (int(exam_id),)).fetchall()
    result = dicts_from_rows(rows)
    for i, r in enumerate(result):
        r['rank'] = i + 1
    return jsonify(result)


@app.route('/api/scores', methods=['POST'])
def save_scores():
    data = request.json
    exam_id = data['exam_id']
    for rec in data['records']:
        if rec.get('score') is not None and rec['score'] != '':
            g.db.execute("""
                INSERT INTO score_items (exam_id, student_id, subject, score)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(exam_id, student_id, subject)
                DO UPDATE SET score = excluded.score
            """, (exam_id, rec['student_id'], rec['subject'], float(rec['score'])))
    g.db.commit()
    return jsonify({'ok': True, 'count': len(data['records'])})


@app.route('/api/scores/import_file', methods=['POST'])
def import_scores_file():
    """上传Excel文件，导入成绩到指定考试"""
    cid = require_cohort()
    if not cid:
        return jsonify({'ok': False, 'error': '请先选择届次'}), 400
    exam_id = request.form.get('exam_id', '')
    if not exam_id:
        return jsonify({'ok': False, 'error': '请先选择考试'}), 400
    try:
        exam_id = int(exam_id)
    except (ValueError, TypeError):
        return jsonify({'ok': False, 'error': '考试ID无效'}), 400
    from import_data import parse_scores_excel
    if 'file' not in request.files:
        return jsonify({'ok': False, 'error': '未上传文件'}), 400
    f = request.files['file']
    ext = f.filename.rsplit('.', 1)[-1].lower()
    tmp_path = os.path.join(os.path.dirname(__file__), 'data', '_tmp_score_import.' + ext)
    f.save(tmp_path)
    try:
        records = parse_scores_excel(tmp_path)
        count, auto_created, unmatched = 0, 0, 0
        for rec in records:
            student = g.db.execute("SELECT id FROM students WHERE name = ? AND cohort_id = ? AND is_active = 1",
                                   (rec['name'], cid)).fetchone()
            if not student:
                try:
                    g.db.execute("INSERT INTO students (cohort_id, student_no, name) VALUES (?, ?, ?)",
                                 (cid, f'AUTO-{rec["name"]}', rec['name']))
                    student = {'id': g.db.insert_id()}
                    auto_created += 1
                except Exception:
                    unmatched += 1
                    continue
            for subject, score in rec['scores'].items():
                if score is not None:
                    try:
                        g.db.execute("""
                            INSERT INTO score_items (exam_id, student_id, subject, score)
                            VALUES (?, ?, ?, ?)
                            ON CONFLICT(exam_id, student_id, subject)
                            DO UPDATE SET score = excluded.score
                        """, (exam_id, student['id'], subject, float(score)))
                        count += 1
                    except Exception:
                        pass
        g.db.commit()
        msg = f'导入 {count} 条成绩记录'
        if auto_created:
            msg += f'，自动创建 {auto_created} 名新学生'
        if unmatched:
            msg += f'，{unmatched} 名学生未匹配跳过'
        return jsonify({'ok': True, 'count': count, 'message': msg})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.route('/api/scores/trend', methods=['GET'])
def get_score_trend():
    student_id = request.args.get('student_id', '')
    subject = request.args.get('subject', '')
    if not student_id:
        return jsonify([])
    query = """
        SELECT se.name as exam_name, se.exam_date, si.subject, si.score, sm.name as semester_name
        FROM score_items si
        JOIN score_exams se ON si.exam_id = se.id
        LEFT JOIN semesters sm ON se.semester_id = sm.id
        WHERE si.student_id = ?
    """
    params = [int(student_id)]
    if subject:
        query += " AND si.subject = ?"
        params.append(subject)
    query += " ORDER BY se.semester_id, se.exam_date, se.id"
    return jsonify(dicts_from_rows(g.db.execute(query, params).fetchall()))


@app.route('/api/scores/subjects', methods=['GET'])
def get_subjects():
    cid = require_cohort()
    if not cid:
        return jsonify([])
    rows = g.db.execute("""
        SELECT DISTINCT si.subject FROM score_items si
        JOIN score_exams se ON si.exam_id = se.id
        WHERE se.cohort_id = ? ORDER BY si.subject
    """, (cid,)).fetchall()
    return jsonify([r['subject'] for r in rows])


@app.route('/api/scores/class_stats', methods=['GET'])
def get_class_stats():
    exam_id = request.args.get('exam_id', '')
    if not exam_id:
        return jsonify({})
    rows = g.db.execute("""
        SELECT subject, ROUND(AVG(score), 1) as avg_score, MAX(score) as max_score,
               MIN(score) as min_score, COUNT(*) as count,
               SUM(CASE WHEN score >= 60 THEN 1 ELSE 0 END) as pass_count
        FROM score_items WHERE exam_id = ? GROUP BY subject ORDER BY subject
    """, (int(exam_id),)).fetchall()
    return jsonify(dicts_from_rows(rows))


# ── 事件 API ───────────────────────────────────────────
@app.route('/api/events', methods=['GET'])
def get_events():
    cid = require_cohort()
    if not cid:
        return jsonify([])
    student_id = request.args.get('student_id', '')
    event_type = request.args.get('event_type', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    limit = request.args.get('limit', '100')
    query = "SELECT e.*, s.name as student_name, s.student_no FROM events e JOIN students s ON e.student_id = s.id WHERE s.cohort_id = ?"
    params = [cid]
    if student_id:
        query += " AND e.student_id = ?"
        params.append(int(student_id))
    if event_type:
        query += " AND e.event_type = ?"
        params.append(event_type)
    if date_from:
        query += " AND e.event_date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND e.event_date <= ?"
        params.append(date_to)
    query += " ORDER BY e.event_date DESC, e.id DESC LIMIT ?"
    params.append(int(limit))
    return jsonify(dicts_from_rows(g.db.execute(query, params).fetchall()))


@app.route('/api/events', methods=['POST'])
def create_event():
    data = request.json
    g.db.execute("""
        INSERT INTO events (student_id, event_type, title, description, event_date, severity, follow_up)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (data['student_id'], data['event_type'], data['title'],
          data.get('description'), data['event_date'], data.get('severity'), data.get('follow_up')))
    g.db.commit()
    return jsonify({'ok': True, 'id': g.db.insert_id()})


@app.route('/api/events/<int:eid>', methods=['PUT'])
def update_event(eid):
    data = request.json
    fields = ['event_type', 'title', 'description', 'event_date', 'severity', 'follow_up']
    sets, params = [], []
    for f in fields:
        if f in data:
            sets.append(f"{f} = ?")
            params.append(data[f])
    if not sets:
        return jsonify({'ok': False, 'error': '无更新内容'}), 400
    params.append(eid)
    g.db.execute(f"UPDATE events SET {', '.join(sets)} WHERE id = ?", params)
    g.db.commit()
    return jsonify({'ok': True})


@app.route('/api/events/<int:eid>', methods=['DELETE'])
def delete_event(eid):
    g.db.execute("DELETE FROM events WHERE id = ?", (eid,))
    g.db.commit()
    return jsonify({'ok': True})


# ── 仪表盘 API ─────────────────────────────────────────
@app.route('/api/dashboard', methods=['GET'])
def get_dashboard():
    db = g.db
    cid = require_cohort()
    result = {'total_students': 0, 'semester_name': '', 'current_week': 0,
              'weekly_avg': 0, 'top5': [], 'bottom5': [],
              'recent_events': [], 'recent_exams': []}
    if not cid:
        return jsonify(result)
    row = db.execute("SELECT COUNT(*) as cnt FROM students WHERE cohort_id = ? AND is_active = 1", (cid,)).fetchone()
    result['total_students'] = row['cnt']

    # 当前学期的最新周
    sid = get_active_semester_id(db)
    if sid:
        sem = db.execute("SELECT * FROM semesters WHERE id = ?", (sid,)).fetchone()
        result['semester_name'] = sem['name'] if sem else ''
        latest = db.execute("""
            SELECT MAX(wp.week_num) as max_week FROM weekly_points wp
            JOIN students s ON wp.student_id = s.id
            WHERE s.cohort_id = ? AND wp.semester_id = ?
        """, (cid, sid)).fetchone()
        if latest and latest['max_week']:
            result['current_week'] = latest['max_week']
            row = db.execute("""
                SELECT ROUND(AVG(wp.score), 1) as avg_score FROM weekly_points wp
                JOIN students s ON wp.student_id = s.id
                WHERE wp.semester_id = ? AND wp.week_num = ? AND s.cohort_id = ?
            """, (sid, latest['max_week'], cid)).fetchone()
            result['weekly_avg'] = row['avg_score'] or 0
            rows = db.execute("""
                SELECT s.name, SUM(wp.score) as total FROM weekly_points wp
                JOIN students s ON wp.student_id = s.id
                WHERE wp.semester_id = ? AND s.cohort_id = ? AND s.is_active = 1
                GROUP BY s.id ORDER BY total DESC LIMIT 5
            """, (sid, cid)).fetchall()
            result['top5'] = dicts_from_rows(rows)
            rows = db.execute("""
                SELECT s.name, SUM(wp.score) as total FROM weekly_points wp
                JOIN students s ON wp.student_id = s.id
                WHERE wp.semester_id = ? AND s.cohort_id = ? AND s.is_active = 1
                GROUP BY s.id ORDER BY total ASC LIMIT 5
            """, (sid, cid)).fetchall()
            result['bottom5'] = dicts_from_rows(rows)

    rows = db.execute("""
        SELECT e.*, s.name as student_name FROM events e
        JOIN students s ON e.student_id = s.id WHERE s.cohort_id = ?
        ORDER BY e.event_date DESC, e.id DESC LIMIT 5
    """, (cid,)).fetchall()
    result['recent_events'] = dicts_from_rows(rows)
    rows = db.execute("""
        SELECT se.*, COUNT(DISTINCT si.student_id) as student_count
        FROM score_exams se LEFT JOIN score_items si ON se.id = si.exam_id
        WHERE se.cohort_id = ? GROUP BY se.id ORDER BY se.exam_date DESC LIMIT 3
    """, (cid,)).fetchall()
    result['recent_exams'] = dicts_from_rows(rows)
    return jsonify(result)


# ── 导入 API ───────────────────────────────────────────
@app.route('/api/import/students', methods=['POST'])
def import_students():
    cid = require_cohort()
    if not cid:
        return jsonify({'ok': False, 'error': '请先选择届次'}), 400
    from import_data import parse_student_info
    if 'file' not in request.files:
        return jsonify({'ok': False, 'error': '未上传文件'}), 400
    f = request.files['file']
    ext = f.filename.rsplit('.', 1)[-1].lower()
    tmp_path = os.path.join(os.path.dirname(__file__), 'data', '_tmp_import.' + ext)
    f.save(tmp_path)
    try:
        students = parse_student_info(tmp_path)
        # 获取当前届次的班级号，用于过滤
        cohort = g.db.execute("SELECT class_no FROM cohorts WHERE id = ?", (cid,)).fetchone()
        target_class = cohort['class_no'] if cohort else ''
        count = 0
        skipped = 0
        auto_seq = 1000  # 自动序号起点
        used_nos = set()
        for s in students:
            # 如果学生数据有班级号，只导入当前届次对应班级的学生
            file_class = s.get('class_no', '')
            if file_class and target_class and file_class != target_class:
                skipped += 1
                continue
            # 确保 student_no 唯一
            student_no = s.get('student_no', '').strip()
            if not student_no or student_no in used_nos:
                student_no = str(auto_seq)
                auto_seq += 1
            else:
                used_nos.add(student_no)
            try:
                g.db.execute("""
                    INSERT INTO students (cohort_id, student_no, name, gender, birth_date, ethnicity, id_number, group_name, group_order,
                        address, household_type, household_loc, father, father_work, father_phone, mother, mother_work, mother_phone)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(cohort_id, student_no) DO UPDATE SET
                        name=excluded.name, gender=excluded.gender, birth_date=excluded.birth_date,
                        ethnicity=excluded.ethnicity, id_number=excluded.id_number,
                        address=excluded.address, household_type=excluded.household_type,
                        household_loc=excluded.household_loc, father=excluded.father,
                        father_work=excluded.father_work, father_phone=excluded.father_phone,
                        mother=excluded.mother, mother_work=excluded.mother_work, mother_phone=excluded.mother_phone
                """, (cid, student_no, s['name'], s.get('gender'), s.get('birth_date'),
                      s.get('ethnicity'), s.get('id_number'), s.get('group_name'), s.get('group_order'),
                      s.get('address', ''), s.get('household_type', ''), s.get('household_loc', ''),
                      s.get('father', ''), s.get('father_work', ''), s.get('father_phone', ''),
                      s.get('mother', ''), s.get('mother_work', ''), s.get('mother_phone', '')))
                count += 1
            except Exception:
                pass
        g.db.commit()
        msg = f'导入 {count} 名学生'
        if skipped:
            msg += f'（跳过其他班级 {skipped} 人）'
        return jsonify({'ok': True, 'count': count, 'message': msg})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.route('/api/import/preview', methods=['POST'])
def import_preview():
    from import_data import preview_excel
    if 'file' not in request.files:
        return jsonify({'ok': False, 'error': '未上传文件'}), 400
    f = request.files['file']
    ext = f.filename.rsplit('.', 1)[-1].lower()
    tmp_path = os.path.join(os.path.dirname(__file__), 'data', '_tmp_preview.' + ext)
    f.save(tmp_path)
    try:
        return jsonify({'ok': True, **preview_excel(tmp_path)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.route('/api/import/points', methods=['POST'])
def import_points():
    cid = require_cohort()
    if not cid:
        return jsonify({'ok': False, 'error': '请先选择届次'}), 400
    semester_id = request.form.get('semester_id') or get_active_semester_id(g.db)
    if not semester_id:
        return jsonify({'ok': False, 'error': '请先选择学期'}), 400
    from import_data import parse_points_excel
    if 'file' not in request.files:
        return jsonify({'ok': False, 'error': '未上传文件'}), 400
    f = request.files['file']
    ext = f.filename.rsplit('.', 1)[-1].lower()
    tmp_path = os.path.join(os.path.dirname(__file__), 'data', '_tmp_points.' + ext)
    f.save(tmp_path)
    try:
        records = parse_points_excel(tmp_path, '')
        count, auto_created, skipped = 0, 0, 0
        for rec in records:
            student = g.db.execute("SELECT id FROM students WHERE name = ? AND cohort_id = ?", (rec['name'], cid)).fetchone()
            if not student:
                try:
                    g.db.execute("INSERT INTO students (cohort_id, student_no, name) VALUES (?, ?, ?)",
                                 (cid, f'AUTO-{rec["name"]}', rec['name']))
                    student = {'id': g.db.insert_id()}
                    auto_created += 1
                except Exception:
                    skipped += 1
                    continue
            for week_num, score in rec['weeks'].items():
                if score is not None:
                    try:
                        g.db.execute("""
                            INSERT INTO weekly_points (student_id, week_num, semester_id, score, source)
                            VALUES (?, ?, ?, ?, 'import')
                            ON CONFLICT(student_id, week_num, semester_id)
                            DO UPDATE SET score = excluded.score, source = 'import'
                        """, (student['id'], week_num, int(semester_id), score))
                        count += 1
                    except Exception:
                        pass
        g.db.commit()
        msg = f'导入 {count} 条积分记录'
        if auto_created:
            msg += f'，自动创建 {auto_created} 名新学生'
        if skipped:
            msg += f'，{skipped} 名学生未匹配跳过'
        return jsonify({'ok': True, 'count': count, 'message': msg})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.route('/api/import/scores', methods=['POST'])
def import_scores():
    cid = require_cohort()
    if not cid:
        return jsonify({'ok': False, 'error': '请先选择届次'}), 400
    semester_id = request.form.get('semester_id') or get_active_semester_id(g.db)
    from import_data import parse_scores_excel
    if 'file' not in request.files:
        return jsonify({'ok': False, 'error': '未上传文件'}), 400
    f = request.files['file']
    exam_name = request.form.get('exam_name', '导入考试')
    exam_type = request.form.get('exam_type', '其他')
    ext = f.filename.rsplit('.', 1)[-1].lower()
    tmp_path = os.path.join(os.path.dirname(__file__), 'data', '_tmp_scores.' + ext)
    f.save(tmp_path)
    try:
        records = parse_scores_excel(tmp_path)
        g.db.execute("INSERT INTO score_exams (cohort_id, semester_id, name, exam_type) VALUES (?, ?, ?, ?)",
                     (cid, semester_id, exam_name, exam_type))
        exam_id = g.db.insert_id()
        count, auto_created = 0, 0
        for rec in records:
            student = g.db.execute("SELECT id FROM students WHERE name = ? AND cohort_id = ?", (rec['name'], cid)).fetchone()
            if not student:
                try:
                    g.db.execute("INSERT INTO students (cohort_id, student_no, name) VALUES (?, ?, ?)",
                                 (cid, f'AUTO-{rec["name"]}', rec['name']))
                    student = {'id': g.db.insert_id()}
                    auto_created += 1
                except Exception:
                    continue
            for subject, score in rec['scores'].items():
                if score is not None:
                    try:
                        g.db.execute("INSERT INTO score_items (exam_id, student_id, subject, score) VALUES (?, ?, ?, ?)",
                                     (exam_id, student['id'], subject, float(score)))
                        count += 1
                    except Exception:
                        pass
        g.db.commit()
        msg = f'导入 {count} 条成绩记录'
        if auto_created:
            msg += f'，自动创建 {auto_created} 名新学生'
        return jsonify({'ok': True, 'exam_id': exam_id, 'count': count, 'message': msg})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# ── AI对话 API ─────────────────────────────────────────
@app.route('/api/chat', methods=['POST'])
def chat():
    """AI对话接口
    策略：
    - 已配置AI（有API Key）→ 查询类问题直接走大模型，操作类（加分/记录事件/添加学生）走规则引擎
    - 未配置AI → 全部走规则引擎
    """
    cid = require_cohort()
    if not cid:
        return jsonify({'reply': '请先在设置页面创建一个届次', 'actions': []})
    data = request.json
    message = data.get('message', '').strip()
    messages = data.get('messages', [])
    if not message:
        return jsonify({'reply': '请输入内容', 'actions': []})
    sid = get_active_semester_id(g.db)

    from chat import process_message
    from ai_chat import get_ai_settings, build_rich_system_prompt, call_ai_api_with_history

    ai_settings = get_ai_settings(g.db)
    has_ai = bool(ai_settings['provider'] and ai_settings['api_key'])

    # 判断是否是操作类指令（加分、记录事件、添加学生）
    is_operation = any(kw in message for kw in [
        '加', '减', '加分', '减分', '记录', '添加学生', '添加同学',
        '录入', '新增', '加入',
    ]) and any(kw in message for kw in [
        '分', '违纪', '处分', '表扬', '谈话', '家访', '学生', '同学',
    ])

    if has_ai and not is_operation:
        # ── AI优先：已配置AI且非操作类指令，直接调用大模型 ──
        system_prompt = build_rich_system_prompt(g.db, cid, sid)
        ai_result = call_ai_api_with_history(ai_settings, system_prompt, message, messages)
        if ai_result and 'reply' in ai_result:
            # 解析并执行AI回复中的操作指令
            reply, exec_log = _execute_ai_actions(g.db, ai_result['reply'], cid, sid)
            if exec_log:
                reply += '\n\n' + '\n'.join(exec_log)
            return jsonify({'reply': reply, 'actions': []})
        # AI调用失败，回退规则引擎
        rule_result = process_message(g.db, message, cid, sid)
        return jsonify({'reply': rule_result.get('reply', '查询出错，请稍后再试'), 'actions': []})

    # ── 规则引擎：AI未配置 或 操作类指令 ──
    rule_result = process_message(g.db, message, cid, sid)

    # 规则引擎不认识，且有AI兜底（如添加好友等操作类被误判）
    if rule_result.get('_intent') == 'unknown' and has_ai:
        system_prompt = build_rich_system_prompt(g.db, cid, sid)
        ai_result = call_ai_api_with_history(ai_settings, system_prompt, message, messages)
        if ai_result and 'reply' in ai_result:
            return jsonify(ai_result)

    return jsonify(rule_result)


@app.route('/api/chat/upload', methods=['POST'])
def chat_upload():
    """AI对话文件上传接口：接收Excel文件 → 解析 → AI分析 → 自动导入"""
    cid = require_cohort()
    if not cid:
        return jsonify({'ok': False, 'error': '请先选择届次', 'reply': '请先在设置页面创建一个届次'})
    sid = get_active_semester_id(g.db)

    if 'file' not in request.files:
        return jsonify({'ok': False, 'error': '未上传文件', 'reply': '请选择要上传的文件'})

    file = request.files['file']
    if not file.filename:
        return jsonify({'ok': False, 'error': '文件名为空', 'reply': '请选择有效的文件'})

    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in ('xlsx', 'xls'):
        return jsonify({'ok': False, 'error': '仅支持xlsx/xls格式', 'reply': '目前仅支持上传 Excel 文件（.xlsx / .xls）'})

    # 保存临时文件
    tmp_name = f'chat_upload_{uuid.uuid4().hex[:8]}.{ext}'
    tmp_path = os.path.join(app.root_path, 'uploads', tmp_name)
    file.save(tmp_path)

    try:
        # 解析 Excel
        import openpyxl
        wb = openpyxl.load_workbook(tmp_path, read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append([c if c is not None else '' for c in row])
        wb.close()

        if not rows or len(rows) < 2:
            os.remove(tmp_path)
            return jsonify({'ok': False, 'error': '文件为空', 'reply': '文件似乎没有数据，请检查内容'})

        header = [str(h).strip() for h in rows[0]]
        data_rows = rows[1:]
        total_rows = len([r for r in data_rows if any(str(c).strip() for c in r)])

        # 自动检测数据类型并尝试导入
        import_result = _try_auto_import(g.db, header, data_rows, cid, sid, file.filename)

        # 构建数据摘要给AI — 包含完整的表数据
        summary_parts = [f'文件名称：{file.filename}', f'列头：{" | ".join(header)}', f'数据行数：{total_rows}', '']

        # 格式化为表格，让AI能看清每一行
        summary_parts.append('| ' + ' | '.join(header) + ' |')
        summary_parts.append('|' + '|'.join('---' for _ in header) + '|')
        show_limit = max(30, total_rows)  # 展示全部数据让AI能完整处理
        for r in data_rows[:show_limit]:
            vals = [str(c)[:40] if c != '' else '-' for c in r[:len(header)]]
            summary_parts.append('| ' + ' | '.join(vals) + ' |')

        summary_text = '\n'.join(summary_parts)

        # AI分析
        from ai_chat import get_ai_settings, build_rich_system_prompt, call_ai_api_with_history
        ai_settings = get_ai_settings(g.db)

        user_msg = request.form.get('message', '').strip()
        if not user_msg:
            user_msg = f'我上传了一个Excel文件"{file.filename}"，里面是{total_rows}行数据，列头是：{"、".join(header)}。请查看文件内容并告诉我数据情况，如果是学号更新、成绩等，请根据需要执行操作。'

        if ai_settings['provider'] and ai_settings['api_key']:
            system_prompt = build_rich_system_prompt(g.db, cid, sid)
            import_note = ''
            if import_result:
                import_note = f'\n\n【自动导入结果】{import_result["message"]}'
                if import_result.get('type') == 'student_no' and '未找到' in import_result['message']:
                    import_note += '\n请注意：只有上面"未找到"的学生才需要你处理，已更新的那些不用管。'
            system_prompt += f'\n\n## 用户上传的文件数据（完整表）\n{summary_text}{import_note}\n\n请根据这份文件数据回答用户。你可以使用 ###EXECUTE:...### 命令来根据文件数据修改数据库。\n\n**批量操作提醒：如果需要对多个学生执行相同操作（如批量更新学号），请使用 batch_update_students 命令，一条命令搞定所有学生，不要逐个生成独立命令。**'
            ai_result = call_ai_api_with_history(ai_settings, system_prompt, user_msg, [])
            if ai_result and 'reply' in ai_result:
                reply = ai_result['reply']
                # 解析并执行AI回复中的操作指令
                reply, exec_log = _execute_ai_actions(g.db, reply, cid, sid)
                if exec_log:
                    reply += '\n\n' + '\n'.join(exec_log)
            else:
                reply = f'已解析文件：{file.filename}\n\n共 {total_rows} 条数据\n列头：{"、".join(header)}'
                if import_result:
                    reply += f'\n\n{import_result["message"]}'
        else:
            reply = f'📎 已收到文件：**{file.filename}**\n\n共 **{total_rows}** 条数据\n列头：{"、".join(header)}'
            if import_result:
                reply += f'\n\n{import_result["message"]}'

        os.remove(tmp_path)
        return jsonify({'ok': True, 'reply': reply, 'actions': []})

    except Exception as e:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        return jsonify({'ok': False, 'error': str(e), 'reply': f'文件解析出错：{str(e)[:100]}'})


def _try_auto_import(db, header, data_rows, cohort_id, semester_id, filename):
    """自动检测文件类型并尝试导入数据库"""
    # 检测是否为成绩表（含"姓名" + 数字科目列）
    name_col = None
    subject_cols = {}  # col_index → subject_name
    for i, h in enumerate(header):
        if '姓名' in h or '名字' in h or '学生' in h:
            name_col = i
        elif h and h not in ('序号', '学号', '排名', '名次', '总分', '班次', '进退步'):
            # 检查是否数值列（科目）
            is_num = True
            for r in data_rows[:5]:
                if i < len(r):
                    val = r[i]
                    if val != '' and val is not None:
                        try:
                            float(val)
                        except (ValueError, TypeError):
                            if not isinstance(val, (int, float)):
                                is_num = False
                                break
            if is_num:
                subject_cols[i] = h

    # 检测学生信息更新表（含"姓名"+"学号"列，没有科目列）
    student_no_col = None
    for i, h in enumerate(header):
        if '学号' == h.strip() or '学生学号' in h:
            student_no_col = i

    if name_col is not None and student_no_col is not None and len(subject_cols) == 0 and len(data_rows) >= 1:
        # 视为学号更新表
        updated = 0
        not_found = []
        for row in data_rows:
            if name_col >= len(row) or student_no_col >= len(row):
                continue
            sname = str(row[name_col]).strip()
            sno = str(row[student_no_col]).strip()
            if not sname or not sno:
                continue
            student = db.execute(
                "SELECT id, student_no FROM students WHERE cohort_id = ? AND name = ? AND is_active = 1",
                (cohort_id, sname)
            ).fetchone()
            if not student:
                not_found.append(sname)
                continue
            # 更新学号
            db.execute("UPDATE students SET student_no = ? WHERE id = ?", (sno, student['id']))
            updated += 1
        db.commit()
        msg = f'✅ 已更新 **{updated}** 名学生的学号'
        if not_found:
            msg += f'\n⚠️ 未找到以下学生：{"、".join(not_found[:10])}'
            if len(not_found) > 10:
                msg += f'等{len(not_found)}人'
        return {'ok': True, 'message': msg, 'type': 'student_no'}

    # 如果识别为成绩表（有姓名列+至少1个科目列+数据>1行）
    if name_col is not None and len(subject_cols) >= 1 and len(data_rows) >= 1:
        # 创建考试
        exam_name = filename.rsplit('.', 1)[0].strip()
        if not exam_name:
            exam_name = '上传成绩'
        from datetime import date
        today = date.today().isoformat()

        db.execute("""INSERT INTO score_exams (cohort_id, semester_id, name, exam_type, exam_date)
                      VALUES (?, ?, ?, ?, ?)""",
                   (cohort_id, semester_id, exam_name, '考试', today))

        exam_id = db.insert_id()
        imported = 0
        skipped = 0

        for row in data_rows:
            if name_col >= len(row):
                continue
            sname = str(row[name_col]).strip()
            if not sname:
                continue
            # 查找学生
            student = db.execute(
                "SELECT id FROM students WHERE cohort_id = ? AND name = ? AND is_active = 1",
                (cohort_id, sname)
            ).fetchone()
            if not student:
                # 模糊匹配
                student = db.execute(
                    "SELECT id FROM students WHERE cohort_id = ? AND name LIKE ? AND is_active = 1 LIMIT 1",
                    (cohort_id, f'%{sname}%')
                ).fetchone()
            if not student:
                skipped += 1
                continue

            for col_idx, subj in subject_cols.items():
                if col_idx < len(row):
                    val = row[col_idx]
                    if val != '' and val is not None:
                        try:
                            score_val = float(val)
                            db.execute("""INSERT OR REPLACE INTO score_items
                                          (exam_id, student_id, subject, score)
                                          VALUES (?, ?, ?, ?)""",
                                       (exam_id, student['id'], subj, score_val))
                        except (ValueError, TypeError):
                            pass
            imported += 1

        db.commit()
        subj_list = '、'.join(subject_cols.values())
        msg = f'✅ 已自动识别为成绩表，创建考试「{exam_name}」，导入{imported}人{subj_list}成绩'
        if skipped:
            msg += f'，{skipped}人未找到对应学生已跳过'
        return {'ok': True, 'message': msg, 'type': 'scores', 'exam_id': exam_id}

    return None


def _execute_ai_actions(db, reply, cohort_id, semester_id):
    """解析AI回复中的 ###EXECUTE...### 指令，执行并返回日志"""
    import re, json
    log = []

    # 允许的字段白名单
    allowed = {'name','gender','birth_date','ethnicity','id_number','group_name',
               'address','household_type','household_loc',
               'father','father_work','father_phone',
               'mother','mother_work','mother_phone','student_no'}

    pattern = r'###EXECUTE:\s*(\{.*?\})\s*###'
    matches = re.findall(pattern, reply, re.DOTALL)

    for raw in matches:
        try:
            cmd = json.loads(raw.strip())
            action = cmd.get('action', '')
            params = cmd.get('params', {})

            if action == 'update_student':
                name = params.get('name', '')
                field = params.get('field', '')
                value = params.get('value', '')
                if not name or not field:
                    log.append(f'❌ 更新学生失败：缺少姓名或字段')
                    continue
                # 查找学生
                student = db.execute(
                    "SELECT id, name FROM students WHERE cohort_id = ? AND name LIKE ? AND is_active = 1",
                    (cohort_id, f'%{name}%')
                ).fetchone()
                if not student:
                    log.append(f'❌ 未找到学生「{name}」')
                    continue
                # 验证字段名（白名单）
                if field not in allowed:
                    log.append(f'❌ 不允许的字段「{field}」')
                    continue
                db.execute(f"UPDATE students SET {field} = ? WHERE id = ?", (value, student['id']))
                db.commit()
                log.append(f'✅ 已更新 {student["name"]} 的{field}为「{value}」')

            elif action == 'add_event':
                name = params.get('name', '')
                etype = params.get('event_type', '违纪')
                title = params.get('title', '')
                if not name:
                    log.append(f'❌ 记录事件失败：缺少学生姓名')
                    continue
                student = db.execute(
                    "SELECT id, name FROM students WHERE cohort_id = ? AND name LIKE ? AND is_active = 1",
                    (cohort_id, f'%{name}%')
                ).fetchone()
                if not student:
                    log.append(f'❌ 未找到学生「{name}」')
                    continue
                today = date.today().isoformat()
                db.execute("INSERT INTO events (student_id, event_type, title, event_date) VALUES (?, ?, ?, ?)",
                           (student['id'], etype, title or etype, today))
                db.commit()
                log.append(f'✅ 已记录 {student["name"]} · {etype} · {title or etype}')

            elif action == 'add_points':
                name = params.get('name', '')
                score = params.get('score', 0)
                if not name:
                    log.append(f'❌ 录入积分失败：缺少学生姓名')
                    continue
                if not semester_id:
                    log.append(f'❌ 录入积分失败：未选择学期')
                    continue
                student = db.execute(
                    "SELECT id, name FROM students WHERE cohort_id = ? AND name LIKE ? AND is_active = 1",
                    (cohort_id, f'%{name}%')
                ).fetchone()
                if not student:
                    log.append(f'❌ 未找到学生「{name}」')
                    continue
                latest = db.execute(
                    "SELECT MAX(week_num) as w FROM weekly_points WHERE student_id = ? AND semester_id = ?",
                    (student['id'], semester_id)
                ).fetchone()
                week = latest['w'] if latest and latest['w'] else 1
                existing = db.execute(
                    "SELECT id, score FROM weekly_points WHERE student_id = ? AND week_num = ? AND semester_id = ?",
                    (student['id'], week, semester_id)
                ).fetchone()
                if existing:
                    new_score = existing['score'] + score
                    db.execute("UPDATE weekly_points SET score = ? WHERE id = ?", (new_score, existing['id']))
                else:
                    db.execute("INSERT INTO weekly_points (student_id, week_num, semester_id, score, source) VALUES (?, ?, ?, ?, 'ai')",
                               (student['id'], week, semester_id, score))
                db.commit()
                log.append(f'✅ 已给 {student["name"]} 第{week}周 {"+" if score >= 0 else ""}{score}分')

            elif action == 'batch_update_students':
                students = params.get('students', [])
                if not students:
                    log.append(f'❌ 批量更新失败：students 列表为空')
                    continue
                field = params.get('field', 'student_no')
                if field not in allowed:
                    log.append(f'❌ 批量更新失败：不允许的字段「{field}」')
                    continue
                updated = 0
                not_found = []
                for item in students:
                    name = item.get('name', '')
                    value = item.get('value', '')
                    if not name:
                        continue
                    student = db.execute(
                        "SELECT id, name FROM students WHERE cohort_id = ? AND name LIKE ? AND is_active = 1",
                        (cohort_id, f'%{name}%')
                    ).fetchone()
                    if not student:
                        not_found.append(name)
                        continue
                    db.execute(f"UPDATE students SET {field} = ? WHERE id = ?", (value, student['id']))
                    updated += 1
                db.commit()
                log.append(f'✅ 批量更新了 {updated} 名学生的{field}（共 {len(students)} 条）')
                if not_found:
                    log.append(f'⚠️ 未找到的学生（{len(not_found)}人）：{"、".join(not_found[:10])}{"等" if len(not_found) > 10 else ""}')

            else:
                log.append(f'❌ 不支持的操作类型「{action}」')

        except json.JSONDecodeError:
            log.append(f'❌ 命令格式错误：{raw[:50]}...')
        except Exception as e:
            log.append(f'❌ 执行出错：{str(e)[:80]}')

    # 从回复中移除 EXECUTE 指令
    cleaned = re.sub(r'\s*###EXECUTE:.*?###\s*', '', reply, flags=re.DOTALL).strip()

    return cleaned, log


# ── 启动 ───────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
