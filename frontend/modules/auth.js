// modules/auth.js

import { mostrarAvisoTesterCada } from './utils.js';
import { createClient } from 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js/+esm';

const _SUPABASE_URL = 'https://idbdvpykclbxdeoirsye.supabase.co';
const _SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlkYmR2cHlrY2xieGRlb2lyc3llIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI0ODQ5ODYsImV4cCI6MjA4ODA2MDk4Nn0.GEPzBysq6hKiH5UCIi443lEeM0gX17wAtZjp9ZAJUoM';
const _supabase = createClient(_SUPABASE_URL, _SUPABASE_ANON_KEY);
// ============================================
// ESTADO
// ============================================

let currentUser = null;
let _pendingEmail = null;
let _pendingPassword = null;
let _pendingNombre = null;

// ============================================
// FUNCIONES PÚBLICAS
// ============================================

export function getCurrentUser() {
    return currentUser;
}

export function showAuthScreen() {
    // Ocultar el chat
    document.querySelector('.app').style.display = 'none';

    // Crear pantalla de auth si no existe
    if (!document.getElementById('auth-screen')) {
        _crearAuthScreen();
    }

    document.getElementById('auth-screen').classList.remove('hidden');
    _mostrarTab('login');
}

export function hideAuthScreen() {
    const authScreen = document.getElementById('auth-screen');
    if (authScreen) authScreen.classList.add('hidden');
    document.querySelector('.app').style.display = 'flex';
}

// ============================================
// CREAR PANTALLA
// ============================================

function _crearAuthScreen() {
    const screen = document.createElement('div');
    screen.id = 'auth-screen';
    screen.innerHTML = `
        <div class="auth-container">

            <div class="auth-logo">
                <span>🐼</span>
                <h1>Numa</h1>
                <p>Tu compañero emocional</p>
            </div>

            <div class="auth-tabs">
                <button class="auth-tab active" id="tab-login" onclick="switchTab('login')">
                    Iniciar sesión
                </button>
                <button class="auth-tab" id="tab-register" onclick="switchTab('register')">
                    Registrarse
                </button>
            </div>

            <!-- LOGIN -->
            <div id="form-login" class="auth-form">
                <input 
                    type="email"
                    id="login-email"
                    placeholder="Tu email"
                    class="auth-input"
                />
                <input 
                    type="password"
                    id="login-password"
                    placeholder="Contraseña"
                    class="auth-input"
                />
                <button class="auth-btn" onclick="submitLogin()">
                    Entrar
                </button>
                <div class="auth-divider"><span>o</span></div>
                <button class="auth-btn-google" onclick="loginConGoogle()">
                    <img src="https://www.google.com/favicon.ico" width="18" height="18" />
                    Continuar con Google
                </button>
                <p id="login-error" class="auth-error hidden"></p>
            </div>

            <!-- REGISTRO -->
            <div id="form-register" class="auth-form hidden">
                <input 
                    type="text"
                    id="register-nombre"
                    placeholder="¿Cómo te llamás?"
                    class="auth-input"
                />
                <input 
                    type="email"
                    id="register-email"
                    placeholder="Tu email"
                    class="auth-input"
                />
                <input 
                    type="password"
                    id="register-password"
                    placeholder="Contraseña (mínimo 6 caracteres)"
                    class="auth-input"
                />
                <button class="auth-btn" onclick="submitRegister()">
                    Crear cuenta
                </button>
                <div class="auth-divider"><span>o</span></div>
                <button class="auth-btn-google" onclick="loginConGoogle()">
                    <img src="https://www.google.com/favicon.ico" width="18" height="18" />
                    Continuar con Google
                </button>
                <p id="register-error" class="auth-error hidden"></p>
            </div>

        </div>
    `;

    document.body.appendChild(screen);
}

// ============================================
// TABS
// ============================================

