// Contenedor del oso 3D
let scene, camera, renderer, bearGroup;
let isCalm = true;
let isListening = false;
let isHappy = false;
let isStressed = false;
let isSad = false;
let isThinking = false;

function init3DBear() {
  const container = document.getElementById('bear-container');
  
  // Escena
  scene = new THREE.Scene();
  
  // Cámara
  camera = new THREE.PerspectiveCamera(45, 1, 0.1, 1000);
  camera.position.z = 6;
  
  // Renderizador
  renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
  renderer.setSize(220, 220);
  renderer.setClearColor(0x000000, 0);
  container.appendChild(renderer.domElement);
  
  // Luces
  const light = new THREE.DirectionalLight(0xffffff, 1.2);
  light.position.set(5, 5, 5);
  scene.add(light);
  
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.8);
  scene.add(ambientLight);
  
  const backLight = new THREE.DirectionalLight(0xffffff, 0.4);
  backLight.position.set(-3, -3, -3);
  scene.add(backLight);
  
  // Grupo del panda
  bearGroup = new THREE.Group();
  
  // === MATERIALES ===
  const whiteMaterial = new THREE.MeshPhongMaterial({ 
    color: 0xffffff,
    shininess: 20
  });
  
  const blackMaterial = new THREE.MeshPhongMaterial({ 
    color: 0x1a1a1a,
    shininess: 15
  });
  
  const noseMaterial = new THREE.MeshPhongMaterial({ 
    color: 0x2a2a2a,
    shininess: 50
  });
  
  const blushMaterial = new THREE.MeshPhongMaterial({ 
    color: 0xffb6c1,
    shininess: 5,
    transparent: true,
    opacity: 0.7
  });
  
  // === CUERPO (barriga blanca) ===
  const body = new THREE.Mesh(
    new THREE.SphereGeometry(0.9, 32, 32),
    whiteMaterial
  );
  body.scale.set(1, 1.2, 0.9);
  body.position.y = -0.8;
  bearGroup.add(body);
  
  // === CABEZA (blanca) ===
  const head = new THREE.Mesh(
    new THREE.SphereGeometry(1, 32, 32),
    whiteMaterial
  );
  head.scale.set(1, 1.05, 0.95);
  head.position.y = 0.3;
  bearGroup.add(head);
  
  // === PARCHES NEGROS DE OJOS ===
  const eyePatchGeometry = new THREE.SphereGeometry(0.35, 32, 32);
  
  const leftEyePatch = new THREE.Mesh(eyePatchGeometry, blackMaterial);
  leftEyePatch.position.set(-0.35, 0.4, 0.75);
  leftEyePatch.scale.set(1.1, 1.3, 0.5);
  bearGroup.add(leftEyePatch);
  
  const rightEyePatch = new THREE.Mesh(eyePatchGeometry, blackMaterial);
  rightEyePatch.position.set(0.35, 0.4, 0.75);
  rightEyePatch.scale.set(1.1, 1.3, 0.5);
  bearGroup.add(rightEyePatch);
  
  // === OJOS (dentro de los parches negros) ===
  const eyeGeometry = new THREE.SphereGeometry(0.1, 32, 32);
  
  const leftEye = new THREE.Mesh(eyeGeometry, blackMaterial);
  leftEye.position.set(-0.35, 0.42, 0.88);
  bearGroup.add(leftEye);
  
  const rightEye = new THREE.Mesh(eyeGeometry, blackMaterial);
  rightEye.position.set(0.35, 0.42, 0.88);
  bearGroup.add(rightEye);
  
  // Brillo en ojos (blanco)
  const shineMaterial = new THREE.MeshBasicMaterial({ color: 0xffffff });
  const shineGeometry = new THREE.SphereGeometry(0.04, 16, 16);
  
  const leftShine = new THREE.Mesh(shineGeometry, shineMaterial);
  leftShine.position.set(-0.33, 0.46, 0.93);
  bearGroup.add(leftShine);
  
  const rightShine = new THREE.Mesh(shineGeometry, shineMaterial);
  rightShine.position.set(0.37, 0.46, 0.93);
  bearGroup.add(rightShine);
  
  // === OREJAS NEGRAS (redondas) ===
  const earGeometry = new THREE.SphereGeometry(0.3, 32, 32);
  
  const leftEar = new THREE.Mesh(earGeometry, blackMaterial);
  leftEar.position.set(-0.65, 0.9, 0.05);
  bearGroup.add(leftEar);
  
  const rightEar = new THREE.Mesh(earGeometry, blackMaterial);
  rightEar.position.set(0.65, 0.9, 0.05);
  bearGroup.add(rightEar);
  
  // === NARIZ NEGRA ===
  const nose = new THREE.Mesh(
    new THREE.SphereGeometry(0.12, 32, 32),
    noseMaterial
  );
  nose.position.set(0, 0.15, 1.0);
  nose.scale.set(1, 0.7, 0.8);
  bearGroup.add(nose);
  
  // === SONRISA (curva sutil) ===
  const smileCurve = new THREE.QuadraticBezierCurve3(
    new THREE.Vector3(-0.15, 0.05, 0.98),
    new THREE.Vector3(0, -0.02, 1.0),
    new THREE.Vector3(0.15, 0.05, 0.98)
  );
  
  const smileGeometry = new THREE.TubeGeometry(smileCurve, 20, 0.02, 8, false);
  const smileMaterial = new THREE.MeshBasicMaterial({ color: 0x2a2a2a });
  const smile = new THREE.Mesh(smileGeometry, smileMaterial);
  bearGroup.add(smile);
  
  // === MEJILLAS ROSADAS ===
  const cheekGeometry = new THREE.SphereGeometry(0.18, 32, 32);
  
  const leftCheek = new THREE.Mesh(cheekGeometry, blushMaterial);
  leftCheek.position.set(-0.65, 0.12, 0.75);
  leftCheek.scale.set(1.2, 0.8, 0.5);
  bearGroup.add(leftCheek);
  
  const rightCheek = new THREE.Mesh(cheekGeometry, blushMaterial);
  rightCheek.position.set(0.65, 0.12, 0.75);
  rightCheek.scale.set(1.2, 0.8, 0.5);
  bearGroup.add(rightCheek);
  
  // === BRAZOS NEGROS ===
  const armGeometry = new THREE.SphereGeometry(0.35, 32, 32);
  
  const leftArm = new THREE.Mesh(armGeometry, blackMaterial);
  leftArm.position.set(-0.85, -0.5, 0.3);
  leftArm.scale.set(0.7, 1.2, 0.6);
  leftArm.rotation.z = 0.3;
  bearGroup.add(leftArm);
  
  const rightArm = new THREE.Mesh(armGeometry, blackMaterial);
  rightArm.position.set(0.85, -0.5, 0.3);
  rightArm.scale.set(0.7, 1.2, 0.6);
  rightArm.rotation.z = -0.3;
  bearGroup.add(rightArm);
  
  // === PIERNAS NEGRAS ===
  const legGeometry = new THREE.SphereGeometry(0.4, 32, 32);
  
  const leftLeg = new THREE.Mesh(legGeometry, blackMaterial);
  leftLeg.position.set(-0.45, -1.5, 0.2);
  leftLeg.scale.set(0.9, 0.7, 0.8);
  bearGroup.add(leftLeg);
  
  const rightLeg = new THREE.Mesh(legGeometry, blackMaterial);
  rightLeg.position.set(0.45, -1.5, 0.2);
  rightLeg.scale.set(0.9, 0.7, 0.8);
  bearGroup.add(rightLeg);
  
  // Posición inicial
  bearGroup.rotation.x = -0.1;
  bearGroup.position.y = 0;
  
  scene.add(bearGroup);
  
  animate();
}

