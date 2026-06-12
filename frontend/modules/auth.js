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

// Forgot password state
let _resetEmail = null;
let _resetToken = null;
let _resendTimerId = null;

// ============================================
// FUNCIONES PÚBLICAS
// ============================================

export function getCurrentUser() {
    return currentUser;
}

export function showAuthScreen() {
    document.querySelector('.app').style.display = 'none';

    if (!document.getElementById('auth-screen')) {
        _crearAuthScreen();
    }

    // Limpiar estado OTP si quedó de una sesión anterior
    const formOtp = document.getElementById('form-otp');
    if (formOtp) formOtp.remove();
    // Limpiar estado forgot password si quedó de una sesión anterior
    const formReset = document.getElementById('form-reset');
    if (formReset) formReset.remove();
    if (_resendTimerId) { clearInterval(_resendTimerId); _resendTimerId = null; }
    _resetEmail = null;
    _resetToken = null;

    const tabs = document.querySelector('#auth-screen .auth-tabs');
    if (tabs) tabs.classList.remove('hidden');
    _pendingEmail = null;
    _pendingPassword = null;
    _pendingNombre = null;

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
                <button class="auth-forgot-link" onclick="mostrarOlvideContrasena()">¿Olvidaste tu contraseña?</button>
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
    // Supabase envía códigos de 6 dígitos (la validación anterior exigía 8
    // y bloqueaba el registro). Se acepta 6-8 por si cambia la config.
    if (!/^\d{6,8}$/.test(codigo)) {
        _mostrarError(errorEl, 'Ingresá el código de 6 dígitos que te llegó por email');
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
            redirectTo: 'https://web-production-3f4e4.up.railway.app',
            queryParams: { prompt: 'select_account' }
        }
    });
    if (error) {
        const errorEl = document.getElementById('login-error');
        _mostrarError(errorEl, 'Error al conectar con Google');
    }
}

