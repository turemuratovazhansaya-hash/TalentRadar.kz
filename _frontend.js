        const state = {
            role: null,
            token: localStorage.getItem('talentradar_token') || null,
            apiOnline: false,
            currentStudentTab: 'overview',
            profile: { id: null, name: '', city: '', grade: '', track: '', visibilityScore: 0 },
            university: { name: '', city: '' },
            certificates: [],
            activities: [],
            offers: [],
            candidates: []
        };

        let API_BASE = '';
        async function detectApiBase() {
            if (window.API_BASE !== undefined) { API_BASE = window.API_BASE; return true; }
            for (const base of ['', 'http://localhost:5000']) {
                try {
                    const response = await fetch(base + '/api/health');
                    if (response.ok && (await response.json()).status === 'ok') { API_BASE = base; return true; }
                } catch (e) {}
            }
            return false;
        }
        const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
        const mediaUrl = path => !path || path.startsWith('http') || path.startsWith('data:') ? path : API_BASE + path;

        async function api(path, opts = {}) {
            const response = await fetch(API_BASE + path, {
                ...opts,
                headers: { ...(state.token ? { Authorization: 'Bearer ' + state.token } : {}), ...(opts.headers || {}) }
            });
            const data = await response.json().catch(() => null);
            if (!response.ok) {
                const error = new Error((data && data.error) || ('Ошибка ' + response.status));
                error.http = response.status;
                throw error;
            }
            return data;
        }
        const jsonOpts = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

        const CERT_LABEL = { pending: 'На проверке', verified: 'Подтверждено', rejected: 'Не подтверждено' };
        const normProfile = profile => ({
            id: profile.id,
            name: profile.name,
            city: profile.city,
            grade: profile.grade,
            track: profile.track,
            email: profile.email || '',
            visibilityScore: profile.visibility_score ?? 0
        });
        const normCert = cert => ({
            id: cert.id,
            title: cert.title,
            org: cert.org,
            date: cert.date,
            status: cert.status,
            reason: cert.reason || '',
            checks: cert.checks || [],
            scoreBoost: cert.score_boost || 0,
            image: cert.image ? mediaUrl(cert.image) : null
        });
        const normAct = activity => ({ id: activity.id, title: activity.title, type: activity.type, date: activity.date, bonus: activity.bonus, region: activity.region, joined: !!activity.joined });
        const normOffer = offer => ({ id: offer.id, university: offer.university, title: offer.title, message: offer.message, region: offer.region, accepted: offer.status === 'accepted' });
        const normCand = candidate => ({ id: candidate.id, name: candidate.name, city: candidate.city, grade: candidate.grade, track: candidate.track, score: candidate.score, achievement: candidate.achievement, offerSent: !!candidate.offer_sent });

        function logout(reload = true) {
            localStorage.removeItem('talentradar_token');
            state.token = null;
            state.role = null;
            if (reload) location.reload();
        }

        function setApiStatus(online) {
            state.apiOnline = online;
            const dot = document.getElementById('api-dot');
            const text = document.getElementById('api-status-text');
            const badge = document.getElementById('api-badge');
            if (!dot) return;
            dot.className = 'w-1.5 h-1.5 rounded-full ' + (online ? 'bg-emerald-500' : 'bg-amber-500');
            text.textContent = online ? 'База подключена' : 'Нет связи с сервером';
            badge.className = 'flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold border ' +
                (online ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-amber-50 text-amber-700 border-amber-200');
        }

        function showScreen(name) {
            document.getElementById('screen-auth').classList.toggle('hidden', name !== 'auth');
            document.getElementById('screen-student').classList.toggle('hidden', name !== 'student');
            document.getElementById('screen-b2b').classList.toggle('hidden', name !== 'university');
            document.getElementById('header-guest').classList.toggle('hidden', name !== 'auth');
            document.getElementById('header-user').classList.toggle('hidden', name === 'auth');
            const studentOnly = name === 'student';
            document.getElementById('btn-edit-profile').classList.toggle('hidden', !studentOnly);
            document.getElementById('btn-edit-profile-mobile').classList.toggle('hidden', !studentOnly);
        }

        function paintHeader() {
            const role = state.role === 'university' ? 'Вуз' : 'Школьник';
            document.getElementById('header-role').textContent = role;
            document.getElementById('header-user-name').textContent = state.role === 'university' ? state.university.name : state.profile.name;
        }

        async function enterSession(session) {
            state.token = session.token;
            state.role = session.role;
            localStorage.setItem('talentradar_token', state.token);
            if (session.role === 'student') {
                state.profile = normProfile(session.profile);
                showScreen('student');
                paintHeader();
                await Promise.all([fetchCertificates(), fetchActivities(), fetchOffers()]);
                renderAll();
            } else {
                state.university = session.profile || { name: 'Вуз', city: '' };
                showScreen('university');
                paintHeader();
                const title = document.querySelector('#screen-b2b h2');
                if (title) title.textContent = state.university.name + ' — радар абитуриентов';
                await loadCandidates();
                applyRadarFilters();
            }
        }

        async function fetchCertificates() { state.certificates = (await api('/api/certificates')).map(normCert); }
        async function fetchActivities() { state.activities = (await api('/api/activities')).map(normAct); }
        async function fetchOffers() { state.offers = (await api('/api/offers')).map(normOffer); }
        async function loadCandidates() {
            state.candidates = (await api('/api/radar?city=Все&min_score=0')).map(normCand);
        }

        document.addEventListener('DOMContentLoaded', async () => {
            setApiStatus(false);
            const online = await detectApiBase();
            setApiStatus(online);
            if (!online) {
                showScreen('auth');
                showToast('Сервер не запущен. В папке проекта выполните: python main.py', 'error');
                return;
            }
            if (state.token) {
                try {
                    await enterSession(await api('/api/auth/me'));
                    return;
                } catch (e) {
                    localStorage.removeItem('talentradar_token');
                    state.token = null;
                }
            }
            showScreen('auth');
        });

        function switchAuthTab(tab) {
            const login = document.getElementById('login-form');
            const signup = document.getElementById('signup-form');
            const loginBtn = document.getElementById('auth-tab-login');
            const signupBtn = document.getElementById('auth-tab-signup');
            const showLogin = tab === 'login';
            login.classList.toggle('hidden', !showLogin);
            signup.classList.toggle('hidden', showLogin);
            loginBtn.className = (showLogin ? 'tab-active' : 'tab-inactive') + ' flex-1 py-2 rounded-lg text-sm font-bold';
            signupBtn.className = (!showLogin ? 'tab-active' : 'tab-inactive') + ' flex-1 py-2 rounded-lg text-sm font-bold';
        }

        document.querySelectorAll('input[name="signup-role"]').forEach(input => {
            input.addEventListener('change', () => {
                const role = document.querySelector('input[name="signup-role"]:checked').value;
                document.getElementById('signup-student-fields').classList.toggle('hidden', role !== 'student');
                document.getElementById('signup-name-label').textContent = role === 'student' ? 'Имя' : 'Название вуза';
                document.getElementById('signup-name').placeholder = role === 'student' ? 'Алихан С.' : 'Astana IT University';
            });
        });

        document.getElementById('login-form').addEventListener('submit', async event => {
            event.preventDefault();
            try {
                const session = await api('/api/auth/login', jsonOpts('POST', {
                    email: document.getElementById('login-email').value.trim(),
                    password: document.getElementById('login-password').value
                }));
                await enterSession(session);
                showToast(session.role === 'university' ? 'Открыт кабинет вуза' : 'Открыт кабинет школьника', 'success');
            } catch (error) {
                showToast(error.message, 'error');
            }
        });

        document.getElementById('signup-form').addEventListener('submit', async event => {
            event.preventDefault();
            const role = document.querySelector('input[name="signup-role"]:checked').value;
            try {
                const session = await api('/api/auth/register', jsonOpts('POST', {
                    role,
                    name: document.getElementById('signup-name').value.trim(),
                    email: document.getElementById('signup-email').value.trim(),
                    password: document.getElementById('signup-password').value,
                    city: document.getElementById('signup-city').value,
                    grade: document.getElementById('signup-grade').value,
                    track: document.getElementById('signup-track').value
                }));
                await enterSession(session);
                showToast('Аккаунт создан и сохранён в базе', 'success');
            } catch (error) {
                showToast(error.message, 'error');
            }
        });

        function switchStudentTab(tab) {
            state.currentStudentTab = tab;
            ['overview', 'verification', 'activities', 'offers'].forEach(name => {
                const button = document.getElementById('tab-' + name);
                const content = document.getElementById('content-' + name);
                const active = name === tab;
                button.classList.toggle('tab-active', active);
                button.classList.toggle('tab-inactive', !active);
                content.classList.toggle('hidden', !active);
            });
            if (tab === 'verification') renderCertificates();
            if (tab === 'activities') renderActivities();
            if (tab === 'offers') renderOffers();
        }

        function renderAll() {
            const profile = state.profile;
            document.getElementById('student-city').textContent = 'г. ' + String(profile.city || '—').replace(/^г\.\s*/, '');
            document.getElementById('student-grade').textContent = profile.grade || '—';
            document.getElementById('student-track').textContent = profile.track || '—';
            document.getElementById('profile-name').textContent = profile.name || 'Профиль';
            document.getElementById('profile-avatar').textContent = (String(profile.name || '?').match(/#\d+/) || [String(profile.name || '?').charAt(0).toUpperCase()])[0];
            const score = Math.max(0, Math.min(100, Number(profile.visibilityScore) || 0));
            document.getElementById('visibility-score').textContent = score + '%';
            document.getElementById('visibility-bar').style.width = score + '%';
            switchStudentTab(state.currentStudentTab);
        }

        function renderCertificates() {
            const container = document.getElementById('certificates-container');
            if (!state.certificates.length) {
                container.innerHTML = `
                    <div class="col-span-2 glass-card rounded-2xl p-10 text-center border-dashed border-2 border-zinc-200">
                        <div class="text-4xl mb-2 opacity-30">📜</div>
                        <p class="text-zinc-400 text-sm font-medium">Грамот пока нет.</p>
                        <p class="text-xs text-zinc-400 mt-1">Загрузите фото — сервер проверит бланк, а не просто поставит галочку.</p>
                    </div>`;
                return;
            }
            container.innerHTML = state.certificates.map(cert => {
                const verified = cert.status === 'verified';
                const rejected = cert.status === 'rejected';
                const badge = verified
                    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                    : rejected ? 'bg-red-50 text-red-700 border-red-200' : 'bg-amber-50 text-amber-700 border-amber-200';
                const checks = (cert.checks || []).map(check =>
                    `<li class="text-[11px] ${check.ok ? 'text-emerald-700' : 'text-red-600'}">${check.ok ? '✓' : '✕'} ${esc(check.name)}: ${esc(check.detail)}</li>`
                ).join('');
                return `
                    <div class="glass-card rounded-2xl p-5 flex flex-col card-enter border-l-4 ${verified ? 'border-l-emerald-500' : rejected ? 'border-l-red-400' : 'border-l-amber-400'}">
                        <div class="flex justify-between items-start mb-3 gap-2">
                            <span class="text-[10px] font-bold uppercase tracking-wider text-zinc-400">${esc(cert.org)}</span>
                            <span class="px-2 py-0.5 rounded-md text-[10px] font-bold border ${badge}">${esc(CERT_LABEL[cert.status] || cert.status)}</span>
                        </div>
                        <h3 class="text-sm font-bold text-zinc-900 mb-3">${esc(cert.title)}</h3>
                        ${cert.image
                            ? `<div class="mb-3 rounded-lg overflow-hidden border border-zinc-200 bg-zinc-50"><img src="${esc(cert.image)}" class="w-full h-36 object-contain bg-white" alt="Грамота"></div>`
                            : `<div class="mb-3 h-24 bg-zinc-50 rounded-lg border border-dashed border-zinc-200 flex items-center justify-center text-zinc-300 text-[10px]">Нет фото</div>`}
                        ${cert.reason ? `<p class="text-xs text-zinc-600 mb-2">${esc(cert.reason)}</p>` : ''}
                        ${checks ? `<ul class="space-y-1 mb-3">${checks}</ul>` : ''}
                        <div class="flex items-center justify-between mt-auto pt-3 border-t border-zinc-100">
                            <span class="text-[10px] text-zinc-500">📅 ${esc(cert.date)}</span>
                            ${verified
                                ? `<span class="text-[10px] font-bold text-emerald-600">+${cert.scoreBoost} к индексу</span>`
                                : `<button onclick="verifyCertificate('${cert.id}')" class="text-[10px] font-bold text-purple-600 hover:underline">Проверить фото снова</button>`}
                        </div>
                    </div>`;
            }).join('');
        }

        async function submitCertificate() {
            const title = document.getElementById('cert-title').value.trim();
            const org = document.getElementById('cert-org').value.trim();
            const rawDate = document.getElementById('cert-date').value;
            const file = document.getElementById('cert-photo').files[0];
            const date = rawDate ? rawDate.split('-').reverse().join('.') : new Date().toLocaleDateString('ru-RU');
            if (!title || !org) { showToast('Заполните название и организатора', 'error'); return; }
            if (!file) { showToast('Нужно фото грамоты — без него проверять нечего', 'error'); return; }
            try {
                const form = new FormData();
                form.append('cert-title', title);
                form.append('cert-org', org);
                form.append('cert-date', date);
                form.append('cert-photo', file);
                const result = normCert(await api('/api/certificates', { method: 'POST', body: form }));
                if (result.visibility_score !== undefined) state.profile.visibilityScore = result.visibility_score;
                const fresh = await api('/api/profile');
                state.profile = normProfile(fresh);
                state.certificates.unshift(result);
                closeCertModal();
                switchStudentTab('verification');
                renderAll();
                showToast(result.reason || (result.status === 'verified' ? 'Грамота подтверждена' : 'Грамота не прошла проверку'), result.status === 'verified' ? 'success' : 'error');
            } catch (error) {
                showToast(error.message, 'error');
            }
        }

        function handleImagePreview() {
            const input = document.getElementById('cert-photo');
            const preview = document.getElementById('image-preview');
            const file = input.files && input.files[0];
            if (!file) return;
            if (file.size > 5 * 1024 * 1024) {
                input.value = '';
                showToast('Файл больше 5 МБ', 'error');
                return;
            }
            const reader = new FileReader();
            reader.onload = event => {
                preview.src = event.target.result;
                preview.classList.remove('hidden');
                document.getElementById('dropzone-content').classList.add('hidden');
            };
            reader.readAsDataURL(file);
        }

        function openFilePicker(event) {
            if (event.target.id !== 'cert-photo') document.getElementById('cert-photo').click();
        }

        async function verifyCertificate(certId) {
            const cert = state.certificates.find(item => String(item.id) === String(certId));
            if (!cert) return;
            try {
                const result = normCert(await api('/api/certificates/' + cert.id + '/verify', { method: 'POST' }));
                Object.assign(cert, result);
                const fresh = await api('/api/profile');
                state.profile = normProfile(fresh);
                renderAll();
                showToast(result.reason || 'Проверка завершена', result.status === 'verified' ? 'success' : 'error');
            } catch (error) {
                showToast(error.message, 'error');
            }
        }

        function renderActivities() {
            const container = document.getElementById('activities-container');
            if (!state.activities.length) {
                container.innerHTML = `<div class="glass-card rounded-2xl p-10 text-center border-dashed border-2 border-zinc-200 text-sm text-zinc-500">Для вашего города и направления мероприятий пока нет.</div>`;
                return;
            }
            container.innerHTML = state.activities.map(activity => `
                <div class="glass-card rounded-2xl p-5 flex flex-col justify-between border-t-4 border-t-purple-400">
                    <div class="space-y-3">
                        <div class="flex items-center gap-2 flex-wrap">
                            <span class="px-2 py-0.5 rounded-md text-[10px] font-bold bg-purple-50 text-purple-700 border border-purple-200 uppercase">${esc(activity.type)}</span>
                            <span class="text-[10px] text-zinc-500">📍 ${esc(activity.region)} • 📅 ${esc(activity.date)}</span>
                        </div>
                        <h3 class="text-base font-bold text-zinc-900">${esc(activity.title)}</h3>
                        <span class="text-[10px] font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">${esc(activity.bonus)}</span>
                    </div>
                    <div class="mt-4">
                        ${activity.joined
                            ? `<span class="inline-flex justify-center w-full text-xs font-bold text-emerald-700 bg-emerald-50 px-3 py-2 rounded-lg border border-emerald-200">Заявка отправлена</span>`
                            : `<button onclick="joinActivity('${activity.id}')" class="w-full py-2 rounded-lg bg-zinc-950 text-white text-xs font-bold">Участвовать</button>`}
                    </div>
                </div>`).join('');
        }

        async function joinActivity(activityId) {
            const activity = state.activities.find(item => String(item.id) === String(activityId));
            if (!activity || activity.joined) return;
            try {
                await api('/api/activities/' + activity.id + '/join', { method: 'POST' });
                activity.joined = true;
                renderActivities();
                showToast('Заявка сохранена в базе', 'success');
            } catch (error) {
                showToast(error.message, 'error');
            }
        }

        function renderOffers() {
            const container = document.getElementById('offers-container');
            if (!state.offers.length) {
                container.innerHTML = `<div class="glass-card rounded-2xl p-10 text-center border-dashed border-2 border-zinc-200 text-sm text-zinc-500">Офферов пока нет.</div>`;
                return;
            }
            container.innerHTML = state.offers.map(offer => `
                <div class="glass-card rounded-2xl p-6 flex flex-col md:flex-row md:items-center justify-between gap-6 border-l-4 border-l-pink-500">
                    <div class="space-y-2">
                        <span class="px-2.5 py-0.5 rounded-md text-xs font-bold bg-pink-50 text-pink-700 border border-pink-200">🏛 ${esc(offer.university)}</span>
                        <h3 class="text-lg font-extrabold text-zinc-900">${esc(offer.title)}</h3>
                        <p class="text-sm text-zinc-600">${esc(offer.message)}</p>
                    </div>
                    ${offer.accepted
                        ? `<div class="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm font-bold text-center">Принято. Контакты переданы вузу.</div>`
                        : `<button onclick="acceptOffer('${offer.id}')" class="px-6 py-3 rounded-xl bg-gradient-to-r from-pink-500 to-purple-600 text-white text-sm font-bold">Принять оффер</button>`}
                </div>`).join('');
        }

        async function acceptOffer(offerId) {
            const offer = state.offers.find(item => String(item.id) === String(offerId));
            if (!offer) return;
            try {
                await api('/api/offers/' + offer.id + '/accept', { method: 'POST' });
                offer.accepted = true;
                renderOffers();
                showToast('Оффер принят', 'success');
            } catch (error) {
                showToast(error.message, 'error');
            }
        }

        function applyRadarFilters() {
            const cityFilter = document.getElementById('filter-city').value;
            const trackFilter = document.getElementById('filter-track').value;
            const scoreFilter = parseInt(document.getElementById('filter-score').value, 10) || 0;
            const filtered = state.candidates.filter(candidate =>
                (cityFilter === 'Все' || candidate.city === cityFilter) &&
                (trackFilter === 'Все' || candidate.track === trackFilter) &&
                candidate.score >= scoreFilter
            );
            document.getElementById('candidates-count').textContent = 'Найдено: ' + filtered.length;
            const container = document.getElementById('candidates-container');
            if (!filtered.length) {
                container.innerHTML = `<div class="col-span-2 glass-card rounded-2xl p-10 text-center text-sm text-zinc-500">Никого не нашли. Сбросьте фильтры.</div>`;
                return;
            }
            container.innerHTML = filtered.map(candidate => `
                <div class="glass-card rounded-2xl p-6 flex flex-col justify-between border-t-4 border-t-purple-400">
                    <div class="space-y-4">
                        <div class="flex items-start justify-between gap-3">
                            <div>
                                <h3 class="text-sm font-bold text-zinc-900">${esc(candidate.name)}</h3>
                                <p class="text-[11px] text-zinc-500">📍 ${esc(candidate.city)} • ${esc(candidate.grade)}</p>
                            </div>
                            <div class="text-right">
                                <div class="text-lg font-extrabold gradient-text">${candidate.score}%</div>
                                <div class="text-[9px] font-bold uppercase text-zinc-400">Индекс</div>
                            </div>
                        </div>
                        <span class="inline-block px-2 py-0.5 rounded-md text-[10px] font-semibold bg-purple-50 text-purple-700 border border-purple-100">${esc(candidate.track)}</span>
                        <p class="text-xs text-zinc-600">${esc(candidate.achievement)}</p>
                    </div>
                    <div class="mt-5 pt-4 border-t border-zinc-100">
                        ${candidate.offerSent
                            ? `<div class="py-2 rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-bold text-center">Оффер уже в кабинете школьника</div>`
                            : `<button onclick="sendOffer('${candidate.id}')" class="w-full py-2.5 rounded-lg bg-zinc-950 text-white text-xs font-bold">Отправить приглашение</button>`}
                    </div>
                </div>`).join('');
        }

        function resetFilters() {
            document.getElementById('filter-city').value = 'Все';
            document.getElementById('filter-track').value = 'Все';
            document.getElementById('filter-score').value = '0';
            applyRadarFilters();
        }

        async function sendOffer(candidateId) {
            const candidate = state.candidates.find(item => String(item.id) === String(candidateId));
            if (!candidate) return;
            try {
                await api('/api/radar/' + candidate.id + '/offer', jsonOpts('POST', {
                    title: 'Приглашение на грант',
                    message: 'Приёмная комиссия ' + (state.university.name || 'вуза') + ' приглашает вас. Направление: ' + candidate.track + '.'
                }));
                candidate.offerSent = true;
                applyRadarFilters();
                showToast('Приглашение записано школьнику ' + candidate.name, 'success');
            } catch (error) {
                showToast(error.message, 'error');
            }
        }

        function openEditModal() {
            const profile = state.profile;
            document.getElementById('reg-name').value = profile.name || '';
            document.getElementById('reg-city').value = String(profile.city || 'Актобе').replace(/^г\.\s*/, '');
            document.getElementById('reg-grade').value = parseInt(profile.grade, 10) || 11;
            document.getElementById('reg-track').value = profile.track || 'IT / Python';
            const modal = document.getElementById('register-modal');
            modal.classList.remove('hidden');
            modal.classList.add('flex');
        }
        function closeEditModal() {
            const modal = document.getElementById('register-modal');
            modal.classList.add('hidden');
            modal.classList.remove('flex');
        }
        function openRegisterModal() { openEditModal(); }
        function closeRegisterModal() { closeEditModal(); }

        document.getElementById('register-form').addEventListener('submit', async event => {
            event.preventDefault();
            try {
                const profile = await api('/api/profile', jsonOpts('POST', {
                    name: document.getElementById('reg-name').value.trim(),
                    city: document.getElementById('reg-city').value,
                    grade: document.getElementById('reg-grade').value,
                    track: document.getElementById('reg-track').value
                }));
                state.profile = normProfile(profile);
                paintHeader();
                await fetchActivities();
                closeEditModal();
                renderAll();
                showToast('Профиль обновлён в базе', 'success');
            } catch (error) {
                showToast(error.message, 'error');
            }
        });

        function openCertModal() {
            const modal = document.getElementById('cert-modal');
            modal.classList.remove('hidden');
            modal.classList.add('flex');
        }
        function closeCertModal() {
            const modal = document.getElementById('cert-modal');
            modal.classList.add('hidden');
            modal.classList.remove('flex');
            document.getElementById('cert-form').reset();
            const preview = document.getElementById('image-preview');
            preview.classList.add('hidden');
            preview.src = '';
            document.getElementById('dropzone-content').classList.remove('hidden');
        }
        document.getElementById('cert-form').addEventListener('submit', event => {
            event.preventDefault();
            submitCertificate();
        });

        function showToast(message, type = 'success') {
            const container = document.getElementById('toast-container');
            const toastId = 'toast-' + Date.now();
            const colors = {
                success: 'bg-white border-l-4 border-l-emerald-500',
                info: 'bg-white border-l-4 border-l-indigo-500',
                error: 'bg-white border-l-4 border-l-red-500'
            };
            const icons = { success: '✅', info: '💡', error: '⚠️' };
            const toast = document.createElement('div');
            toast.id = toastId;
            toast.className = 'toast-enter flex items-center gap-3 px-4 py-3.5 rounded-xl shadow-2xl border border-zinc-200 max-w-sm w-full pointer-events-auto ' + (colors[type] || colors.info);
            toast.innerHTML = `
                <div class="w-8 h-8 rounded-full bg-zinc-100 flex items-center justify-center text-sm">${icons[type] || icons.info}</div>
                <p class="flex-1 text-xs text-zinc-700">${esc(message)}</p>
                <button onclick="removeToast('${toastId}')" class="text-zinc-400">✕</button>`;
            container.appendChild(toast);
            setTimeout(() => removeToast(toastId), 4500);
        }
        function removeToast(toastId) {
            const toast = document.getElementById(toastId);
            if (!toast) return;
            toast.classList.add('toast-exit');
            setTimeout(() => toast.remove(), 300);
        }
