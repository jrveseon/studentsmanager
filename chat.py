"""AI对话模块 - 基于规则的意图识别和数据操作"""
import re
import json
from datetime import datetime


def process_message(db, message, cohort_id, semester_id):
    """处理用户消息，返回回复"""
    msg = message.strip()
    if not msg:
        return {'reply': '请输入内容', 'actions': []}

    # 意图匹配
    intent = classify_intent(msg)

    if intent['type'] == 'query_students':
        result = handle_query_students(db, cohort_id, msg)
    elif intent['type'] == 'query_gender':
        result = handle_query_gender(db, cohort_id)
    elif intent['type'] == 'query_groups':
        result = handle_query_groups(db, cohort_id, msg)
    elif intent['type'] == 'query_points':
        result = handle_query_points(db, cohort_id, semester_id, msg)
    elif intent['type'] == 'query_points_bottom':
        result = handle_query_points_bottom(db, cohort_id, msg)
    elif intent['type'] == 'query_points_group':
        result = handle_query_points_group(db, cohort_id, semester_id)
    elif intent['type'] == 'query_points_week':
        result = handle_query_points_week(db, cohort_id, semester_id, msg)
    elif intent['type'] == 'query_scores':
        result = handle_query_scores(db, cohort_id, semester_id, msg)
    elif intent['type'] == 'query_scores_exam_detail':
        result = handle_query_scores_exam_detail(db, cohort_id, msg)
    elif intent['type'] == 'query_events':
        result = handle_query_events(db, cohort_id, msg)
    elif intent['type'] == 'query_events_type':
        result = handle_query_events_type(db, cohort_id, msg)
    elif intent['type'] == 'query_events_most':
        result = handle_query_events_most(db, cohort_id)
    elif intent['type'] == 'add_student':
        result = handle_add_student(db, cohort_id, msg)
    elif intent['type'] == 'add_event':
        result = handle_add_event(db, cohort_id, msg)
    elif intent['type'] == 'add_points':
        result = handle_add_points(db, cohort_id, semester_id, msg)
    elif intent['type'] == 'help':
        result = handle_help()
    else:
        result = handle_unknown()
    result['_intent'] = intent['type']
    return result


