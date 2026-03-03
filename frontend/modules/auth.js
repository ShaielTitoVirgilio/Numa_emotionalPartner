// modules/auth.js

// ============================================
// ESTADO
// ============================================

let currentUser = null;

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

    } catch (e) {
        _mostrarError(errorEl, 'Error de conexión');
    }
}

// ============================================
// SUBMIT REGISTRO
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

        // Registro exitoso → hacer login automático
        const loginRes = await fetch('/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });

        const data = await loginRes.json();
        currentUser = data;
        localStorage.setItem('numa_user', JSON.stringify(data));

        hideAuthScreen();

    } catch (e) {
        _mostrarError(errorEl, 'Error de conexión');
    }
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