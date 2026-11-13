# main.py
import os
import uuid
from datetime import datetime

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

import backend as be

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
ALLOWED_EXT = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

be.init_db()


def current_token():
    return (request.headers.get('Authorization') or '').replace('Bearer ', '', 1).strip()


def current_user():
    token = current_token()
    return be.get_user_by_token(token) if token else None


def current_student():
    user = current_user()
    if not user or user['role'] != 'student':
        return None
    return be.get_student_by_user_id(user['id'])


@app.errorhandler(413)
def too_large(_):
    return jsonify({'error': 'Файл больше 5 МБ'}), 413


@app.route('/api/health')
def health():
    return jsonify({'status': 'ok'})


@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    try:
        session = be.register_user(
            email=data.get('email'),
            password=data.get('password'),
            role=data.get('role'),
            name=data.get('name'),
            city=data.get('city'),
            grade=data.get('grade'),
            track=data.get('track'),
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify(session), 201


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    session = be.login_user(data.get('email'), data.get('password'))
    if not session:
        return jsonify({'error': 'Неверная почта или пароль'}), 401
    return jsonify(session)


@app.route('/api/auth/me')
def me():
    token = current_token()
    if not token:
        return jsonify({'error': 'Нужно войти'}), 401
    session = be.session_for_token(token)
    if not session:
        return jsonify({'error': 'Сессия не найдена'}), 401
    return jsonify(session)


@app.route('/api/profile', methods=['GET'])
def get_profile():
    student = current_student()
    if not student:
        return jsonify({'error': 'Войдите как школьник'}), 401
    student = dict(student)
    student['email'] = current_user()['email']
    return jsonify(student)


@app.route('/api/profile', methods=['POST'])
def update_profile():
    user = current_user()
    student = current_student()
    if not user or not student:
        return jsonify({'error': 'Войдите как школьник'}), 401
    data = request.get_json(silent=True) or {}
    profile = be.update_student_profile(user['id'], data)
    profile['email'] = user['email']
    return jsonify(profile)


@app.route('/api/certificates', methods=['GET'])
def get_certificates():
    student = current_student()
    if not student:
        return jsonify({'error': 'Войдите как школьник'}), 401
    return jsonify(be.get_student_certificates(student['id']))


@app.route('/api/certificates', methods=['POST'])
def add_certificate():
    student = current_student()
    if not student:
        return jsonify({'error': 'Войдите как школьник'}), 401

    image = request.files.get('cert-photo')
    if not image or not image.filename:
        return jsonify({'error': 'Приложите фото грамоты'}), 400
    ext = os.path.splitext(image.filename)[1].lower()
    if ext not in ALLOWED_EXT or not (image.mimetype or '').startswith('image/'):
        return jsonify({'error': 'Нужна картинка JPG, PNG, WEBP или GIF'}), 400
    image_filename = f'cert_{uuid.uuid4().hex}{ext}'
    image.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))

    cert = be.add_certificate(
        student_id=student['id'],
        title=(request.form.get('cert-title') or 'Достижение')[:200],
        org=(request.form.get('cert-org') or 'Организатор')[:200],
        date=request.form.get('cert-date') or datetime.now().strftime('%d.%m.%Y'),
        image_filename=image_filename,
    )
    reviewed = be.verify_certificate(cert['id'], student['id'])
    return jsonify(reviewed), 201


@app.route('/api/certificates/<int:cert_id>/verify', methods=['POST'])
def verify_certificate_route(cert_id):
    student = current_student()
    if not student:
        return jsonify({'error': 'Войдите как школьник'}), 401
    result = be.verify_certificate(cert_id, student['id'])
    if result is None:
        return jsonify({'error': 'Грамота не найдена'}), 404
    if result.get('already'):
        return jsonify(result), 200
    return jsonify(result)


@app.route('/api/activities', methods=['GET'])
def get_activities_route():
    student = current_student()
    if not student:
        return jsonify([])
    return jsonify(be.get_recommended_activities(
        student['id'], student['city'], student['track'], request.args.get('type'),
    ))


@app.route('/api/activities/<int:activity_id>/join', methods=['POST'])
def join_activity_route(activity_id):
    student = current_student()
    if not student:
        return jsonify({'error': 'Войдите как школьник'}), 401
    status = be.join_activity(activity_id, student['id'])
    if status is None:
        return jsonify({'error': 'Мероприятие не найдено'}), 404
    return jsonify({'status': status})


@app.route('/api/offers', methods=['GET'])
def get_offers_route():
    student = current_student()
    if not student:
        return jsonify([])
    return jsonify(be.get_student_offers(student['id']))


@app.route('/api/offers/<int:offer_id>/accept', methods=['POST'])
def accept_offer_route(offer_id):
    student = current_student()
    if not student:
        return jsonify({'error': 'Войдите как школьник'}), 401
    if not be.accept_offer(offer_id, student['id']):
        return jsonify({'error': 'Оффер не найден'}), 404
    return jsonify({'status': 'accepted'})


@app.route('/api/radar', methods=['GET'])
def get_radar_route():
    user = current_user()
    if not user or user['role'] != 'university':
        return jsonify({'error': 'Войдите как вуз'}), 403
    university = be.get_university_by_user_id(user['id'])
    try:
        min_score = int(request.args.get('min_score', 0))
    except ValueError:
        return jsonify({'error': 'min_score должен быть числом'}), 400
    return jsonify(be.get_radar_candidates(
        request.args.get('city', 'Все'),
        request.args.get('track', 'Все'),
        min_score,
        university['name'] if university else user['name'],
    ))


@app.route('/api/radar/<int:candidate_id>/offer', methods=['POST'])
def send_offer_route(candidate_id):
    user = current_user()
    if not user or user['role'] != 'university':
        return jsonify({'error': 'Войдите как вуз'}), 403
    university = be.get_university_by_user_id(user['id'])
    data = request.get_json(silent=True) or {}
    result = be.send_offer_to_candidate(
        candidate_id,
        university=university['name'] if university else data.get('university', 'Вуз'),
        title=data.get('title', 'Приглашение на грант'),
        message=data.get('message', 'Мы вас рекомендуем!'),
    )
    if result is None:
        return jsonify({'error': 'Абитуриент не найден'}), 404
    return jsonify(result)


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/')
def serve_frontend():
    return send_from_directory(BASE_DIR, 'index.html')


@app.route('/api/activities/search_real', methods=['GET'])
def search_real_activities_route():
    """Маршрут для реального поиска мероприятий в Google, Devpost, Stepik и локальной БД."""
    student = current_student()
    if not student:
        return jsonify({'error': 'Требуется доступ школьника'}), 401

    city = request.args.get('city', student['city'])
    track = request.args.get('track', student['track'])
    query = request.args.get('q', '')

    # Запускаем агрегацию реального поиска через backend.py
    results = be.aggregate_real_search(city, track, query, student['id'])
    return jsonify(results)


@app.route('/api/ai/consult', methods=['POST'])
def ai_consult_route():
    """Маршрут для общения с ИИ-консультантом (смена вкладки 'ИИ-Помощник')."""
    student = current_student()
    if not student:
        return jsonify({'error': 'Требуется доступ школьника'}), 401

    data = request.get_json(silent=True) or {}
    user_msg = str(data.get('message') or '').strip()[:1000]
    if not user_msg:
        return jsonify({'error': 'Напишите вопрос'}), 400

    advice = be.consult_ai(student, user_msg)
    return jsonify({'response': advice})


# Запуск сервера (в самом конце файла)
if __name__ == '__main__':
    print('TalentRadar: http://localhost:5000')
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=os.environ.get('FLASK_DEBUG') == '1')