def classify_intent(msg):
    """分类用户意图（优先级：操作 > 查询）"""
    # ── 操作类 ──
    # 添加学生
    if re.search(r'(添加|新增|加入|录入).{0,5}(学生|同学)', msg):
        return {'type': 'add_student'}

    # 记录事件: 记录XX违纪 / 记录XX违纪：xxx
    if re.search(r'(记录|记下|发生)\s*[\u4e00-\u9fff]{2,3}(违纪|处分|表扬|谈话|家访|事件)', msg):
        return {'type': 'add_event'}

    # 录入积分：给XX加N分 / XX积分+N / 录入XX积分
    if re.search(r'(给|录入|添加)\s*[\u4e00-\u9fff]{2,3}.*(加|减|\+|-)\d+\s*分', msg):
        return {'type': 'add_points'}
    if re.search(r'[\u4e00-\u9fff]{2,3}积分\s*[\+\-]\s*\d+', msg):
        return {'type': 'add_points'}

    # ── 学生查询 ──
    # 男女分布（需在 general "多少人" 之前匹配）
    if any(kw in msg for kw in ['男生多少', '女生多少', '男女', '男生人数', '女生人数', '几个男生', '几个女生', '男女比例']):
        return {'type': 'query_gender'}
    if '性别' in msg and any(kw in msg for kw in ['统计', '分布', '比例', '多少', '人数']):
        return {'type': 'query_gender'}

    if any(kw in msg for kw in ['有哪些学生', '学生名单', '学生列表', '多少学生', '总人数', '班级人数']):
        return {'type': 'query_students'}
    # "多少人" 排除 "男生/女生多少人"
    if '多少人' in msg and not any(kw in msg for kw in ['男生', '女生']):
        return {'type': 'query_students'}
    if re.search(r'(谁是|查.{0,5}(学生|同学)|查\s*[\u4e00-\u9fff]{2,4}|找.{0,5}(学生|同学)|学生.{0,3}信息)', msg):
        return {'type': 'query_students'}

    # ── 小组查询 ──
    if '各小组' in msg and '积分' in msg:
        return {'type': 'query_points_group'}
    if any(kw in msg for kw in ['各小组', '小组人数', '分组情况', '小组名单']):
        return {'type': 'query_groups'}
    if re.search(r'[\u4e00-\u9fff]{1,3}组\s*(有|的|哪些|谁|成员)', msg):
        return {'type': 'query_groups'}
    if re.search(r'(有|哪些)小组', msg):
        return {'type': 'query_groups'}

    # ── 积分查询 ──
    if any(kw in msg for kw in ['积分排名', '排名', '谁最高', 'top', 'TOP', '积分汇总', '多少分']):
        return {'type': 'query_points'}
    if any(kw in msg for kw in ['积分最低', '最后一名', '积分倒数', '垫底', '最后几名']):
        return {'type': 'query_points_bottom'}
    if any(kw in msg for kw in ['小组积分', '小组平均', '各组积分', '哪个组']):
        return {'type': 'query_points_group'}
    if re.search(r'第\s*\d+\s*周', msg) and '积分' in msg:
        return {'type': 'query_points_week'}
    # XX的积分 / XX积分
    if re.search(r'[\u4e00-\u9fff]{2,3}(的)?积分', msg):
        return {'type': 'query_points'}
    if '积分' in msg and not re.search(r'(录入|加|减)', msg):
        return {'type': 'query_points'}

    # ── 成绩查询 ──
    if any(kw in msg for kw in ['均分', '及格率', '平均分', '最高分', '最低分']):
        return {'type': 'query_scores_exam_detail'}
    if any(kw in msg for kw in ['成绩', '考试', '最近考试']):
        return {'type': 'query_scores'}

    # ── 事件查询 ──
    if any(kw in msg for kw in ['最近事件', '事件记录', '事件列表']):
        return {'type': 'query_events'}
    # 查特定学生事件
    if re.search(r'[\u4e00-\u9fff]{2,3}(的|.{0,1})(事件|记录|违纪|处分|表扬)', msg) and not re.search(r'(记录|记下|发生)', msg):
        return {'type': 'query_events'}
    # 按类型查事件
    if any(kw in msg for kw in ['最近的违纪', '最近的表扬', '最近的处分', '最近违纪', '最近表扬', '最近处分']):
        return {'type': 'query_events_type'}
    if any(kw in msg for kw in ['谁经常', '违纪最多', '表扬最多', '谁违纪', '哪个人违纪']):
        return {'type': 'query_events_most'}
    if re.search(r'(违纪|表扬|处分)的(学生|同学|名单)', msg):
        return {'type': 'query_events_type'}

    # 帮助
    if any(kw in msg for kw in ['帮助', '怎么用', '能做什么', '功能', 'help', '你会什么']):
        return {'type': 'help'}

    return {'type': 'unknown'}


# ── 学生查询 ───────────────────────────────────────

def handle_query_students(db, cohort_id, msg):
    """查询学生信息"""
    # 查具体学生
    name = None
    if '查' in msg or '找' in msg or '谁是' in msg:
        # 提取"查/找"后面的名字
        m = re.search(r'(?:查|找|谁是)\s*([\u4e00-\u9fff]{2,4})', msg)
        if m:
            name = m.group(1)
    if name:
        row = db.execute("SELECT * FROM students WHERE cohort_id = ? AND name LIKE ? AND is_active = 1",
                         (cohort_id, f'%{name}%')).fetchone()
        if row:
            s = dict(row)
            return {
                'reply': f'**{s["name"]}** 的信息：\n- 学号：{s["student_no"]}\n- 性别：{s.get("gender", "-")}\n- 小组：{s.get("group_name", "-")}组\n- 出生日期：{s.get("birth_date", "-")}\n- 家长电话：{s.get("parent_phone", "-")}',
                'actions': [{'type': 'highlight_student', 'id': s['id'], 'name': s['name']}]
            }
        return {'reply': f'没有找到名为「{name}」的学生', 'actions': []}

    # 查询总数和列表
    rows = db.execute("""
        SELECT name, student_no, group_name FROM students
        WHERE cohort_id = ? AND is_active = 1
        ORDER BY CAST(student_no AS INTEGER), student_no
    """, (cohort_id,)).fetchall()
    if not rows:
        return {'reply': '当前还没有学生数据，请先到「数据导入」页面导入学生信息。', 'actions': []}

    names = [r['name'] for r in rows]
    groups = {}
    for r in rows:
        g = r['group_name'] or '未分组'
        groups.setdefault(g, []).append(r['name'])

    reply = f'当前共有 **{len(names)}** 名学生：\n\n'
    for g, members in sorted(groups.items()):
        reply += f'**{g}组**（{len(members)}人）：{"、".join(members)}\n'

    return {'reply': reply, 'actions': []}


