# backend.py
import json
import os
import sqlite3
import html
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from PIL import Image, ImageFilter, ImageOps, ImageStat
from werkzeug.security import check_password_hash, generate_password_hash

# requests и python-dotenv необязательны: без них сервер всё равно стартует
try:
    import requests
except ImportError:
    requests = None
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

# Загружаем переменные окружения из .env
if load_dotenv:
    load_dotenv()

# --- НАСТРОЙКИ КЛЮЧЕЙ ---
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY', 'YOUR_GOOGLE_API_KEY_HERE')
GOOGLE_CSE_ID = os.environ.get('GOOGLE_CSE_ID', 'YOUR_CSE_ID_HERE')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', 'YOUR_OPENAI_KEY_HERE')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, 'talentradar.db')
UPLOADS = os.path.join(BASE_DIR, 'static', 'uploads')

DEMO_STUDENT_EMAIL = 'student@talentradar.kz'
DEMO_STUDENT_PASSWORD = 'student123'
DEMO_UNI_EMAIL = 'vuz@talentradar.kz'
DEMO_UNI_PASSWORD = 'vuz123'

# URLs реальных платформ
DEVPOST_API_URL = "https://devpost.com/api/hackathons"
STEPIK_API_URL = "https://stepik.org/api/v2/courses"


def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def _cols(cur, table):
    return {row[1] for row in cur.execute(f'PRAGMA table_info({table})')}


