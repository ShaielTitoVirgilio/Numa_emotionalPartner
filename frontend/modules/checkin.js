// modules/checkin.js
// Modal de check-in diario: aparece después del primer mensaje respondido por Numa.
// Solo para usuarios logueados. Un check-in por día.

let _checkinVerificado = false; // Evita verificar más de una vez por sesión

const OPCIONES = [
  { value: 1, emoji: "😔", label: "Mal" },
  { value: 2, emoji: "😐", label: "Regular" },
  { value: 3, emoji: "🙂", label: "Bien" },
  { value: 4, emoji: "😄", label: "Muy bien" },
];

export async function verificarCheckinDiario() {
  if (_checkinVerificado) return;
  _checkinVerificado = true;

  const numaUser = localStorage.getItem("numa_user");
  if (!numaUser) return; // No logueado

  const userId = JSON.parse(numaUser).user_id;
  if (!userId) return;

  try {
    const res = await fetch(`/checkin/today?user_id=${userId}`);
    const data = await res.json();
    if (!data.checkin) {
      // No hizo check-in hoy → mostrar modal con pequeño delay para no interrumpir
      setTimeout(() => _mostrarModal(userId), 800);
    }
  } catch (e) {
    // Silencioso — el check-in no es crítico
    console.warn("No se pudo verificar el check-in:", e);
  }
}

function _mostrarModal(userId) {
  // Evitar duplicados
  if (document.getElementById("checkin-modal")) return;

  const overlay = document.createElement("div");
  overlay.id = "checkin-modal";
  overlay.className = "checkin-overlay";
  overlay.innerHTML = `
    <div class="checkin-card" role="dialog" aria-label="Check-in diario">
      <p class="checkin-pregunta">¿Cómo llegás hoy?</p>
      <div class="checkin-opciones">
        ${OPCIONES.map(op => `
          <button class="checkin-btn" data-value="${op.value}" aria-label="${op.label}">
            <span class="checkin-emoji">${op.emoji}</span>
            <span class="checkin-label">${op.label}</span>
          </button>
        `).join("")}
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  // Forzar reflow para que la animación de entrada funcione
  requestAnimationFrame(() => overlay.classList.add("visible"));

  // Event listeners en los botones
  overlay.querySelectorAll(".checkin-btn").forEach(btn => {
    btn.addEventListener("click", () => _guardarCheckin(userId, parseInt(btn.dataset.value), overlay));
  });

  // Click fuera = cerrar sin guardar
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) _cerrarModal(overlay);
  });
}

async function _guardarCheckin(userId, moodValue, overlay) {
  // Feedback visual inmediato
  overlay.querySelectorAll(".checkin-btn").forEach(btn => btn.disabled = true);
  const btnSeleccionado = overlay.querySelector(`[data-value="${moodValue}"]`);
  if (btnSeleccionado) btnSeleccionado.classList.add("seleccionado");

  try {
    await fetch("/checkin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, mood_value: moodValue }),
    });
  } catch (e) {
    console.warn("No se pudo guardar el check-in:", e);
  }

  setTimeout(() => _cerrarModal(overlay), 600);
}

function _cerrarModal(overlay) {
  overlay.classList.remove("visible");
  overlay.addEventListener("transitionend", () => overlay.remove(), { once: true });
}