def handle_query_gender(db, cohort_id):
    """查询男女分布"""
    male = db.execute("SELECT COUNT(*) as cnt FROM students WHERE cohort_id = ? AND is_active = 1 AND gender = '男'",
                      (cohort_id,)).fetchone()
    female = db.execute("SELECT COUNT(*) as cnt FROM students WHERE cohort_id = ? AND is_active = 1 AND gender = '女'",
                        (cohort_id,)).fetchone()
    total = db.execute("SELECT COUNT(*) as cnt FROM students WHERE cohort_id = ? AND is_active = 1",
                       (cohort_id,)).fetchone()
    m = male['cnt'] if male else 0
    f = female['cnt'] if female else 0
    t = total['cnt'] or 1
    reply = f'**男女分布：**\n- 👦 男生：**{m}**人（{m*100//t}%）\n- 👧 女生：**{f}**人（{f*100//t}%）\n- 总计：{t}人'
    return {'reply': reply, 'actions': []}


def handle_query_groups(db, cohort_id, msg):
    """查询小组信息"""
    # 查某个特定小组
    group_match = re.search(r'([\u4e00-\u9fff]{1,3})组', msg)
    if group_match:
        gname = group_match.group(1) + '组'
        # 排除 "各小组"、"所有组" 这类词组
        if gname in ('各小组', '所有组', '什么组', '哪个组'):
            return _show_all_groups(db, cohort_id)
        students = db.execute(
            "SELECT name, student_no FROM students WHERE cohort_id = ? AND is_active = 1 AND group_name = ? ORDER BY CAST(student_no AS INTEGER)",
            (cohort_id, gname)
        ).fetchall()
        if students:
            return {'reply': f'**{gname}**（{len(students)}人）：{"、".join(s["name"] for s in students)}', 'actions': []}
        # 没找到 → 显示所有组
        return _show_all_groups(db, cohort_id)

    return _show_all_groups(db, cohort_id)


def _show_all_groups(db, cohort_id):
    """显示各小组人数总览"""
    rows = db.execute("""
        SELECT CASE WHEN group_name IS NULL OR group_name = '' THEN '未分组' ELSE group_name END as gname,
               COUNT(*) as cnt
        FROM students WHERE cohort_id = ? AND is_active = 1
        GROUP BY gname ORDER BY gname
    """, (cohort_id,)).fetchall()
    if not rows:
        return {'reply': '暂无学生数据', 'actions': []}
    reply = '**各小组人数：**\n'
    for r in rows:
        reply += f'- {r["gname"]}：{r["cnt"]}人\n'
    return {'reply': reply, 'actions': []}


# ── 积分查询 ───────────────────────────────────────