function _mostrarTab(tab) {
    const loginForm = document.getElementById('form-login');
    const registerForm = document.getElementById('form-register');
    const tabLogin = document.getElementById('tab-login');
    const tabRegister = document.getElementById('tab-register');

    if (tab === 'login') {
        loginForm.classList.remove('hidden');
        registerForm.classList.add('hidden');
        tabLogin.classList.add('active');
        tabRegister.classList.remove('active');
    } else {
        loginForm.classList.add('hidden');
        registerForm.classList.remove('hidden');
        tabLogin.classList.remove('active');
        tabRegister.classList.add('active');
    }
}

// ============================================
// SUBMIT LOGIN
// ============================================

async function _submitLogin() {
    const email = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value.trim();
    const errorEl = document.getElementById('login-error');

    if (!email || !password) {
        _mostrarError(errorEl, 'Completá todos los campos');
        return;
    }

    try {
        const res = await fetch('/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });

        if (!res.ok) {
            const err = await res.json();
            _mostrarError(errorEl, err.detail || 'Error al iniciar sesión');
            return;
        }

        const data = await res.json();
        currentUser = data;
        localStorage.setItem('numa_user', JSON.stringify(data));

        hideAuthScreen();

        // Chequear si ya completó el onboarding
        try {
            const perfilRes = await fetch(`/profile/${data.user_id}`, {
                headers: { 'Authorization': `Bearer ${data.access_token}` }
            });
            if (perfilRes.ok) {
                const perfil = await perfilRes.json();
                if (!perfil.onboarding_completo) {
                    const { showOnboarding } = await import('./onboarding.js');
                    showOnboarding(data.user_id);
                    return;
                }
            }
        } catch (e) {
            console.warn('No se pudo verificar onboarding:', e);
        }

        if (window.inicializarChat) await window.inicializarChat();
        if (window.agregarMensaje) window.agregarMensaje(`Bienvenido ${data.name || 'de vuelta'} 🐼 Me alegra que estés aquí.`, 'oso');
        mostrarAvisoTesterCada();
    } catch (e) {
        _mostrarError(errorEl, 'Error de conexión');
    }
}

// ============================================
// SUBMIT REGISTRO — con onboarding para usuarios nuevos
// ============================================

async function _submitRegister() {
    const nombre = document.getElementById('register-nombre').value.trim();
    const email = document.getElementById('register-email').value.trim();
    const password = document.getElementById('register-password').value.trim();
    const errorEl = document.getElementById('register-error');

    if (!nombre || !email || !password) {
        _mostrarError(errorEl, 'Completá todos los campos');
        return;
    }

    if (password.length < 6) {
        _mostrarError(errorEl, 'La contraseña debe tener al menos 6 caracteres');
        return;
    }

    try {
        const res = await fetch('/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password, nombre })
        });

        if (!res.ok) {
            const err = await res.json();
            _mostrarError(errorEl, err.detail || 'Error al registrarse');
            return;
        }

        // Registro exitoso → guardar datos y mostrar pantalla OTP
        _pendingEmail = email;
        _pendingPassword = password;
        _pendingNombre = nombre;
        _mostrarPantallaOtp(email);

    } catch (e) {
        _mostrarError(errorEl, 'Error de conexión');
    }
}

// ============================================
// PANTALLA OTP
// ============================================

function _mostrarPantallaOtp(email) {
    const container = document.querySelector('#auth-screen .auth-container');
    container.querySelector('.auth-tabs').classList.add('hidden');
    container.querySelector('#form-login').classList.add('hidden');
    container.querySelector('#form-register').classList.add('hidden');

    const existing = container.querySelector('#form-otp');
    if (existing) existing.remove();

    const div = document.createElement('div');
    div.id = 'form-otp';
    div.className = 'auth-form';
    div.innerHTML = `
        <h2>Revisá tu email 📬</h2>
        <p>Te mandamos un código a <strong>${email}</strong>. Ingresalo acá:</p>
        <input
            type="text"
            id="otp-input"
            inputmode="numeric"
            maxlength="8"
            placeholder="· · · · · ·"
            class="auth-input"
            style="text-align:center; font-size:2rem; letter-spacing:0.5rem"
        />
        <button class="auth-btn" onclick="submitOtp()">Confirmar</button>
        <button onclick="reenviarOtp()" style="background:none;border:none;color:inherit;cursor:pointer;margin-top:8px;text-decoration:underline;">Reenviar código</button>
        <p id="otp-error" class="auth-error hidden"></p>
    `;
    container.appendChild(div);
}

