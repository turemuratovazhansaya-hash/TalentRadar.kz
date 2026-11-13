const API_BASE_URL = 'http://localhost:5000';

const state = {
  mode: 'student',
  token: localStorage.getItem('talentradar_token') || null,
  apiOnline: false,
  profile: {
    id: '#402',
    name: 'Ученик #402',
    city: 'Актобе',
    grade: '11 класс',
    track: 'IT / Python',
    visibilityScore: 85
  },
  activities: [],
  offers: [],
  candidates: []
};

// ==========================================
// ИНИЦИАЛИЗАЦИЯ И ПОЛУЧЕНИЕ ДАННЫХ С СЕРВЕРА
// ==========================================

async function initApp() {
  if (!state.token) {
    try {
      const res = await fetch(`${API_BASE_URL}/api/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: 'student', city: 'Актобе', track: 'IT / Python' })
      });
      if (res.ok) {
        const data = await res.json();
        state.token = data.token || `token_${Date.now()}`;
        localStorage.setItem('talentradar_token', state.token);
        setApiStatus(true);
      } else {
        throw new Error('Non-200 response');
      }
    } catch (err) {
      state.token = `token_demo_aktobe_402`;
      localStorage.setItem('talentradar_token', state.token);
      setApiStatus(false);
    }
  }

  const tokenDisplay = document.getElementById('session-token-display');
  if (tokenDisplay) tokenDisplay.textContent = state.token;

  await Promise.allSettled([
    fetchProfile(),
    fetchRealActivities(), // Грузим реальный поиск с сервера
    fetchOffers(),
    fetchRadar('Актобе', 15)
  ]);

  renderAll();
}

function setApiStatus(isOnline) {
  state.apiOnline = isOnline;
  const dot = document.getElementById('api-dot');
  const text = document.getElementById('api-status-text');
  const mobileBadge = document.getElementById('api-badge');

  if (dot && text) {
    dot.className = `w-2 h-2 rounded-full ${isOnline ? 'bg-emerald-500' : 'bg-amber-500'}`;
    text.textContent = isOnline ? 'Бэкенд подключен (localhost:5000)' : 'Автономный режим (Mock)';
  }
}

async function fetchProfile() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/profile`, {
      method: 'GET',
      headers: { 'Authorization': `Bearer ${state.token}` }
    });
    if (!res.ok) return;
    const data = await res.json();
    setApiStatus(true);
    if (data && data.name) {
      state.profile = { ...state.profile, ...data };
    }
  } catch (e) {}
}

// 🌐 РЕАЛЬНЫЙ ПОИСК АКТИВНОСТЕЙ (Google, Devpost, Stepik)
async function fetchRealActivities(searchQuery = '') {
  try {
    const city = state.profile.city || 'Актобе';
    const track = state.profile.track || 'IT / Python';
    
    const res = await fetch(`${API_BASE_URL}/api/activities/search_real?city=${encodeURIComponent(city)}&track=${encodeURIComponent(track)}&q=${encodeURIComponent(searchQuery)}`, {
      method: 'GET',
      headers: { 'Authorization': `Bearer ${state.token}` }
    });
    
    if (!res.ok) return;
    const data = await res.json();
    setApiStatus(true);
    if (Array.isArray(data)) {
      state.activities = data;
      renderStudentView();
    }
  } catch (e) {
    console.log('Используем локальные активности');
  }
}

async function fetchOffers() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/offers`, {
      method: 'GET',
      headers: { 'Authorization': `Bearer ${state.token}` }
    });
    if (!res.ok) return;
    const data = await res.json();
    setApiStatus(true);
    if (Array.isArray(data)) {
      state.offers = data;
    }
  } catch (e) {}
}

async function fetchRadar(city = 'Актобе', minScore = 15) {
  try {
    const query = new URLSearchParams({ city, min_score: minScore }).toString();
    const res = await fetch(`${API_BASE_URL}/api/radar?${query}`, {
      method: 'GET',
      headers: { 'Authorization': `Bearer ${state.token}` }
    });
    if (!res.ok) return;
    const data = await res.json();
    setApiStatus(true);
    if (Array.isArray(data)) {
      state.candidates = data;
    }
  } catch (e) {}
}

// ==========================================
// ОТРИСОВКА ИНТЕРФЕЙСА (RENDER)
// ==========================================

function renderAll() {
  if (state.mode === 'student') {
    renderStudentView();
  } else {
    applyRadarFilters();
  }
}

function renderStudentView() {
  const score = Math.min(100, state.profile.visibilityScore || 85);
  const scoreElem = document.getElementById('visibility-score');
  const barElem = document.getElementById('visibility-bar');
  const captionElem = document.getElementById('visibility-caption');

  if (scoreElem) scoreElem.textContent = `${score}%`;
  if (barElem) barElem.style.width = `${score}%`;
  if (captionElem) {
    captionElem.innerHTML = `Твой профиль виден <strong class="text-zinc-950">${score}% IT-вузов Казахстана</strong> (Астана, Алматы).`;
  }

  // Офферы
  const offersContainer = document.getElementById('offers-container');
  if (offersContainer) {
    offersContainer.innerHTML = state.offers.map(offer => `
      <div class="glass-card rounded-2xl p-6 border-l-4 border-l-indigo-600 mb-4">
        <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div class="space-y-1.5">
            <div class="flex flex-wrap items-center gap-2">
              <span class="px-2.5 py-0.5 rounded-md text-xs font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">
                🏛 ${offer.university}
              </span>
              <span class="text-xs font-medium text-zinc-500">Прямой оффер</span>
            </div>
            <h3 class="text-lg font-bold text-zinc-950">${offer.title}</h3>
            <p class="text-sm text-zinc-600">${offer.message}</p>
          </div>
          <div class="shrink-0">
            ${offer.accepted
              ? `<div class="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm font-semibold">
                   ✅ Контакты переданы вузу
                 </div>`
              : `<button onclick="acceptOffer('${offer.id}')" class="px-5 py-2.5 rounded-xl bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 transition">
                   Принять оффер
                 </button>`
            }
          </div>
        </div>
      </div>
    `).join('');
  }

  // Активности (Реальный поиск)
  const activitiesContainer = document.getElementById('activities-container');
  if (activitiesContainer) {
    if (!state.activities.length) {
      activitiesContainer.innerHTML = `<div class="p-8 text-center text-zinc-400">Идет реальный поиск мероприятий по Казахстану...</div>`;
    } else {
      activitiesContainer.innerHTML = state.activities.map(act => `
        <div class="glass-card rounded-2xl p-5 border-t-4 border-t-purple-400 mb-4 flex flex-col justify-between">
          <div class="space-y-2">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="px-2 py-0.5 rounded-md text-[10px] font-bold bg-purple-50 text-purple-700 border border-purple-200 uppercase">${act.type || 'Ивент'}</span>
              <span class="text-[10px] text-zinc-500">📍 ${act.city || 'Казахстан'} • 📅 ${act.date || 'Скоро'}</span>
            </div>
            <h3 class="text-base font-bold text-zinc-900">${act.title}</h3>
            <p class="text-xs text-zinc-600">${act.snippet || act.prize || ''}</p>
            <div class="text-[10px] text-zinc-400">🔗 Источник: ${act.platform || act.source || 'Веб-поиск'}</div>
          </div>
          <div class="mt-4 pt-3 border-t border-zinc-100 flex items-center justify-between">
            <span class="text-xs font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full">${act.boost || '+15%'} к индексу</span>
            ${act.link && act.link !== '#' 
              ? `<a href="${act.link}" target="_blank" class="px-3 py-1.5 rounded-lg bg-zinc-950 text-white text-xs font-bold">Перейти на сайт &rarr;</a>`
              : `<button onclick="joinActivity('${act.id}')" class="px-3 py-1.5 rounded-lg bg-zinc-950 text-white text-xs font-bold">${act.joined ? 'Вы участвуете' : 'Участвовать'}</button>`
            }
          </div>
        </div>
      `).join('');
    }
  }
}

// ==========================================
// 🤖 ИИ-КОНСУЛЬТАНТ (ЧАТ-ЛОГИКА)
// ==========================================

async function sendChatMessage() {
  const input = document.getElementById('chat-input');
  if (!input) return;
  const msg = input.value.trim();
  if (!msg) return;

  addChatMessage(msg, 'user');
  input.value = '';

  const messagesContainer = document.getElementById('chat-messages');
  const typingDiv = document.createElement('div');
  typingDiv.className = 'flex justify-start';
  typingDiv.innerHTML = `<div class="bg-white border border-zinc-200 px-4 py-2.5 rounded-2xl rounded-bl-none shadow-sm text-zinc-500 text-xs animate-pulse">ИИ анализирует твой профиль...</div>`;
  if (messagesContainer) {
    messagesContainer.appendChild(typingDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  try {
    const res = await fetch(`${API_BASE_URL}/api/ai/consult`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${state.token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ message: msg })
    });
    const data = await res.json();
    typingDiv.remove();
    addChatMessage(data.response || 'Ответ от ИИ получен.', 'assistant');
  } catch (err) {
    typingDiv.remove();
    addChatMessage('Не удалось связаться с ИИ-сервером. Проверьте запуск main.py', 'assistant');
  }
}

function addChatMessage(text, sender) {
  const container = document.getElementById('chat-messages');
  if (!container) return;

  const div = document.createElement('div');
  div.className = `flex ${sender === 'user' ? 'justify-end' : 'justify-start'}`;
  div.innerHTML = `
    <div class="max-w-[85%] px-4 py-3 rounded-2xl text-sm leading-relaxed shadow-sm ${
      sender === 'user' 
        ? 'bg-gradient-to-r from-pink-500 to-purple-600 text-white rounded-br-none' 
        : 'bg-white border border-zinc-200 text-zinc-700 rounded-bl-none'
    }">
      ${text}
    </div>
  `;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

// ==========================================
// ДЕЙСТВИЯ И ОБРАБОТЧИКИ СОБЫТИЙ
// ==========================================

function acceptOffer(offerId) {
  const offer = state.offers.find(o => String(o.id) === String(offerId));
  if (!offer) return;
  offer.accepted = true;
  renderStudentView();
  if (typeof showToast === 'function') {
    showToast('Согласие подтверждено! Контакты отправлены вузу.', 'success');
  }
}

function joinActivity(actId) {
  const act = state.activities.find(a => String(a.id) === String(actId));
  if (!act || act.joined) return;
  act.joined = true;
  renderStudentView();
  if (typeof showToast === 'function') {
    showToast('Заявка отправлена!', 'success');
  }
}

// Слушатель для формы чата
document.addEventListener('DOMContentLoaded', () => {
  initApp();
  const chatForm = document.getElementById('chat-form');
  if (chatForm) {
    chatForm.addEventListener('submit', (e) => {
      e.preventDefault();
      sendChatMessage();
    });
  }
});