def handle_query_points(db, cohort_id, semester_id, msg):
    """查询积分信息"""
    # 查具体学生的积分 — 匹配姓名（排除"的""了"等助词）
    SKIP_WORDS = {'积分', '排名', '班级', '分数', '成绩', '名次', '总分', '谁最', 'TOP', '最高', '最低'}
    name_match = re.search(r'([\u4e00-\u9fff]{2,3})(的)?(积分|排名|多少分)', msg)
    if name_match:
        name = name_match.group(1)
        if name not in SKIP_WORDS:
            # 验证是否真的是学生名字
            row = db.execute("SELECT id, name FROM students WHERE cohort_id = ? AND name = ? AND is_active = 1",
                             (cohort_id, name)).fetchone()
            if not row:
                row = db.execute("SELECT id, name FROM students WHERE cohort_id = ? AND name LIKE ? AND is_active = 1",
                                 (cohort_id, f'%{name}%')).fetchone()
            if row:
                sid = row['id']
                # 入学以来总分
                total = db.execute("SELECT COALESCE(SUM(score), 0) as total FROM weekly_points WHERE student_id = ?",
                                   (sid,)).fetchone()
                # 当前学期总分
                sem_total = db.execute("SELECT COALESCE(SUM(score), 0) as total FROM weekly_points WHERE student_id = ? AND semester_id = ?",
                                       (sid, semester_id)).fetchone() if semester_id else None
                # 各周明细
                weekly = db.execute(
                    "SELECT week_num, score FROM weekly_points WHERE student_id = ? AND semester_id = ? ORDER BY week_num",
                    (sid, semester_id)).fetchall() if semester_id else []
                reply = f'**{row["name"]}** 的积分情况：\n- 入学以来总分：{total["total"]}\n'
                if sem_total:
                    reply += f'- 当前学期总分：{sem_total["total"]}\n'
                if weekly:
                    detail = '、'.join(f'第{r["week_num"]}周 {r["score"]}' for r in weekly[-8:])
                    reply += f'- 各周明细：{detail}\n'
                return {'reply': reply, 'actions': []}
            return {'reply': f'没有找到名为「{name}」的学生', 'actions': []}

    # 查排名
    if any(kw in msg for kw in ['排名', 'top', 'TOP', '谁最高', '谁最']):
        rows = db.execute("""
            SELECT s.name, COALESCE(SUM(wp.score), 0) as total
            FROM weekly_points wp JOIN students s ON wp.student_id = s.id
            WHERE s.cohort_id = ? AND s.is_active = 1
            GROUP BY s.id ORDER BY total DESC LIMIT 10
        """, (cohort_id,)).fetchall()
        if not rows:
            return {'reply': '暂无积分数据', 'actions': []}
        reply = '**积分排名 Top 10：**\n'
        for i, r in enumerate(rows):
            reply += f'{i+1}. {r["name"]} — {r["total"]}分\n'
        return {'reply': reply, 'actions': []}

    # 默认：概览
    total = db.execute("SELECT COUNT(*) as cnt FROM weekly_points wp JOIN students s ON wp.student_id = s.id WHERE s.cohort_id = ?",
                       (cohort_id,)).fetchone()
    return {'reply': f'当前共有 **{total["cnt"]}** 条积分记录。你可以问我：\n- 「XX同学积分多少」\n- 「积分排名」\n- 「谁的积分最高」'
                     '\n- 「谁积分最低」\n- 「各小组平均积分」\n- 「第3周积分排名」', 'actions': []}


def handle_query_points_bottom(db, cohort_id, msg):
    """查询积分最低的N名学生"""
    n = 5
    num_match = re.search(r'(\d+)', msg)
    if num_match:
        n = min(int(num_match.group(1)), 30)
    rows = db.execute("""
        SELECT s.name, COALESCE(SUM(wp.score), 0) as total
        FROM weekly_points wp JOIN students s ON wp.student_id = s.id
        WHERE s.cohort_id = ? AND s.is_active = 1
        GROUP BY s.id ORDER BY total ASC LIMIT ?
    """, (cohort_id, n)).fetchall()
    if not rows:
        return {'reply': '暂无积分数据', 'actions': []}
    # 看看每个学生有几周数据，排除0条数据的
    rows_with_points = []
    for r in rows:
        cnt = db.execute("SELECT COUNT(*) as c FROM weekly_points wp JOIN students s ON wp.student_id = s.id WHERE s.name = ? AND s.cohort_id = ?",
                         (r['name'], cohort_id)).fetchone()
        if cnt and cnt['c'] > 0:
            rows_with_points.append(r)
    if not rows_with_points:
        return {'reply': '暂无积分数据', 'actions': []}
    reply = f'**积分最低 {len(rows_with_points)} 名：**\n'
    for i, r in enumerate(rows_with_points):
        reply += f'{i+1}. {r["name"]} — {r["total"]}分\n'
    return {'reply': reply, 'actions': []}