// === ANIMACIÓN ===
let time = 0;
let blinkTimer = 0;
let isBlinking = false;

function animate() {
  requestAnimationFrame(animate);
  
  time += 0.016; // ~60fps
  blinkTimer += 0.016;
  
  // Parpadeo aleatorio
  if (blinkTimer > 3 + Math.random() * 3 && !isBlinking) {
    blink();
    blinkTimer = 0;
  }
  
  if (isCalm) {
    // Respiración suave
    bearGroup.scale.y = 1 + Math.sin(time * 0.8) * 0.02;
    bearGroup.scale.x = 1 + Math.sin(time * 0.8) * 0.01;
    // Flotación
    bearGroup.position.y = Math.sin(time * 0.6) * 0.15;
    // Balanceo muy sutil
    bearGroup.rotation.z = Math.sin(time * 0.5) * 0.03;
    bearGroup.rotation.y = Math.sin(time * 0.4) * 0.05;
  }
  
  if (isListening) {
    // Inclinación de cabeza (curioso)
    bearGroup.rotation.y = Math.sin(time * 2) * 0.15;
    bearGroup.rotation.z = Math.sin(time * 1.5) * 0.08;
    bearGroup.scale.set(
      1 + Math.sin(time * 2) * 0.015,
      1 + Math.sin(time * 2) * 0.015,
      1 + Math.sin(time * 2) * 0.015
    );
  }
  
  if (isHappy) {
    // Rebote alegre
    bearGroup.position.y = Math.abs(Math.sin(time * 4)) * 0.4;
    bearGroup.rotation.z = Math.sin(time * 4) * 0.1;
    bearGroup.scale.x = 1 + Math.sin(time * 8) * 0.03;
  }

  if (isStressed) {
    // Vibración pequeña y rápida — nerviosismo
    bearGroup.position.x = Math.sin(time * 12) * 0.06;
    bearGroup.position.y = Math.sin(time * 10) * 0.04;
    bearGroup.rotation.z = Math.sin(time * 8) * 0.05;
    bearGroup.scale.y = 1 + Math.sin(time * 6) * 0.02;
  }

  if (isSad) {
    // Movimiento lento y caído — pesadez
    bearGroup.position.y = -0.2 + Math.sin(time * 0.4) * 0.05;
    bearGroup.rotation.z = Math.sin(time * 0.3) * 0.04;
    bearGroup.rotation.x = -0.15 + Math.sin(time * 0.3) * 0.02; // cabeza ligeramente hacia abajo
  }

  if (isThinking) {
    // Inclinación lenta a un lado — reflexivo
    bearGroup.rotation.z = 0.12 + Math.sin(time * 0.8) * 0.05;
    bearGroup.rotation.y = Math.sin(time * 0.6) * 0.08;
    bearGroup.position.y = Math.sin(time * 0.5) * 0.1;
  }
  
  renderer.render(scene, camera);
}

