"""Excel数据导入工具"""
import os


def _get_reader(filepath):
    """根据文件扩展名选择读取方式"""
    ext = filepath.rsplit('.', 1)[-1].lower()
    if ext == 'xls':
        import xlrd
        wb = xlrd.open_workbook(filepath)
        ws = wb.sheet_by_index(0)
        rows = []
        for i in range(ws.nrows):
            rows.append([ws.cell_value(i, j) for j in range(ws.ncols)])
        return rows
    else:
        import openpyxl
        wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append(list(row))
        wb.close()
        return rows


def _read_sheet(filepath, sheet_name=None):
    """读取指定sheet"""
    ext = filepath.rsplit('.', 1)[-1].lower()
    if ext == 'xls':
        import xlrd
        wb = xlrd.open_workbook(filepath)
        if sheet_name:
            ws = wb.sheet_by_name(sheet_name)
        else:
            ws = wb.sheet_by_index(0)
        rows = []
        for i in range(ws.nrows):
            rows.append([ws.cell_value(i, j) for j in range(ws.ncols)])
        return rows, [ws.sheet_by_name(s).name for s in wb.sheet_names()]
    else:
        import openpyxl
        wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
        sheet_names = wb.sheetnames
        if sheet_name:
            ws = wb[sheet_name]
        else:
            ws = wb[sheet_names[0]]
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append(list(row))
        wb.close()
        return rows, sheet_names


def preview_excel(filepath):
    """预览Excel文件内容"""
    ext = filepath.rsplit('.', 1)[-1].lower()
    if ext == 'xls':
        import xlrd
        wb = xlrd.open_workbook(filepath)
        sheets = []
        for name in wb.sheet_names():
            ws = wb.sheet_by_name(name)
            header = [ws.cell_value(0, j) for j in range(ws.ncols)]
            sample = []
            for i in range(1, min(4, ws.nrows)):
                sample.append([ws.cell_value(i, j) for j in range(ws.ncols)])
            sheets.append({
                'name': name,
                'rows': ws.nrows,
                'cols': ws.ncols,
                'header': header,
                'sample': sample
            })
        return {'sheets': sheets}
    else:
        import openpyxl
        wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
        sheets = []
        for name in wb.sheetnames:
            ws = wb[name]
            all_rows = list(ws.iter_rows(max_row=4, values_only=True))
            header = list(all_rows[0]) if all_rows else []
            sample = [list(r) for r in all_rows[1:]] if len(all_rows) > 1 else []
            sheets.append({
                'name': name,
                'rows': ws.max_row or 0,
                'cols': ws.max_column or 0,
                'header': [str(h) if h else '' for h in header],
                'sample': [[str(c) if c is not None else '' for c in row] for row in sample]
            })
        wb.close()
        return {'sheets': sheets}