def handle_query_points_group(db, cohort_id, semester_id):
    """查询各小组平均积分"""
    if not semester_id:
        # 无学期限制
        rows = db.execute("""
            SELECT CASE WHEN s.group_name IS NULL OR s.group_name = '' THEN '未分组' ELSE s.group_name END as gname,
                   COUNT(DISTINCT s.id) as cnt,
                   COALESCE(SUM(wp.score), 0) as total
            FROM students s LEFT JOIN weekly_points wp ON wp.student_id = s.id
            WHERE s.cohort_id = ? AND s.is_active = 1
            GROUP BY gname ORDER BY total DESC
        """, (cohort_id,)).fetchall()
    else:
        rows = db.execute("""
            SELECT CASE WHEN s.group_name IS NULL OR s.group_name = '' THEN '未分组' ELSE s.group_name END as gname,
                   COUNT(DISTINCT s.id) as cnt,
                   COALESCE(SUM(wp.score), 0) as total
            FROM students s LEFT JOIN weekly_points wp ON wp.student_id = s.id AND wp.semester_id = ?
            WHERE s.cohort_id = ? AND s.is_active = 1
            GROUP BY gname ORDER BY total DESC
        """, (semester_id, cohort_id)).fetchall()
    if not rows:
        return {'reply': '暂无积分数据', 'actions': []}
    reply = '**各小组积分总览：**\n'
    for r in rows:
        avg = r['total'] / r['cnt'] if r['cnt'] > 0 else 0
        reply += f'- {r["gname"]}：共{r["cnt"]}人，总分{r["total"]}（人均{avg:.1f}分）\n'
    return {'reply': reply, 'actions': []}


def handle_query_points_week(db, cohort_id, semester_id, msg):
    """按周查询积分排名"""
    week_match = re.search(r'第?\s*(\d+)\s*周', msg)
    if not week_match:
        return {'reply': '请说明周次，例如「第3周积分排名」', 'actions': []}
    week = int(week_match.group(1))
    rows = db.execute("""
        SELECT s.name, wp.score
        FROM weekly_points wp JOIN students s ON wp.student_id = s.id
        WHERE s.cohort_id = ? AND s.is_active = 1 AND wp.week_num = ?
        ORDER BY wp.score DESC LIMIT 10
    """, (cohort_id, week))
    all_rows = rows.fetchall()
    if not all_rows:
        return {'reply': f'第{week}周暂无积分数据', 'actions': []}
    reply = f'**第{week}周积分排名：**\n'
    for i, r in enumerate(all_rows):
        reply += f'{i+1}. {r["name"]} — {r["score"]}分\n'
    return {'reply': reply, 'actions': []}


# ── 成绩查询 ───────────────────────────────────────

def handle_query_scores(db, cohort_id, semester_id, msg):
    """查询成绩信息"""
    # 查具体学生成绩
    name_match = re.search(r'([\u4e00-\u9fff]{2,4}).{0,5}(成绩|分数|考了多少)', msg)
    if name_match:
        name = name_match.group(1)
        row = db.execute("SELECT id, name FROM students WHERE cohort_id = ? AND name LIKE ? AND is_active = 1",
                         (cohort_id, f'%{name}%')).fetchone()
        if row:
            scores = db.execute("""
                SELECT se.name as exam_name, si.subject, si.score
                FROM score_items si
                JOIN score_exams se ON si.exam_id = se.id
                WHERE si.student_id = ?
                ORDER BY se.exam_date DESC, si.subject
                LIMIT 20
            """, (row['id'],)).fetchall()
            if not scores:
                return {'reply': f'{row["name"]} 暂无成绩记录', 'actions': []}
            reply = f'**{row["name"]}** 的成绩：\n'
            current_exam = ''
            for s in scores:
                if s['exam_name'] != current_exam:
                    current_exam = s['exam_name']
                    reply += f'\n**{current_exam}**：'
                reply += f' {s["subject"]}{s["score"]}'
            return {'reply': reply, 'actions': []}
        return {'reply': f'没有找到名为「{name}」的学生', 'actions': []}

    # 考试列表
    exams = db.execute("""
        SELECT se.name, se.exam_type, se.exam_date, COUNT(DISTINCT si.student_id) as cnt
        FROM score_exams se LEFT JOIN score_items si ON se.id = si.exam_id
        WHERE se.cohort_id = ?
        GROUP BY se.id ORDER BY se.exam_date DESC LIMIT 5
    """, (cohort_id,)).fetchall()
    if not exams:
        return {'reply': '暂无考试记录。你可以到「成绩管理」页面新建考试并录入成绩。', 'actions': []}
    reply = '**最近考试：**\n'
    for e in exams:
        reply += f'- {e["name"]}（{e["exam_type"]}）{e["cnt"]}人参加\n'
    return {'reply': reply, 'actions': []}


