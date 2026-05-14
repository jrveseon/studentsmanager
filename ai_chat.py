"""AI对话 - OpenAI兼容API调用"""
import json
import urllib.request
import urllib.error


def get_ai_settings(db):
    """从settings表获取AI配置"""
    rows = db.execute("SELECT key, value FROM settings WHERE key >= 'ai_' AND key < 'aj'").fetchall()
    settings = {r['key']: r['value'] for r in rows}
    return {
        'provider': settings.get('ai_provider', ''),
        'api_key': settings.get('ai_api_key', ''),
        'model': settings.get('ai_model', ''),
        'api_url': settings.get('ai_api_url', ''),
    }


def format_val(v):
    """格式化字段值"""
    if v is None or v == '' or v == 'None':
        return '-'
    return str(v)


def build_rich_system_prompt(db, cohort_id, semester_id):
    """构建富含真实数据库上下文的系统提示词
    注入完整的数据库数据，让AI能基于真实数据回答任何问题，
    无需编造。所有数据直接从 SQLite 数据库查询。
    """
    from db import dicts_from_rows
    parts = []

    # ── 角色定义 ──
    parts.append("你叫「阿悟」，是初中班主任的AI助手。你的工作就是回答班主任关于班级数据的问题。")
    parts.append("")

    # ── 班级信息 ──
    cohort = db.execute("SELECT * FROM cohorts WHERE id = ?", (cohort_id,)).fetchone()
    if cohort:
        parts.append(f"📌 当前班级：{cohort['display_name']}")

    if semester_id:
        sem = db.execute("SELECT * FROM semesters WHERE id = ?", (semester_id,)).fetchone()
        if sem:
            parts.append(f"📌 当前学期：{sem['name']}（{sem['year_range'] or ''}）")

    parts.append(f"📌 查询日期：{__import__('datetime').datetime.now().strftime('%Y-%m-%d')}")
    parts.append("")

    # ── 完整学生信息表（精简字段，减少token消耗） ──
    students = db.execute("""
        SELECT student_no, name, gender, birth_date, ethnicity,
               group_name, phone, parent_phone
        FROM students WHERE cohort_id = ? AND is_active = 1
        ORDER BY CAST(NULLIF(student_no, '') AS INTEGER)
    """, (cohort_id,)).fetchall()

    sarr = [dict(r) for r in students]
    parts.append(f"## 📋 学生信息（共 {len(sarr)} 人）")
    parts.append("")
    parts.append("| 学号 | 姓名 | 性别 | 出生日期 | 民族 | 小组 | 本人电话 | 家长电话 |")
    parts.append("|------|------|------|----------|------|------|----------|----------|")
    for s in sarr:
        parts.append(
            f"| {format_val(s['student_no'])} "
            f"| {format_val(s['name'])} "
            f"| {format_val(s['gender'])} "
            f"| {format_val(s['birth_date'])} "
            f"| {format_val(s['ethnicity'])} "
            f"| {format_val(s['group_name'])} "
            f"| {format_val(s['phone'])} "
            f"| {format_val(s['parent_phone'])} |"
        )
    parts.append("")

    # ── 积分数据 ──
    if semester_id:
        pts = db.execute("""
            SELECT s.name, wp.week_num, wp.score
            FROM weekly_points wp
            JOIN students s ON wp.student_id = s.id
            WHERE wp.semester_id = ? AND s.cohort_id = ?
            ORDER BY wp.week_num, wp.score DESC
        """, (semester_id, cohort_id)).fetchall()
        if pts:
            parts.append("## 📊 当前学期各周积分")
            parts.append("")
            by_week = {}
            for r in pts:
                by_week.setdefault(r['week_num'], []).append(r)
            for wk in sorted(by_week.keys()):
                scores = by_week[wk]
                total_sum = sum(s['score'] for s in scores)
                top3 = sorted(scores, key=lambda x: x['score'], reverse=True)[:3]
                top3_txt = '、'.join(f"{s['name']}({s['score']})" for s in top3)
                parts.append(f"**第{wk}周** — 共{len(scores)}人，总分{total_sum} | 前三：{top3_txt}")
            parts.append("")

    # ── 成绩数据 ──
    exams = db.execute("""
        SELECT id, name, exam_type, exam_date FROM score_exams
        WHERE cohort_id = ? ORDER BY exam_date DESC LIMIT 5
    """, (cohort_id,)).fetchall()
    if exams:
        parts.append("## 📝 考试成绩")
        parts.append("")
        for exam in exams:
            scores = db.execute("""
                SELECT s.name, si.subject, si.score
                FROM score_items si JOIN students s ON si.student_id = s.id
                WHERE si.exam_id = ? ORDER BY si.subject, si.score DESC
            """, (exam['id'],)).fetchall()
            if scores:
                parts.append(f"**{exam['name']}**（{exam['exam_date'] or ''}）")
                by_subject = {}
                for r in scores:
                    by_subject.setdefault(r['subject'], []).append(r)
                for subj in sorted(by_subject.keys()):
                    items = by_subject[subj]
                    scores_list = [s['score'] for s in items if s['score'] is not None]
                    if scores_list:
                        avg = sum(scores_list) / len(scores_list)
                        top = max(scores_list)
                        low = min(scores_list)
                        top_name = next((s['name'] for s in items if s['score'] == top), '')
                        parts.append(f"  {subj}：平均{avg:.1f}，最高{top}（{top_name}），最低{low}")
                parts.append("")

    # ── 事件数据 ──
    events = db.execute("""
        SELECT s.name, e.event_type, e.title, e.event_date
        FROM events e JOIN students s ON e.student_id = s.id
        WHERE s.cohort_id = ? ORDER BY e.event_date DESC LIMIT 20
    """, (cohort_id,)).fetchall()
    if events:
        parts.append("## 🔔 事件记录（最近20条）")
        parts.append("")
        for e in events:
            parts.append(f"- [{e['event_date']}] {e['name']}·{e['event_type']}：{e['title']}")
        parts.append("")

    # ── 重要规则 ──
    parts.append("")
    parts.append("## ⚠️ 重要规则")
    parts.append("1. **以上所有数据都是直接从本地 SQLite 数据库查询的真实数据，不是示例。**")
    parts.append("2. **你的回答必须严格基于上面提供的数据，不能编造、不能猜测。**")
    parts.append("3. 如果用户问的问题在上面数据中找不到答案，直接说「抱歉，数据库中没有找到这个信息」，不要自己编。")
    parts.append("4. 回答要简洁直接，不要啰嗦。用自然的中文回答。")
    parts.append("5. 如果涉及学生姓名匹配，一定要严格匹配上面表格中的姓名。")
    parts.append("")
    parts.append("### 🔑 核心区分：考试成绩 vs 量化积分")
    parts.append("这是两个**完全独立**的数据系统，不能混淆：")
    parts.append("")
    parts.append("- **考试成绩**：存在 `score_exams`（考试）和 `score_items`（各科分数）表中。")
    parts.append("  每次考试创建一条 `score_exams` 记录，每个学生的各科分数存为 `score_items` 记录。")
    parts.append("  用 `###EXECUTE###` 操作时使用 `add_scores` 或直接告诉用户通过导入功能处理。")
    parts.append("")
    parts.append("- **量化积分**：存在 `weekly_points` 表中，按学期和按周记录。")
    parts.append("  录入积分请使用 **add_points** 命令（见下方操作说明）。")
    parts.append("  每个学生每周只有一条积分记录，多次录入会累加到同一周。")
    parts.append("")
    parts.append("**⚠️ 重要：上传文件时系统会自动识别文件类型。如果文件列头含有「积分」「得分」「量化」等字眼，会自动导入为量化积分。如果文件是成绩表，会自动创建考试并录入分数。你无需手动处理导入逻辑。**")
    parts.append("")
    parts.append("## 🔧 执行操作（重要：你可以直接修改数据库）")
    parts.append("如果用户要求修改数据，在你的回复末尾加上操作指令，格式如下：")
    parts.append("")
    parts.append("###EXECUTE:")
    parts.append('{"action":"update_student","params":{"name":"学生姓名","field":"要修改的字段名","value":"新值"}}')
    parts.append('###')
    parts.append("")
    parts.append("支持的 action 类型：")
    parts.append("")
    parts.append("1. **update_student** — 修改学生字段")
    parts.append("   字段名可以是：name, gender, birth_date, ethnicity, id_number, group_name, address, household_type, household_loc, father, father_work, father_phone, mother, mother_work, mother_phone, student_no")
    parts.append("   示例：{\"action\":\"update_student\",\"params\":{\"name\":\"高成硕\",\"field\":\"father_phone\",\"value\":\"13800000000\"}}")
    parts.append("")
    parts.append("2. **add_event** — 记录学生事件")
    parts.append('   示例：{"action":"add_event","params":{"name":"高成硕","event_type":"违纪","title":"上课玩手机"}}')
    parts.append("")
    parts.append("3. **add_points** — 录入积分（必须当前学期有效）")
    parts.append('   示例：{"action":"add_points","params":{"name":"高成硕","score":10}}')
    parts.append("")
    parts.append("4. **batch_update_students** — 批量更新多个学生的同一字段（推荐用于批量操作）")
    parts.append("   params需要包含 \"students\"（数组，每项含 name 和 value）和 \"field\"（字段名）")
    parts.append("   示例（批量更新学号）：")
    parts.append('   {"action":"batch_update_students","params":{"field":"student_no","students":[')
    parts.append('     {"name":"高成硕","value":"01"},')
    parts.append('     {"name":"崔伴佟","value":"02"},')
    parts.append('     {"name":"曹子硕","value":"03"}')
    parts.append('   ]}}')
    parts.append("")
    parts.append("**重要原则：对于批量操作（如更新全班学号），永远使用 batch_update_students 一条命令搞定，不要生成多个独立 update_student。**")
    parts.append("")
    parts.append("重要：")
    parts.append("- 一个回复中可以包含多个 ###EXECUTE...### 块")
    parts.append("- 执行结果会在下次回复中告诉你，你需要在回答中引用")

    return '\n'.join(parts)