def _add_column(cur, table, column, ddl):
    if column not in _cols(cur, table):
        cur.execute(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}')


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password_hash TEXT,
            role TEXT,
            token TEXT UNIQUE,
            name TEXT
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE,
            name TEXT,
            city TEXT,
            grade TEXT,
            track TEXT,
            visibility_score INTEGER DEFAULT 15,
            user_id INTEGER
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS universities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            name TEXT,
            city TEXT
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS certificates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            title TEXT,
            org TEXT,
            date TEXT,
            status TEXT DEFAULT 'pending',
            score_boost INTEGER DEFAULT 0,
            image_filename TEXT,
            review_note TEXT,
            checks_json TEXT,
            FOREIGN KEY (student_id) REFERENCES students(id)
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            type TEXT,
            date TEXT,
            bonus TEXT,
            region TEXT,
            track TEXT
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS activity_joins (
            student_id INTEGER,
            activity_id INTEGER,
            PRIMARY KEY (student_id, activity_id)
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            university TEXT,
            title TEXT,
            message TEXT,
            status TEXT DEFAULT 'pending',
            region TEXT,
            FOREIGN KEY (student_id) REFERENCES students(id)
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            city TEXT,
            grade TEXT,
            track TEXT,
            score INTEGER,
            achievement TEXT,
            offer_sent INTEGER DEFAULT 0
        )
    ''')

    _add_column(cur, 'students', 'user_id', 'INTEGER')
    _add_column(cur, 'certificates', 'review_note', 'TEXT')
    _add_column(cur, 'certificates', 'checks_json', 'TEXT')

    if cur.execute('SELECT COUNT(*) FROM students').fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO students (token, name, city, grade, track, visibility_score) VALUES (?, ?, ?, ?, ?, ?)",
            ('token_demo_aktobe_402', 'Ученик #402', 'Актобе', '11 класс', 'IT / Python', 88),
        )
        student_id = cur.lastrowid
        cur.execute(
            "INSERT INTO certificates (student_id, title, org, date, status, score_boost, review_note) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (student_id, 'Победитель областной олимпиады по Python', 'Актобе IT-школа / 1 место', '12.11.2026', 'verified', 15, 'Демо-грамота, уже подтверждена'),
        )
        cur.execute(
            "INSERT INTO certificates (student_id, title, org, date, status, score_boost, review_note) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (student_id, 'Участник хакатона "Gambit regional"', 'Gambit / Участник', '05.11.2026', 'verified', 10, 'Демо-грамота, уже подтверждена'),
        )
        cur.executemany(
            "INSERT INTO activities (title, type, date, bonus, region, track) VALUES (?, ?, ?, ?, ?, ?)",
            [
                ('Областная олимпиада по программированию (Актобе)', 'Олимпиада', '20 ноября', '+30% к видимости', 'Актобе', 'IT / Python'),
                ('Gambit Regional Hackathon', 'Хакатон', '15–17 ноября', '+25% к видимости', 'Онлайн / Актобе', 'IT / Python'),
                ('STEM-квест "Наука в Актобе"', 'Конкурс', '28 ноября', '+15% к видимости', 'Актобе', 'Естественные науки (Био/Хим/Физ)'),
            ],
        )
        cur.executemany(
            "INSERT INTO offers (student_id, university, title, message, status, region) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (student_id, 'Astana IT University (Квота регионов)', 'Приглашение на грант 50% (Software Engineering)', 'Ваш профиль из Актобе замечен приемной комиссией!', 'accepted', 'Астана'),
                (student_id, 'КазНУ им. Аль-Фараби (Кампус Актобе)', 'Скидка 30% на факультет Informatics', 'На основании ваших достижений по математике и программированию.', 'pending', 'Актобе'),
            ],
        )
        cur.executemany(
            "INSERT INTO candidates (name, city, grade, track, score, achievement, offer_sent) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ('Ученик #402', 'Актобе', '11 класс', 'IT / Python', 88, '1 место Regional Hackathon Aktobe, 15 репозиториев на GitHub.', 0),
                ('Ученик #305', 'Актобе', '11 класс', 'Математика / Алгоритмы', 92, 'Победитель Республиканской олимпиады по математике.', 0),
                ('Ученик #108', 'Семей', '10 класс', 'Естественные науки (Био/Хим/Физ)', 78, 'Финалист Republican Biology Olympiad.', 0),
                ('Ученик #212', 'Актобе', '11 класс', 'Дизайн / Арт / Творчество', 84, 'Победитель областного конкурса digital-арта.', 0),
            ],
        )

    if cur.execute('SELECT COUNT(*) FROM activities').fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO activities (title, type, date, bonus, region, track) VALUES (?, ?, ?, ?, ?, ?)",
            [
                ('Областная олимпиада по программированию (Актобе)', 'Олимпиада', '20 ноября', '+30% к видимости', 'Актобе', 'IT / Python'),
                ('Gambit Regional Hackathon', 'Хакатон', '15–17 ноября', '+25% к видимости', 'Онлайн / Актобе', 'IT / Python'),
                ('STEM-квест "Наука в Актобе"', 'Конкурс', '28 ноября', '+15% к видимости', 'Актобе', 'Естественные науки (Био/Хим/Физ)'),
            ],
        )

    _sync_candidates_into_students(cur)
    _seed_demo_accounts(cur)
    conn.commit()
    conn.close()


def _sync_candidates_into_students(cur):
    rows = cur.execute('SELECT name, city, grade, track, score, achievement FROM candidates').fetchall()
    for name, city, grade, track, score, achievement in rows:
        found = cur.execute('SELECT id FROM students WHERE name = ?', (name,)).fetchone()
        if found:
            continue
        cur.execute(
            'INSERT INTO students (token, name, city, grade, track, visibility_score) VALUES (NULL, ?, ?, ?, ?, ?)',
            (name, city, grade, track, score),
        )
        cur.execute(
            "INSERT INTO certificates (student_id, title, org, date, status, score_boost, review_note) VALUES (?, ?, ?, ?, 'verified', 0, ?)",
            (cur.lastrowid, achievement, 'Архив достижений', '12.11.2026', 'Подтверждено при загрузке/demo-базы'),
        )


def _seed_demo_accounts(cur):
    student = cur.execute('SELECT id FROM students WHERE name = ?', ('Ученик #402',)).fetchone()
    if student and not cur.execute('SELECT id FROM users WHERE email = ?', (DEMO_STUDENT_EMAIL,)).fetchone():
        token = 'token_' + uuid.uuid4().hex[:16]
        cur.execute(
            'INSERT INTO users (email, password_hash, role, token, name) VALUES (?, ?, ?, ?, ?)',
            (DEMO_STUDENT_EMAIL, generate_password_hash(DEMO_STUDENT_PASSWORD), 'student', token, 'Ученик #402'),
        )
        user_id = cur.lastrowid
        cur.execute('UPDATE students SET user_id = ?, token = ? WHERE id = ?', (user_id, token, student['id']))

    if not cur.execute('SELECT id FROM users WHERE email = ?', (DEMO_UNI_EMAIL,)).fetchone():
        token = 'token_' + uuid.uuid4().hex[:16]
        cur.execute(
            'INSERT INTO users (email, password_hash, role, token, name) VALUES (?, ?, ?, ?, ?)',
            (DEMO_UNI_EMAIL, generate_password_hash(DEMO_UNI_PASSWORD), 'university', token, 'Astana IT University'),
        )
        cur.execute(
            'INSERT INTO universities (user_id, name, city) VALUES (?, ?, ?)',
            (cur.lastrowid, 'Astana IT University', 'Астана'),
        )


def _user_dict(row):
    if not row:
        return None
    data = dict(row)
    data.pop('password_hash', None)
    return data


def get_user_by_token(token):
    conn = get_db()
    row = conn.execute('SELECT * FROM users WHERE token = ?', (token,)).fetchone()
    conn.close()
    return _user_dict(row)


def get_user_by_email(email):
    conn = get_db()
    row = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    conn.close()
    return dict(row) if row else None


def register_user(email, password, role, name, city, grade, track):
    email = (email or '').strip().lower()
    name = (name or '').strip()
    if not email or '@' not in email:
        raise ValueError('Укажите почту')
    if not password or len(password) < 4:
        raise ValueError('Пароль должен быть не короче 4 символов')
    if role not in ('student', 'university'):
        raise ValueError('Выберите роль: школьник или вуз')
    if not name:
        raise ValueError('Укажите имя или название вуза')

    token = 'token_' + uuid.uuid4().hex[:16]
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            'INSERT INTO users (email, password_hash, role, token, name) VALUES (?, ?, ?, ?, ?)',
            (email, generate_password_hash(password), role, token, name[:100]),
        )
    except sqlite3.IntegrityError:
        conn.close()
        raise ValueError('Такая почта уже зарегистрирована')
    user_id = cur.lastrowid

    if role == 'student':
        grade_text = grade if isinstance(grade, str) and 'класс' in str(grade) else f'{grade or 10} класс'
        cur.execute(
            'INSERT INTO students (token, user_id, name, city, grade, track, visibility_score) VALUES (?, ?, ?, ?, ?, ?, 15)',
            (token, user_id, name[:100], (city or 'Актобе')[:60], grade_text, (track or 'IT / Python')[:100]),
        )
    else:
        cur.execute(
            'INSERT INTO universities (user_id, name, city) VALUES (?, ?, ?)',
            (user_id, name[:100], (city or 'Астана')[:60]),
        )
    conn.commit()
    conn.close()
    return session_for_token(token)


def login_user(email, password):
    user = get_user_by_email((email or '').strip().lower())
    if not user or not check_password_hash(user['password_hash'], password or ''):
        return None
    return session_for_token(user['token'])


def session_for_token(token):
    user = get_user_by_token(token)
    if not user:
        return None
    if user['role'] == 'student':
        profile = get_student_by_user_id(user['id'])
    else:
        profile = get_university_by_user_id(user['id'])
    if profile:
        profile['email'] = user['email']
    return {'token': token, 'role': user['role'], 'profile': profile}


def get_student_by_user_id(user_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM students WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_student_by_token(token):
    conn = get_db()
    row = conn.execute('SELECT * FROM students WHERE token = ?', (token,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_university_by_user_id(user_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM universities WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_student_profile(user_id, data):
    grade = data.get('grade') or '10'
    grade_text = grade if isinstance(grade, str) and 'класс' in str(grade) else f'{grade} класс'
    conn = get_db()
    conn.execute(
        'UPDATE students SET name = ?, city = ?, grade = ?, track = ? WHERE user_id = ?',
        (str(data.get('name') or 'Ученик')[:100], str(data.get('city') or 'Актобе')[:60], grade_text, str(data.get('track') or 'IT / Python')[:100], user_id),
    )
    conn.execute('UPDATE users SET name = ? WHERE id = ?', (str(data.get('name') or 'Ученик')[:100], user_id))
    conn.commit()
    conn.close()
    return get_student_by_user_id(user_id)


def _with_image(cert):
    data = dict(cert)
    if data.get('image_filename'):
        data['image'] = f"/uploads/{data['image_filename']}"
    raw = data.get('checks_json')
    data['checks'] = json.loads(raw) if raw else []
    data['reason'] = data.get('review_note') or ''
    return data


def add_certificate(student_id, title, org, date, image_filename):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO certificates (student_id, title, org, date, status, score_boost, image_filename) VALUES (?, ?, ?, ?, 'pending', 0, ?)",
        (student_id, title, org, date, image_filename),
    )
    cert_id = cur.lastrowid
    conn.commit()
    cert = cur.execute('SELECT * FROM certificates WHERE id = ?', (cert_id,)).fetchone()
    conn.close()
    return _with_image(cert)


def get_student_certificates(student_id):
    conn = get_db()
    rows = conn.execute('SELECT * FROM certificates WHERE student_id = ? ORDER BY id DESC', (student_id,)).fetchall()
    conn.close()
    return [_with_image(row) for row in rows]


def inspect_certificate_image(filename):
    checks = []
    if not filename:
        checks.append({'name': 'Фото', 'ok': False, 'detail': 'Файл не приложен'})
        return {'ok': False, 'reason': 'Без фото грамоту проверить нельзя. Загрузите скан.', 'checks': checks, 'boost': 0}

    path = os.path.join(UPLOADS, os.path.basename(filename))
    if not os.path.isfile(path):
        checks.append({'name': 'Фото', 'ok': False, 'detail': 'Файл не найден на сервере'})
        return {'ok': False, 'reason': 'Файл грамоты не сохранился. Загрузите ещё раз.', 'checks': checks, 'boost': 0}

    try:
        image = ImageOps.exif_transpose(Image.open(path))
        image.load()
    except Exception:
        checks.append({'name': 'Файл', 'ok': False, 'detail': 'Это не изображение'})
        return {'ok': False, 'reason': 'Файл повреждён или это не картинка.', 'checks': checks, 'boost': 0}

    width, height = image.size
    size_ok = min(width, height) >= 320 and max(width, height) >= 480
    checks.append({
        'name': 'Размер скана',
        'ok': size_ok,
        'detail': f'{width}×{height} px' if size_ok else f'{width}×{height} px — слишком мелко, снимите бланк целиком',
    })

    preview = image.convert('RGB')
    preview.thumbnail((900, 900))
    gray = preview.convert('L')
    std = ImageStat.Stat(gray).stddev[0]
    contrast_ok = std >= 15
    checks.append({
        'name': 'Контраст',
        'ok': contrast_ok,
        'detail': 'на фото есть и свет, и тёмные штрихи' if contrast_ok else 'снимок почти однотонный, текст не виден',
    })

    pixels = list(gray.get_flattened_data()) if hasattr(gray, 'get_flattened_data') else list(gray.getdata())
    light_ratio = sum(1 for value in pixels if value >= 160) / max(len(pixels), 1)
    paper_ok = light_ratio >= 0.35
    checks.append({
        'name': 'Бланк',
        'ok': paper_ok,
        'detail': f'светлая бумага занимает {round(light_ratio * 100)}% кадра' if paper_ok else 'мало светлой бумаги — это не похоже на грамоту',
    })

    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_mean = ImageStat.Stat(edges).mean[0]
    columns, rows = 8, 8
    tile_w, tile_h = max(edges.size[0] // columns, 1), max(edges.size[1] // rows, 1)
    occupied = 0
    for row in range(rows):
        for col in range(columns):
            tile = edges.crop((col * tile_w, row * tile_h, (col + 1) * tile_w, (row + 1) * tile_h))
            if ImageStat.Stat(tile).mean[0] >= 6:
                occupied += 1
    spread_ok = occupied >= 28 and edge_mean >= 7
    checks.append({
        'name': 'Текст и рамка',
        'ok': spread_ok,
        'detail': f'линии и буквы на {occupied} из 64 участков' if spread_ok else 'мало текста по листу — загрузите саму грамоту, а не пустое фото',
    })

    ok = all(item['ok'] for item in checks)
    if not ok:
        failed = next(item for item in checks if not item['ok'])
        return {'ok': False, 'reason': 'Грамота не подтверждена. ' + failed['detail'], 'checks': checks, 'boost': 0}

    boost = 12 if edge_mean >= 11 and min(width, height) >= 600 else 7
    return {
        'ok': True,
        'reason': 'Грамота подтверждена: на фото читаемый бланк с рамкой и текстом.',
        'checks': checks,
        'boost': boost,
    }


def verify_certificate(cert_id, student_id):
    conn = get_db()
    cur = conn.cursor()
    cert = cur.execute(
        'SELECT * FROM certificates WHERE id = ? AND student_id = ?',
        (cert_id, student_id),
    ).fetchone()
    if not cert:
        conn.close()
        return None

    student = cur.execute('SELECT visibility_score FROM students WHERE id = ?', (student_id,)).fetchone()
    if cert['status'] == 'verified':
        conn.close()
        payload = _with_image(cert)
        payload['already'] = True
        payload['visibility_score'] = student['visibility_score']
        return payload

    review = inspect_certificate_image(cert['image_filename'])
    status = 'verified' if review['ok'] else 'rejected'
    cur.execute(
        'UPDATE certificates SET status = ?, score_boost = ?, review_note = ?, checks_json = ? WHERE id = ?',
        (status, review['boost'], review['reason'], json.dumps(review['checks'], ensure_ascii=False), cert_id),
    )
    visibility = student['visibility_score'] or 0
    if review['ok']:
        visibility = min(100, visibility + review['boost'])
        cur.execute('UPDATE students SET visibility_score = ? WHERE id = ?', (visibility, student_id))
    conn.commit()
    updated = cur.execute('SELECT * FROM certificates WHERE id = ?', (cert_id,)).fetchone()
    conn.close()
    payload = _with_image(updated)
    payload['already'] = False
    payload['visibility_score'] = visibility
    return payload


def get_recommended_activities(student_id, city, track, type_filter=None):
    conn = get_db()
    query = 'SELECT * FROM activities WHERE 1=1'
    params = []
    if city and city != 'Все':
        query += ' AND (region LIKE ? OR region = ? OR region LIKE ?)'
        params.extend([f'%{city}%', city, '%Онлайн%'])
    if track and track != 'Все':
        query += ' AND (track = ? OR track LIKE ?)'
        params.extend([track, f'%{track.split("/")[0].strip()}%'])
    if type_filter and type_filter != 'Все':
        query += ' AND type = ?'
        params.append(type_filter)
    rows = conn.execute(query, params).fetchall()
    joined = {
        row['activity_id']
        for row in conn.execute('SELECT activity_id FROM activity_joins WHERE student_id = ?', (student_id,))
    }
    conn.close()
    result = []
    for row in rows:
        item = dict(row)
        item['joined'] = item['id'] in joined
        result.append(item)
    return result


def join_activity(activity_id, student_id):
    conn = get_db()
    cur = conn.cursor()
    found = cur.execute('SELECT id FROM activities WHERE id = ?', (activity_id,)).fetchone()
    if not found:
        conn.close()
        return None
    cur.execute('INSERT OR IGNORE INTO activity_joins (student_id, activity_id) VALUES (?, ?)', (student_id, activity_id))
    conn.commit()
    conn.close()
    return 'joined'


def get_student_offers(student_id):
    conn = get_db()
    rows = conn.execute('SELECT * FROM offers WHERE student_id = ? ORDER BY id DESC', (student_id,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def accept_offer(offer_id, student_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE offers SET status = 'accepted' WHERE id = ? AND student_id = ?",
        (offer_id, student_id),
    )
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


def get_radar_candidates(city, track, min_score, university_name=None):
    conn = get_db()
    query = 'SELECT * FROM students WHERE visibility_score >= ?'
    params = [min_score or 0]
    if city and city != 'Все':
        query += ' AND city = ?'
        params.append(city)
    if track and track != 'Все':
        query += ' AND track = ?'
        params.append(track)
    query += ' ORDER BY visibility_score DESC'
    rows = conn.execute(query, params).fetchall()
    result = []
    for row in rows:
        achievement = conn.execute(
            "SELECT title FROM certificates WHERE student_id = ? AND status = 'verified' ORDER BY id DESC LIMIT 1",
            (row['id'],),
        ).fetchone()
        offer = None
        if university_name:
            offer = conn.execute(
                'SELECT id FROM offers WHERE student_id = ? AND university = ?',
                (row['id'], university_name),
            ).fetchone()
        result.append({
            'id': row['id'],
            'name': f"Ученик #{row['id']}",
            'city': row['city'],
            'grade': row['grade'],
            'track': row['track'],
            'score': row['visibility_score'],
            'achievement': achievement['title'] if achievement else 'Подтверждённых грамот пока нет',
            'offer_sent': 1 if offer else 0,
        })
    conn.close()
    return result


def send_offer_to_candidate(student_id, university, title, message):
    conn = get_db()
    cur = conn.cursor()
    student = cur.execute('SELECT id, city FROM students WHERE id = ?', (student_id,)).fetchone()
    if not student:
        conn.close()
        return None
    existing = cur.execute(
        'SELECT id FROM offers WHERE student_id = ? AND university = ? AND title = ?',
        (student_id, university, title),
    ).fetchone()
    if not existing:
        cur.execute(
            "INSERT INTO offers (student_id, university, title, message, status, region) VALUES (?, ?, ?, ?, 'pending', ?)",
            (student_id, university, title, message, student['city']),
        )
    conn.commit()
    conn.close()
    return {'status': 'sent', 'candidate_id': student_id}


# =========================================================================
# РЕАЛЬНЫЙ ПОИСК (Google, Devpost, Stepik) И ИИ-КОНСУЛЬТАНТ
# =========================================================================

_TAG_RE = re.compile(r'<[^>]+>')
_IT_RE = re.compile(r'python|\bai\b|\bml\b|software|\bweb\b|data|cyber|code|coding|developer|machine learning|blockchain|\bapp\b', re.I)
_UA = {'User-Agent': 'Mozilla/5.0 (compatible; TalentRadarBot/1.0)'}


def _clean_text(value, limit=160):
    text = html.unescape(_TAG_RE.sub(' ', value or ''))
    text = ' '.join(text.split())
    return text[:limit] + ('…' if len(text) > limit else '')


def _http_get_json(url, params=None, headers=None, timeout=6):
    if requests is None:
        print('Модуль requests не установлен: pip install requests')
        return None
    try:
        resp = requests.get(url, params=params, headers=headers or _UA, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
        print(f'HTTP {resp.status_code} от {url}')
    except Exception as exc:
        print(f'Ошибка запроса к {url}: {exc}')
    return None


def _is_placeholder(value):
    return not value or str(value).startswith('YOUR_')


def _is_it_track(track):
    return 'IT' in (track or '') or 'Python' in (track or '')


def search_real_google(query, city=''):
    if _is_placeholder(GOOGLE_API_KEY) or _is_placeholder(GOOGLE_CSE_ID):
        print('GOOGLE_API_KEY / GOOGLE_CSE_ID не настроены, поиск Google пропущен.')
        return []

    search_query = ' '.join(p for p in [
        'олимпиада хакатон конкурс для школьников', query, city, f'Казахстан {datetime.now().year}',
    ] if p)
    data = _http_get_json(
        'https://www.googleapis.com/customsearch/v1',
        params={'key': GOOGLE_API_KEY, 'cx': GOOGLE_CSE_ID, 'q': search_query, 'num': 5},
        timeout=6,
    )
    results = []
    for item in (data or {}).get('items', []):
        results.append({
            'title': item.get('title'),
            'snippet': _clean_text(item.get('snippet')),
            'link': item.get('link'),
            'source': 'Google',
            'platform': 'Google Web',
            'city': city or 'Любой',
            'track': 'Общее',
            'type': 'Конкурс',
            'date': 'См. на сайте',
            'bonus': '+5%',
        })
    return results


def search_real_devpost(query=''):
    data = _http_get_json(
        DEVPOST_API_URL,
        params={'status[]': ['open', 'upcoming'], 'order_by': 'deadline'},
    )
    results = []
    for h in (data or {}).get('hackathons', []):
        title = h.get('title') or ''
        themes = ' '.join(t.get('name', '') for t in (h.get('themes') or []) if isinstance(t, dict))
        if query:
            if query.lower() not in title.lower():
                continue
        elif not _IT_RE.search(f'{title} {themes}'):
            continue
        prize = _clean_text(h.get('prize_amount'), 40) or 'смотри детали'
        results.append({
            'title': title,
            'snippet': f'Онлайн-хакатон. Призовой фонд: {prize}',
            'link': h.get('url') or f"https://devpost.com/{h.get('slug', '')}",
            'source': 'Devpost',
            'platform': 'Devpost',
            'date': h.get('submission_period_dates') or 'Скоро',
            'city': 'Онлайн',
            'track': 'IT / Python',
            'type': 'Хакатон',
            'bonus': '+30%',
        })
    return results[:4]


STEPIK_KEYWORDS = {
    'IT / Python': 'python программирование основы',
    'Математика / Алгоритмы': 'математика алгоритмы',
    'Естественные науки (Био/Хим/Физ)': 'биология химия физика',
    'Гуманитарные науки (История/Языки)': 'история язык английский',
    'Дизайн / Арт / Творчество': 'дизайн графика',
    'Бизнес / Экономика': 'бизнес экономика стартапы',
}


def search_real_stepik(track='', query=''):
    text = query or STEPIK_KEYWORDS.get(track, 'программирование')
    data = _http_get_json(STEPIK_API_URL, params={'query': text, 'page': 1, 'is_public': 'true'}, timeout=6)
    results = []
    for c in ((data or {}).get('courses') or [])[:3]:
        results.append({
            'title': c.get('title'),
            'snippet': _clean_text(c.get('summary') or c.get('description'), 120),
            'link': f"https://stepik.org/course/{c.get('id')}",
            'source': 'Stepik',
            'platform': 'Stepik',
            'date': 'Доступно постоянно',
            'city': 'Онлайн',
            'track': track,
            'type': 'Курс',
            'bonus': '+10%',
        })
    return results


def search_local_activities(city, track, query='', student_id=None):
    conn = get_db()
    try:
        sql = 'SELECT * FROM activities WHERE 1=1'
        params = []
        if city and city != 'Все':
            sql += ' AND (region LIKE ? OR region LIKE ?)'
            params.extend([f'%{city}%', '%Онлайн%'])
        if track and track != 'Все':
            sql += ' AND (track = ? OR track LIKE ?)'
            params.extend([track, f"%{track.split('/')[0].strip()}%"])
        rows = conn.execute(sql, params).fetchall()
        joined = set()
        if student_id:
            joined = {r['activity_id'] for r in conn.execute(
                'SELECT activity_id FROM activity_joins WHERE student_id = ?', (student_id,))}
    finally:
        conn.close()

    results = []
    for row in rows:
        if query and query.lower() not in (row['title'] or '').lower():
            continue
        results.append({
            'id': row['id'],
            'title': row['title'],
            'snippet': f"Региональное мероприятие. Формат: {row['type']}",
            'link': None,
            'source': 'Локальная база',
            'platform': 'Офлайн / Регион',
            'date': row['date'],
            'city': row['region'],
            'track': row['track'],
            'type': row['type'],
            'bonus': row['bonus'],
            'joined': row['id'] in joined,
        })
    return results


def aggregate_real_search(city, track, query='', student_id=None):
    city, track, query = city or '', track or '', (query or '').strip()[:100]
    print(f"--- Поиск: город={city}, трек={track}, запрос='{query}' ---")

    # внешние источники опрашиваем параллельно, чтобы не ждать их по очереди
    with ThreadPoolExecutor(max_workers=3) as pool:
        google = pool.submit(search_real_google, query, city)
        devpost = pool.submit(search_real_devpost, query) if _is_it_track(track) else None
        stepik = pool.submit(search_real_stepik, track, query)
        external = []
        for fut in (google, devpost, stepik):
            if fut is None:
                continue
            try:
                external.extend(fut.result())
            except Exception as exc:
                print(f'Ошибка источника: {exc}')

    local = search_local_activities(city, track, query, student_id)

    unique, seen = [], set()
    for res in local + external:
        title = (res.get('title') or '').strip().lower()
        if title and title not in seen:
            seen.add(title)
            unique.append(res)

    unique.sort(key=lambda x: (
        0 if x.get('source') == 'Локальная база' else 1,
        0 if city and city in (x.get('city') or '') else 1,
    ))
    return unique


def consult_ai(profile, user_query):
    city = profile.get('city') or 'Актобе'
    track = profile.get('track') or 'IT / Python'
    score = profile.get('visibility_score') or 0

    if not _is_placeholder(OPENAI_API_KEY):
        try:
            import openai
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            response = client.chat.completions.create(
                model='gpt-4o-mini',
                messages=[
                    {'role': 'system', 'content': (
                        f'Ты — карьерный наставник для школьников Казахстана. Школьник из города {city}, '
                        f'направление {track}, индекс видимости {score}/100. '
                        'Дай краткий конкретный совет на русском языке.')},
                    {'role': 'user', 'content': user_query},
                ],
            )
            return response.choices[0].message.content
        except Exception as exc:
            print(f'OpenAI API Error: {exc}')

    q = (user_query or '').lower()
    advice = f"Привет! Твой профиль: город {city}, направление «{track}», индекс видимости {score}/100. "

    if any(w in q for w in ('олимпиад', 'конкурс', 'мероприят', 'хакатон')):
        if score < 50:
            advice += (f'Индекс пока ниже среднего. Начни с региональных олимпиад в {city} — они быстрее всего '
                       'поднимают видимость и показывают вузам, что ты активен.')
        else:
            advice += (f'Ты уже на хорошем счету ({score}/100). Выходи на республиканский уровень: '
                       'хакатоны на Devpost и курсы на Stepik закрепят результат.')
    elif any(w in q for w in ('грант', 'стипенд', 'поступ')):
        advice += ('Гранты в вузах Казахстана чаще всего выдают за победы в олимпиадах и участие в хакатонах. '
                   'Загрузи фото грамот — сервер проверит их и добавит баллы к индексу.')
    elif any(w in q for w in ('поднять', 'видимост', 'индекс')):
        advice += (f'Чтобы поднять индекс с {score}%: 1) загрузи все имеющиеся грамоты; '
                   '2) пройди онлайн-курсы на Stepik; 3) поучаствуй в региональных хакатонах.')
    else:
        advice += ('Задай конкретный вопрос: «Какие олимпиады мне пройти?», «Как получить грант?» '
                   'или «Как поднять индекс видимости?» — и я дам пошаговый план.')
    return advice