def handle_query_scores_exam_detail(db, cohort_id, msg):
    """查询考试详细统计"""
    # 找最新考试
    exam = db.execute("""
        SELECT id, name FROM score_exams WHERE cohort_id = ?
        ORDER BY exam_date DESC LIMIT 1
    """, (cohort_id,)).fetchone()
    if not exam:
        return {'reply': '暂无考试记录', 'actions': []}

    # 各科统计
    stats = db.execute("""
        SELECT subject,
               ROUND(AVG(score), 1) as avg_score,
               MAX(score) as max_score,
               MIN(score) as min_score,
               COUNT(*) as cnt
        FROM score_items WHERE exam_id = ?
        GROUP BY subject ORDER BY subject
    """, (exam['id'],)).fetchall()
    if not stats:
        return {'reply': f'{exam["name"]}暂无成绩数据', 'actions': []}

    reply = f'**{exam["name"]} 成绩统计：**\n'
    for s in stats:
        reply += f'\n**{s["subject"]}**：平均 {s["avg_score"]} | 最高 {s["max_score"]} | 最低 {s["min_score"]}（共{s["cnt"]}人）\n'
    return {'reply': reply, 'actions': []}


# ── 事件查询 ───────────────────────────────────────

def handle_query_events(db, cohort_id, msg):
    """查询事件记录"""
    name_match = re.search(r'([\u4e00-\u9fff]{2,4})(的|.{0,2})(事件|记录|违纪|处分|表扬)', msg)
    if name_match:
        name = name_match.group(1)
        # 先精确匹配，再模糊
        row = db.execute("SELECT id, name FROM students WHERE cohort_id = ? AND name = ? AND is_active = 1",
                         (cohort_id, name)).fetchone()
        if not row:
            row = db.execute("SELECT id, name FROM students WHERE cohort_id = ? AND name LIKE ? AND is_active = 1",
                             (cohort_id, f'%{name}%')).fetchone()
        if row:
            events = db.execute("""
                SELECT event_type, title, event_date, description
                FROM events WHERE student_id = ?
                ORDER BY event_date DESC LIMIT 5
            """, (row['id'],)).fetchall()
            if not events:
                return {'reply': f'{row["name"]} 暂无事件记录', 'actions': []}
            reply = f'**{row["name"]}** 的事件记录：\n'
            for e in events:
                reply += f'- [{e["event_date"]}] {e["event_type"]}：{e["title"]}\n'
            return {'reply': reply, 'actions': []}

    # 最近事件
    events = db.execute("""
        SELECT s.name, e.event_type, e.title, e.event_date
        FROM events e JOIN students s ON e.student_id = s.id
        WHERE s.cohort_id = ?
        ORDER BY e.event_date DESC LIMIT 5
    """, (cohort_id,)).fetchall()
    if not events:
        return {'reply': '暂无事件记录。你可以说「记录XX同学违纪/表扬」来添加。', 'actions': []}
    reply = '**最近事件：**\n'
    for e in events:
        reply += f'- [{e["event_date"]}] {e["name"]}·{e["event_type"]}：{e["title"]}\n'
    return {'reply': reply, 'actions': []}