async function _submitOtp() {
    const codigo = (document.getElementById('otp-input').value || '').trim();
    const errorEl = document.getElementById('otp-error');
    if (codigo.length !== 8) {
        _mostrarError(errorEl, 'El código debe tener 8 dígitos');
        return;
    }
    try {
        const res = await fetch('/verify-email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: _pendingEmail, token: codigo })
        });
        if (!res.ok) {
            const err = await res.json();
            _mostrarError(errorEl, err.detail || 'Código inválido o expirado');
            return;
        }
        const data = await res.json();
        currentUser = data;
        localStorage.setItem('numa_user', JSON.stringify(data));
        document.getElementById('auth-screen').classList.add('hidden');
        const { showOnboarding } = await import('./onboarding.js');
        showOnboarding(data.user_id);
    } catch (e) {
        _mostrarError(errorEl, 'Error de conexión');
    }
}

async function _reenviarOtp() {
    await fetch('/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: _pendingEmail, password: _pendingPassword, nombre: _pendingNombre })
    });
    const errorEl = document.getElementById('otp-error');
    errorEl.textContent = '📬 Te reenviamos el código, revisá tu casilla';
    errorEl.classList.remove('hidden');
}

// ============================================
// GOOGLE OAUTH
// ============================================

async function _loginConGoogle() {
    const { error } = await _supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
            redirectTo: 'https://web-production-3f4e4.up.railway.app'
        }
    });
    if (error) {
        const errorEl = document.getElementById('login-error');
        _mostrarError(errorEl, 'Error al conectar con Google');
    }
}

export async function manejarCallbackOAuth() {
    // Supabase v2 usa PKCE: devuelve ?code= en los query params, no en el hash
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    if (!code) return false;

    const { data, error } = await _supabase.auth.exchangeCodeForSession(window.location.href);
    if (error || !data.session) return false;

    const user = data.session.user;
    const session = data.session;
    currentUser = {
        user_id: user.id,
        email: user.email,
        access_token: session.access_token,
        refresh_token: session.refresh_token
    };
    localStorage.setItem('numa_user', JSON.stringify(currentUser));

    window.history.replaceState(null, '', window.location.pathname);

    try {
        const perfilRes = await fetch(`/profile/${user.id}`, {
            headers: { 'Authorization': `Bearer ${session.access_token}` }
        });
        if (perfilRes.ok) {
            const perfil = await perfilRes.json();
            if (!perfil.onboarding_completo) {
                const { showOnboarding } = await import('./onboarding.js');
                showOnboarding(user.id);
                return true;
            }
        }
    } catch (e) {
        console.warn('No se pudo verificar onboarding OAuth:', e);
    }

    if (window.inicializarChat) await window.inicializarChat();
    if (window.agregarMensaje) window.agregarMensaje(`Bienvenido 🐼 Me alegra que estés aquí.`, 'oso');
    mostrarAvisoTesterCada();
    return true;
}

// ============================================
// HELPERS
// ============================================

function _mostrarError(el, mensaje) {
    el.textContent = mensaje;
    el.classList.remove('hidden');
}

// ============================================
// LOGOUT
// ============================================

function _logout() {
    localStorage.removeItem('numa_user');
    currentUser = null;

    // Limpiar el chat
    const chat = document.getElementById('chat');
    if (chat) chat.innerHTML = '';

    // Mostrar pantalla de login
    showAuthScreen();
}

// ============================================
// EXPONER AL WINDOW
// ============================================

window.switchTab = _mostrarTab;
window.submitLogin = _submitLogin;
window.submitRegister = _submitRegister;
window.logout = _logout;
window.submitOtp = _submitOtp;
window.reenviarOtp = _reenviarOtp;
window.loginConGoogle = _loginConGoogle;