def parse_student_info(filepath):
    """解析学生信息表
    期望列: 序号, 学生姓名, 学生所在班级, 学生性别, 学生出生日期, 民族, 学生身份证号,
           现住址, 户口类别, 户口所在地, 父亲, 父亲工作单位, 父亲电话, 母亲, 母亲工作单位, 母亲电话
    """
    rows = _get_reader(filepath)
    if not rows:
        return []

    header = rows[0]
    # 找到列索引
    col_map = {}
    for i, h in enumerate(header):
        h_str = str(h).strip() if h else ''
        if '姓名' in h_str:
            col_map['name'] = i
        elif '班级' in h_str:
            col_map['class'] = i
        elif '性别' in h_str:
            col_map['gender'] = i
        elif '出生' in h_str:
            col_map['birth'] = i
        elif '民族' in h_str:
            col_map['ethnicity'] = i
        elif '身份证' in h_str:
            col_map['id_number'] = i
        elif '序号' in h_str:
            col_map['seq'] = i
        elif '现住址' in h_str or '住址' in h_str or '地址' in h_str:
            col_map['address'] = i
        elif '户口类别' in h_str or '户口性质' in h_str:
            col_map['household_type'] = i
        elif '户口所在地' in h_str or '户籍' in h_str:
            col_map['household_loc'] = i
        elif '父亲' in h_str and '单位' in h_str:
            col_map['father_work'] = i
        elif '父亲' in h_str and ('电话' in h_str or '手机' in h_str):
            col_map['father_phone'] = i
        elif '父亲' in h_str and '单位' not in h_str and '电话' not in h_str and '手机' not in h_str:
            col_map['father'] = i
        elif '母亲' in h_str and '单位' in h_str:
            col_map['mother_work'] = i
        elif '母亲' in h_str and ('电话' in h_str or '手机' in h_str):
            col_map['mother_phone'] = i
        elif '母亲' in h_str and '单位' not in h_str and '电话' not in h_str and '手机' not in h_str:
            col_map['mother'] = i

    students = []
    for row in rows[1:]:
        if not row or not row[col_map.get('name', 1)]:
            continue
        name = str(row[col_map.get('name', 1)]).strip()
        if not name:
            continue

        seq = row[col_map.get('seq', 0)]
        class_no = row[col_map.get('class', 2)]

        gender_val = row[col_map.get('gender', 3)]
        if isinstance(gender_val, (int, float)):
            gender = '男' if gender_val == 1 else '女'
        else:
            gender = str(gender_val).strip() if gender_val else ''

        birth = row[col_map.get('birth', 4)]
        if isinstance(birth, float):
            birth = ''
        birth = str(birth).strip() if birth else ''

        ethnicity = str(row[col_map.get('ethnicity', 5)]).strip() if col_map.get('ethnicity') is not None and len(row) > col_map.get('ethnicity', 5) else ''
        id_number = str(row[col_map.get('id_number', 6)]).strip() if col_map.get('id_number') is not None and len(row) > col_map.get('id_number', 6) else ''

        student_no = str(int(seq)) if isinstance(seq, (int, float)) and seq not in (None, 0, 0.0, '') else (str(seq).strip() if seq else '')

        # 解析班级号
        raw_class = row[col_map.get('class', 2)]
        if isinstance(raw_class, (int, float)):
            class_no = str(int(raw_class))
        else:
            class_no = str(raw_class).strip() if raw_class else ''

        students.append({
            'student_no': student_no,
            'name': name,
            'gender': gender,
            'birth_date': birth,
            'ethnicity': ethnicity,
            'id_number': id_number,
            'class_no': class_no,
            'address': str(row[col_map.get('address', -1)]).strip() if col_map.get('address') is not None and len(row) > col_map['address'] else '',
            'household_type': str(row[col_map.get('household_type', -1)]).strip() if col_map.get('household_type') is not None and len(row) > col_map['household_type'] else '',
            'household_loc': str(row[col_map.get('household_loc', -1)]).strip() if col_map.get('household_loc') is not None and len(row) > col_map['household_loc'] else '',
            'father': str(row[col_map.get('father', -1)]).strip() if col_map.get('father') is not None and len(row) > col_map['father'] else '',
            'father_work': str(row[col_map.get('father_work', -1)]).strip() if col_map.get('father_work') is not None and len(row) > col_map['father_work'] else '',
            'father_phone': str(row[col_map.get('father_phone', -1)]).strip() if col_map.get('father_phone') is not None and len(row) > col_map['father_phone'] else '',
            'mother': str(row[col_map.get('mother', -1)]).strip() if col_map.get('mother') is not None and len(row) > col_map['mother'] else '',
            'mother_work': str(row[col_map.get('mother_work', -1)]).strip() if col_map.get('mother_work') is not None and len(row) > col_map['mother_work'] else '',
            'mother_phone': str(row[col_map.get('mother_phone', -1)]).strip() if col_map.get('mother_phone') is not None and len(row) > col_map['mother_phone'] else '',
            'group_name': '',
            'group_order': None,
        })
    return students