// Parpadeo
function blink() {
  isBlinking = true;
  // Los ojos están en posiciones 8 y 9
  const leftEye = bearGroup.children[8];
  const rightEye = bearGroup.children[9];
  
  leftEye.scale.y = 0.1;
  rightEye.scale.y = 0.1;
  
  setTimeout(() => {
    leftEye.scale.y = 1;
    rightEye.scale.y = 1;
    isBlinking = false;
  }, 150);
}

// === CONTROL DE ESTADOS ===
function setBearState(state) {
  // Resetear todos los estados
  isCalm = false;
  isListening = false;
  isHappy = false;
  isStressed = false;
  isSad = false;
  isThinking = false;

  // Resetear transformaciones para que no queden residuos del estado anterior
  bearGroup.position.x = 0;
  bearGroup.rotation.x = -0.1;

  if (state === 'calm')      isCalm = true;
  else if (state === 'listening') isListening = true;
  else if (state === 'happy')     isHappy = true;
  else if (state === 'stressed')  isStressed = true;
  else if (state === 'sad')       isSad = true;
  else if (state === 'thinking')  isThinking = true;
  else isCalm = true; // fallback
}

// Exponer al window para que chat.js pueda llamarlo
window.setBearState = setBearState;

// Inicializar cuando cargue la página
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init3DBear);
} else {
  init3DBear();
}