def handle_query_events_type(db, cohort_id, msg):
    """按事件类型查询"""
    etype = None
    if any(kw in msg for kw in ['违纪', '处分']):
        etype = '违纪'
    elif '表扬' in msg:
        etype = '表扬'
    elif '谈话' in msg:
        etype = '谈话'
    elif '家访' in msg:
        etype = '家访'

    if etype:
        events = db.execute("""
            SELECT s.name, e.event_type, e.title, e.event_date
            FROM events e JOIN students s ON e.student_id = s.id
            WHERE s.cohort_id = ? AND e.event_type = ?
            ORDER BY e.event_date DESC LIMIT 10
        """, (cohort_id, etype)).fetchall()
        if not events:
            return {'reply': f'暂无{etype}记录', 'actions': []}
        reply = f'**最近{etype}记录：**\n'
        for e in events:
            reply += f'- [{e["event_date"]}] {e["name"]}：{e["title"]}\n'
        return {'reply': reply, 'actions': []}

    return {'reply': '你想查哪类事件？违纪、表扬、谈话、家访', 'actions': []}


def handle_query_events_most(db, cohort_id):
    """查询事件最多的学生"""
    rows = db.execute("""
        SELECT s.name, COUNT(*) as cnt
        FROM events e JOIN students s ON e.student_id = s.id
        WHERE s.cohort_id = ?
        GROUP BY s.id ORDER BY cnt DESC LIMIT 5
    """, (cohort_id,)).fetchall()
    if not rows:
        return {'reply': '暂无事件记录', 'actions': []}
    reply = '**事件最多的学生：**\n'
    for i, r in enumerate(rows):
        reply += f'{i+1}. {r["name"]} — {r["cnt"]}次\n'
    return {'reply': reply, 'actions': []}


# ── 操作类 ───────────────────────────────────────

def handle_add_student(db, cohort_id, msg):
    """添加学生"""
    m = re.search(r'(?:添加|新增|加入|录入)\s*(?:学生|同学)?\s*([\u4e00-\u9fff]{2,4})', msg)
    if not m:
        return {'reply': '请告诉我学生姓名，例如：「添加学生 张三」', 'actions': []}
    name = m.group(1)
    existing = db.execute("SELECT id FROM students WHERE cohort_id = ? AND name = ?", (cohort_id, name)).fetchone()
    if existing:
        return {'reply': f'学生「{name}」已存在', 'actions': []}
    max_no = db.execute("SELECT MAX(CAST(student_no AS INTEGER)) as m FROM students WHERE cohort_id = ? AND student_no NOT LIKE 'AUTO-%'",
                        (cohort_id,)).fetchone()
    next_no = str((max_no['m'] or 0) + 1)
    db.execute("INSERT INTO students (cohort_id, student_no, name) VALUES (?, ?, ?)", (cohort_id, next_no, name))
    db.commit()
    return {
        'reply': f'✅ 已添加学生「{name}」，学号 {next_no}。\n\n你可以在「学生管理」页面编辑更多信息。',
        'actions': [{'type': 'student_added', 'name': name}]
    }


def handle_add_event(db, cohort_id, msg):
    """记录事件"""
    m = re.search(r'(?:记录|记下|发生)\s*([\u4e00-\u9fff]{2,3})\s*(违纪|处分|表扬|谈话|家访|其他)[：:]*\s*(.*)', msg)
    if not m:
        return {'reply': '请按格式说明，例如：\n「记录张三违纪：上课玩手机」\n「记录李四表扬：期中考试进步很大」', 'actions': []}
    name, event_type, title = m.group(1), m.group(2), m.group(3).strip()
    if not title:
        title = event_type

    row = db.execute("SELECT id FROM students WHERE cohort_id = ? AND name LIKE ? AND is_active = 1",
                     (cohort_id, f'%{name}%')).fetchone()
    if not row:
        return {'reply': f'没有找到名为「{name}」的学生，请先添加。', 'actions': []}

    today = datetime.now().strftime('%Y-%m-%d')
    db.execute("INSERT INTO events (student_id, event_type, title, event_date) VALUES (?, ?, ?, ?)",
               (row['id'], event_type, title, today))
    db.commit()
    return {
        'reply': f'✅ 已记录：{name} · {event_type} · {title}',
        'actions': [{'type': 'event_added', 'student': name, 'event_type': event_type}]
    }