export async function manejarCallbackOAuth() {
    let session = null;

    // PKCE flow: ?code= en los query params
    const queryParams = new URLSearchParams(window.location.search);
    const code = queryParams.get('code');
    if (code) {
        const { data, error } = await _supabase.auth.exchangeCodeForSession(window.location.href);
        if (error || !data.session) return false;
        session = data.session;
    }

    // Recovery flow: el usuario hizo clic en el link de "Reset Password"
    const hash = window.location.hash;
    const hashParams = new URLSearchParams(hash.substring(1));
    if (hashParams.get('type') === 'recovery') {
        const access_token = hashParams.get('access_token');
        const refresh_token = hashParams.get('refresh_token');
        if (access_token) {
            await _supabase.auth.setSession({ access_token, refresh_token: refresh_token || '' });
        }
        window.history.replaceState(null, '', window.location.pathname);
        _mostrarNuevaContrasena();
        return true;
    }

    // Implicit flow: #access_token= en el hash
    if (!session) {
        if (!hash || !hash.includes('access_token')) return false;
        const access_token = hashParams.get('access_token');
        const refresh_token = hashParams.get('refresh_token');
        if (!access_token) return false;
        const { data, error } = await _supabase.auth.setSession({ access_token, refresh_token });
        if (error || !data.session) return false;
        session = data.session;
    }

    const user = session.user;
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
    el.style.color = ''; // reset por si quedó en verde de un mensaje de éxito
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
// FORGOT PASSWORD — PASO 1: Ingresá tu email
// ============================================

function _mostrarForgotPassword() {
    const container = document.querySelector('#auth-screen .auth-container');
    container.querySelector('.auth-tabs').classList.add('hidden');
    container.querySelector('#form-login').classList.add('hidden');
    container.querySelector('#form-register').classList.add('hidden');

    const existing = container.querySelector('#form-reset');
    if (existing) existing.remove();

    const div = document.createElement('div');
    div.id = 'form-reset';
    div.className = 'auth-form';
    div.innerHTML = `
        <h2 style="margin:0 0 6px;color:#2f4f45;font-size:1.3rem">Recuperar contraseña 🔑</h2>
        <p style="margin:0 0 4px;color:#8fb5a3;font-size:0.9rem">
            Ingresá el email de tu cuenta y te enviamos un link para restablecer tu contraseña.
        </p>
        <input
            type="email"
            id="reset-email"
            placeholder="Tu email"
            class="auth-input"
            inputmode="email"
            autocomplete="email"
        />
        <button class="auth-btn" onclick="submitForgotPassword()">Enviar link</button>
        <button onclick="volverAlLogin()" class="auth-link-btn">← Volver al inicio de sesión</button>
        <p id="reset-step1-error" class="auth-error hidden"></p>
    `;
    container.appendChild(div);

    setTimeout(() => {
        const input = document.getElementById('reset-email');
        if (input) input.focus();
    }, 100);
}

async function _submitForgotPassword() {
    const emailInput = document.getElementById('reset-email');
    const errorEl = document.getElementById('reset-step1-error');
    const email = emailInput ? emailInput.value.trim() : '';

    if (!email || !email.includes('@')) {
        _mostrarError(errorEl, 'Ingresá un email válido');
        return;
    }

    const btn = document.querySelector('#form-reset .auth-btn');
    btn.textContent = 'Enviando...';
    btn.disabled = true;

    try {
        // Usar Supabase directamente — manda email de "Reset Password" estándar
        await _supabase.auth.resetPasswordForEmail(email, {
            redirectTo: window.location.origin
        });
    } catch (e) {
        // Silencioso — no revelar si el email existe
    }

    // Siempre mostrar confirmación (prevent enumeration)
    _resetEmail = email;
    _mostrarConfirmacionEnvio(email);
}

// ============================================
// FORGOT PASSWORD — CONFIRMACIÓN (link enviado)
// ============================================

function _mostrarConfirmacionEnvio(email) {
    const container = document.querySelector('#auth-screen .auth-container');
    const existing = container.querySelector('#form-reset');
    if (existing) existing.remove();

    const div = document.createElement('div');
    div.id = 'form-reset';
    div.className = 'auth-form';
    div.innerHTML = `
        <h2 style="margin:0 0 6px;color:#2f4f45;font-size:1.3rem">Revisá tu email</h2>
        <p style="margin:0 0 4px;color:#8fb5a3;font-size:0.9rem">
            Te enviamos un link a <strong style="color:#4a6a5e">${email}</strong>.<br>
            Hacé clic en el link para restablecer tu contraseña.
        </p>
        <p style="margin:0;text-align:center;font-size:0.8rem;color:#aaa">Si no llegó, revisá la carpeta de spam.</p>
        <button id="reset-resend-btn" onclick="reenviarCodigoReset()" class="auth-link-btn" disabled>
            Reenviar link (<span id="reset-resend-timer">30</span>s)
        </button>
        <button onclick="volverAlLogin()" class="auth-link-btn" style="color:#bbb;font-size:0.82rem;margin-top:-6px">← Volver al inicio de sesión</button>
        <p id="reset-confirm-error" class="auth-error hidden"></p>
    `;
    container.appendChild(div);

    _iniciarCooldownReenvio();
}

function _iniciarCooldownReenvio() {
    if (_resendTimerId) clearInterval(_resendTimerId);

    const btn = document.getElementById('reset-resend-btn');
    const timerSpan = document.getElementById('reset-resend-timer');
    if (!btn || !timerSpan) return;

    btn.disabled = true;
    let remaining = 30;
    timerSpan.textContent = remaining;

    _resendTimerId = setInterval(() => {
        remaining--;
        if (remaining <= 0) {
            clearInterval(_resendTimerId);
            _resendTimerId = null;
            btn.disabled = false;
            btn.innerHTML = 'Reenviar link';
        } else {
            timerSpan.textContent = remaining;
        }
    }, 1000);
}

async function _reenviarCodigoReset() {
    const btn = document.getElementById('reset-resend-btn');
    const errorEl = document.getElementById('reset-confirm-error');
    if (!_resetEmail || !btn || btn.disabled) return;

    try {
        await _supabase.auth.resetPasswordForEmail(_resetEmail, {
            redirectTo: window.location.origin
        });
        errorEl.textContent = 'Link reenviado, revisá tu casilla';
        errorEl.style.color = '#5a9e7a';
        errorEl.classList.remove('hidden');
        _iniciarCooldownReenvio();
    } catch (e) {
        _mostrarError(errorEl, 'Error de conexión. Intentá de nuevo.');
    }
}

// ============================================
// FORGOT PASSWORD — NUEVA CONTRASEÑA (via recovery link)
// ============================================

function _mostrarNuevaContrasena() {
    // Asegurar que el auth-screen existe y es visible
    if (!document.getElementById('auth-screen')) _crearAuthScreen();
    document.getElementById('auth-screen').classList.remove('hidden');
    document.querySelector('.app').style.display = 'none';

    const container = document.querySelector('#auth-screen .auth-container');
    // Ocultar tabs y formularios
    const tabs = container.querySelector('.auth-tabs');
    if (tabs) tabs.classList.add('hidden');
    const formLogin = container.querySelector('#form-login');
    if (formLogin) formLogin.classList.add('hidden');
    const formRegister = container.querySelector('#form-register');
    if (formRegister) formRegister.classList.add('hidden');

    const existing = container.querySelector('#form-reset');
    if (existing) existing.remove();

    if (_resendTimerId) { clearInterval(_resendTimerId); _resendTimerId = null; }

    const div = document.createElement('div');
    div.id = 'form-reset';
    div.className = 'auth-form';
    div.innerHTML = `
        <h2 style="margin:0 0 6px;color:#2f4f45;font-size:1.3rem">Nueva contraseña 🔒</h2>
        <p style="margin:0 0 4px;color:#8fb5a3;font-size:0.9rem">
            Elegí una contraseña nueva de al menos 8 caracteres.
        </p>
        <input
            type="password"
            id="reset-nueva"
            placeholder="Nueva contraseña"
            class="auth-input"
            autocomplete="new-password"
        />
        <input
            type="password"
            id="reset-confirmar"
            placeholder="Confirmar contraseña"
            class="auth-input"
            autocomplete="new-password"
        />
        <button class="auth-btn" onclick="submitNuevaContrasena()">Cambiar contraseña</button>
        <p id="reset-step3-error" class="auth-error hidden"></p>
    `;
    container.appendChild(div);

    document.getElementById('reset-nueva').focus();
}

async function _submitNuevaContrasena() {
    const nuevaInput = document.getElementById('reset-nueva');
    const confirmarInput = document.getElementById('reset-confirmar');
    const errorEl = document.getElementById('reset-step3-error');

    const nueva = nuevaInput ? nuevaInput.value : '';
    const confirmar = confirmarInput ? confirmarInput.value : '';

    if (nueva.length < 8) {
        _mostrarError(errorEl, 'La contraseña debe tener al menos 8 caracteres');
        return;
    }
    if (nueva !== confirmar) {
        _mostrarError(errorEl, 'Las contraseñas no coinciden');
        return;
    }

    const btn = document.querySelector('#form-reset .auth-btn');
    btn.textContent = 'Cambiando...';
    btn.disabled = true;

    try {
        // Actualizar contraseña usando la sesión de recovery activa
        const { error } = await _supabase.auth.updateUser({ password: nueva });

        if (error) {
            _mostrarError(errorEl, 'El link expiró o ya fue usado. Solicitá uno nuevo.');
            btn.textContent = 'Cambiar contraseña';
            btn.disabled = false;
            return;
        }

        // Cerrar la sesión de recovery (no dejar al usuario logueado automáticamente)
        await _supabase.auth.signOut();
        _mostrarExitoReset();
    } catch (e) {
        _mostrarError(errorEl, 'Error de conexión. Intentá de nuevo.');
        btn.textContent = 'Cambiar contraseña';
        btn.disabled = false;
    }
}

// ============================================
// FORGOT PASSWORD — PANTALLA ÉXITO
// ============================================

function _mostrarExitoReset() {
    const container = document.querySelector('#auth-screen .auth-container');
    const existing = container.querySelector('#form-reset');
    if (existing) existing.remove();

    const div = document.createElement('div');
    div.id = 'form-reset';
    div.className = 'auth-form';
    div.innerHTML = `
        <div style="text-align:center;padding:16px 0">
            <div style="font-size:3.5rem;margin-bottom:12px">✅</div>
            <h2 style="color:#2f4f45;margin:0 0 8px">¡Listo!</h2>
            <p style="color:#8fb5a3;margin:0 0 24px;font-size:0.95rem">Tu contraseña fue cambiada con éxito. Ya podés iniciar sesión.</p>
            <button class="auth-btn" onclick="volverAlLogin()">Ir al inicio de sesión</button>
        </div>
    `;
    container.appendChild(div);

    // Auto-redirigir al login después de 3s
    setTimeout(() => {
        if (document.getElementById('form-reset')) {
            _volverAlLogin();
        }
    }, 3000);
}

// ============================================
// FORGOT PASSWORD — VOLVER AL LOGIN
// ============================================

function _volverAlLogin() {
    _resetEmail = null;
    _resetToken = null;
    if (_resendTimerId) { clearInterval(_resendTimerId); _resendTimerId = null; }

    const container = document.querySelector('#auth-screen .auth-container');
    const resetDiv = container.querySelector('#form-reset');
    if (resetDiv) resetDiv.remove();

    container.querySelector('.auth-tabs').classList.remove('hidden');
    _mostrarTab('login');
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

// Forgot password
window.mostrarOlvideContrasena = _mostrarForgotPassword;
window.submitForgotPassword = _submitForgotPassword;
window.reenviarCodigoReset = _reenviarCodigoReset;
window.submitNuevaContrasena = _submitNuevaContrasena;
window.volverAlLogin = _volverAlLogin;