def parse_points_excel(filepath, semester):
    """解析积分汇总表
    期望: 每个Sheet代表一周，第一列姓名，其余列为积分
    或者: 总表形式，列为 小组, 组序, 学号, 姓名, 各周积分...
    """
    ext = filepath.rsplit('.', 1)[-1].lower()
    records = []

    if ext == 'xls':
        import xlrd
        wb = xlrd.open_workbook(filepath)
        for sn in wb.sheet_names():
            ws = wb.sheet_by_name(sn)
            if ws.nrows < 2:
                continue
            header = [str(ws.cell_value(0, j)).strip() for j in range(ws.ncols)]
            # 找姓名列
            name_col = None
            for i, h in enumerate(header):
                if '姓名' in h:
                    name_col = i
                    break
            if name_col is None:
                continue

            # 尝试解析sheet名为周次
            try:
                week_num = int(sn.strip())
            except ValueError:
                continue

            for r in range(1, ws.nrows):
                name = str(ws.cell_value(r, name_col)).strip()
                if not name:
                    continue
                # 找合计列或最后一个数值列
                score = None
                for c in range(ws.ncols - 1, name_col, -1):
                    val = ws.cell_value(r, c)
                    if isinstance(val, (int, float)) and val != 0:
                        score = val
                        break
                if score is not None:
                    records.append({'name': name, 'weeks': {week_num: score}})
    else:
        import openpyxl
        wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
        for sn in wb.sheetnames:
            ws = wb[sn]
            rows = list(ws.iter_rows(values_only=True))
            if len(rows) < 2:
                continue
            header = [str(h).strip() if h else '' for h in rows[0]]

            name_col = None
            for i, h in enumerate(header):
                if '姓名' in h:
                    name_col = i
                    break
            if name_col is None:
                continue

            # 检查是否是周次sheet
            try:
                week_num = int(sn.strip())
            except ValueError:
                # 总表形式 - 找各周的列
                for row in rows[1:]:
                    name = str(row[name_col]).strip() if row[name_col] else ''
                    if not name:
                        continue
                    weeks = {}
                    for c in range(len(header)):
                        if c == name_col:
                            continue
                        try:
                            week_n = int(header[c])
                            val = row[c]
                            if isinstance(val, (int, float)) and val != 0:
                                weeks[week_n] = val
                        except (ValueError, TypeError):
                            continue
                    if weeks:
                        records.append({'name': name, 'weeks': weeks})
                continue

            for row in rows[1:]:
                name = str(row[name_col]).strip() if row[name_col] else ''
                if not name:
                    continue
                score = None
                for c in range(len(row) - 1, name_col, -1):
                    val = row[c]
                    if isinstance(val, (int, float)) and val != 0:
                        score = val
                        break
                if score is not None:
                    records.append({'name': name, 'weeks': {week_num: score}})
        wb.close()

    return records


def parse_scores_excel(filepath):
    """解析成绩表
    期望: 第一列姓名，后面各列为科目分数
    """
    rows = _get_reader(filepath)
    if not rows:
        return []

    header = rows[0]
    name_col = None
    subjects = {}

    for i, h in enumerate(header):
        h_str = str(h).strip() if h else ''
        if '姓名' in h_str:
            name_col = i
        elif h_str and h_str not in ('排名', '班次', '进退步', '总分', '序号', '学号'):
            # 判断是否是科目列（检查下面是否有数值）
            is_subject = True
            for check_row in rows[1:4]:
                if i < len(check_row):
                    val = check_row[i]
                    if val is not None and not isinstance(val, (int, float)):
                        try:
                            float(val)
                        except (ValueError, TypeError):
                            is_subject = False
                            break
            if is_subject:
                subjects[i] = h_str

    if name_col is None:
        return []

    records = []
    for row in rows[1:]:
        name = str(row[name_col]).strip() if row[name_col] else ''
        if not name:
            continue
        scores = {}
        for col_idx, subj_name in subjects.items():
            if col_idx < len(row):
                val = row[col_idx]
                if isinstance(val, (int, float)):
                    scores[subj_name] = val
                elif val:
                    try:
                        scores[subj_name] = float(val)
                    except (ValueError, TypeError):
                        pass
        if scores:
            records.append({'name': name, 'scores': scores})

    return records