def handle_add_points(db, cohort_id, semester_id, msg):
    """录入积分"""
    m = re.search(r'(?:给|录入|添加)?\s*([\u4e00-\u9fff]{2,3})\s*(?:积分)?\s*(?:加|减)?\s*(\d+)\s*分', msg)
    if m:
        name = m.group(1)
        score = float(m.group(2))
        if '减' in msg:
            score = -score
    else:
        m = re.search(r'(?:给|录入)?\s*([\u4e00-\u9fff]{2,3})\s*(?:积分)?\s*([+-]?\d+)\s*分', msg)
        if m:
            name = m.group(1)
            score = float(m.group(2))
        else:
            return {'reply': '请按格式说明，例如：\n「给张三加10分」\n「张三积分-5」', 'actions': []}

    row = db.execute("SELECT id FROM students WHERE cohort_id = ? AND name LIKE ? AND is_active = 1",
                     (cohort_id, f'%{name}%')).fetchone()
    if not row:
        return {'reply': f'没有找到名为「{name}」的学生', 'actions': []}

    if not semester_id:
        return {'reply': '请先在侧边栏选择一个学期', 'actions': []}

    latest = db.execute("""
        SELECT MAX(week_num) as w FROM weekly_points wp
        JOIN students s ON wp.student_id = s.id
        WHERE s.cohort_id = ? AND wp.semester_id = ?
    """, (cohort_id, semester_id)).fetchone()
    week = (latest['w'] or 0) + 1 if not latest['w'] else latest['w']

    existing = db.execute("SELECT id, score FROM weekly_points WHERE student_id = ? AND week_num = ? AND semester_id = ?",
                          (row['id'], week, semester_id)).fetchone()
    if existing:
        new_score = existing['score'] + score
        db.execute("UPDATE weekly_points SET score = ? WHERE id = ?", (new_score, existing['id']))
    else:
        db.execute("INSERT INTO weekly_points (student_id, week_num, semester_id, score, source) VALUES (?, ?, ?, ?, 'chat')",
                   (row['id'], week, semester_id, score))
    db.commit()

    return {
        'reply': f'✅ 已给 {name} 第{week}周 {"+" if score >= 0 else ""}{score}分',
        'actions': [{'type': 'points_added', 'student': name, 'score': score}]
    }


# ── 其他 ─────────────────────────────────────────

def handle_help():
    """帮助信息"""
    return {
        'reply': '''我可以帮你管理班级数据，支持以下操作：

**📊 学生查询：**
- 「班级有多少人」— 学生总数
- 「男生多少人」— 男女分布
- 「各小组人数」— 分组情况
- 「查张三」— 学生信息

**💰 积分查询：**
- 「张三的积分」— 个人积分
- 「积分排名」— Top 10
- 「谁积分最低」— 底部名单
- 「各小组平均积分」— 小组统计
- 「第3周积分排名」— 按周查询

**📝 成绩查询：**
- 「最近考试」— 考试列表
- 「张三的成绩」— 个人成绩
- 「平均分」— 最新考试统计

**🔔 事件查询：**
- 「最近事件」— 最新记录
- 「最近的违纪」— 按类型查看
- 「谁违纪最多」— 统计排行

**➕ 快速操作：**
- 「添加学生 张三」— 新增学生
- 「给张三加10分」— 录入积分
- 「记录张三违纪：上课玩手机」— 记录事件

试试看吧！🌿''',
        'actions': []
    }


def handle_unknown():
    """无法识别的意图"""
    return {
        'reply': '不太理解你的意思 😅\n\n试试问我：\n- 「班级有多少人」— 学生总数\n- 「积分排名」— 积分排行\n- 「男生多少人」— 男女分布\n- 「各小组人数」— 分组情况\n- 「谁积分最低」— 底部名单\n- 「最近违纪」— 事件记录\n- 「给张三加10分」— 录入积分\n- 「记录张三违纪：上课说话」— 记录事件\n\n或者输入「帮助」查看更多功能。',
        'actions': []
    }