def call_ai_api(settings, system_prompt, user_message):
    """调用 OpenAI 兼容 API（单轮对话）"""
    return call_ai_api_with_history(settings, system_prompt, user_message, [])


def call_ai_api_with_history(settings, system_prompt, user_message, history):
    """调用 OpenAI 兼容 API（支持对话历史）"""
    if not settings['api_key']:
        return None

    # 确定 API URL
    if settings['api_url']:
        api_url = settings['api_url'].rstrip('/')
        if not api_url.endswith('/chat/completions'):
            api_url += '/chat/completions'
    elif settings['provider'] == 'deepseek':
        api_url = 'https://api.deepseek.com/v1/chat/completions'
    elif settings['provider'] == 'openai':
        api_url = 'https://api.openai.com/v1/chat/completions'
    else:
        return None

    model = settings['model'] or 'gpt-4o-mini'

    # 构建消息数组：system + 历史记录 + 最新提问
    messages = [{'role': 'system', 'content': system_prompt}]
    for h in history:
        if h.get('role') in ('user', 'assistant'):
            # 历史消息太长时截断
            content = h['content']
            if len(content) > 2000:
                content = content[:2000] + '…(截断)'
            messages.append({'role': h['role'], 'content': content})
    messages.append({'role': 'user', 'content': user_message})

    payload = {
        'model': model,
        'messages': messages,
        'temperature': 0.3,
        'max_tokens': 4096,
    }

    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {settings["api_key"]}',
        },
        method='POST',
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            reply = result['choices'][0]['message']['content'].strip()
            return {'reply': reply, 'actions': []}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='replace')
        return {'reply': f'AI 调用失败（HTTP {e.code}）：{error_body[:200]}', 'actions': []}
    except Exception as e:
        return {'reply': f'AI 调用出错：{str(e)[:200]}', 'actions': []}
