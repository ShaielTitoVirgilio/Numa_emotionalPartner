// frontend/ejerciciosData.js

export const CATALOGO_EJERCICIOS = {
  respiracion: [
    {
      id: "respiracion_box",
      nombre: "Respiración Cuadrada (Box)",
      descripcion: "Técnica usada por los Navy SEALs para recuperar el control y la concentración en situaciones de alto estrés.",
      cientifico: "Regula el sistema nervioso autónomo imponiendo un ritmo constante.",
      patron: { inhalar: 4, retener: 4, exhalar: 4, esperar: 4 }, // Segundos
      instruccion: "Imaginá un cuadrado. Inhalá, retené, exhalá y esperá en tiempos iguales."
    },
    {
      id: "respiracion_478",
      nombre: "Técnica 4-7-8",
      descripcion: "Desarrollada por el Dr. Andrew Weil, actúa como un tranquilizante natural para el sistema nervioso.",
      cientifico: "La exhalación larga estimula el nervio vago, reduciendo la frecuencia cardíaca rápidamente.",
      patron: { inhalar: 4, retener: 7, exhalar: 8, esperar: 0 },
      instruccion: "Inhalá suave, retené el aire y soltalo haciendo un sonido de silbido suave."
    },
    {
      id: "respiracion_balance",
      nombre: "Coherencia Cardíaca",
      descripcion: "Respiración rítmica para sincronizar corazón y cerebro.",
      cientifico: "Mejora la Variabilidad de la Frecuencia Cardíaca (VFC), asociada con la estabilidad emocional.",
      patron: { inhalar: 5, retener: 0, exhalar: 5, esperar: 0 },
      instruccion: "Respiración fluida, como las olas del mar. Sin pausas forzadas."
    }
  ],
  meditacion: [
    {
      id: "meditacion_bodyscan",
      nombre: "Escaneo Corporal (Body Scan)",
      descripcion: "Para liberar tensión física acumulada por estrés o ansiedad.",
      duracion: 180, // 3 min
      pasos: [
        "Cerrá los ojos y llevá la atención a los pies.",
        "Notá si hay tensión. Soltala al exhalar.",
        "Subí lentamente por las piernas, rodillas y muslos.",
        "Relajá el abdomen y el pecho.",
        "Soltá los hombros, dejálos caer.",
        "Relajá la mandíbula y la frente."
      ]
    },
    {
      id: "meditacion_mindfulness",
      nombre: "Atención Plena (3 min)",
      descripcion: "Para salir del bucle de pensamientos repetitivos.",
      duracion: 180,
      pasos: [
        "No intentes poner la mente en blanco.",
        "Solo observá tus pensamientos como si fueran nubes.",
        "Dejá que pasen sin juzgarlos.",
        "Si te distraés, volvé amablemente a tu respiración.",
        "Estás aquí, en el presente."
      ]
    }
  ],
  yoga: [
    {
      id: "yoga_cuello",
      nombre: "Alivio Cervical",
      descripcion: "Ideal para quienes trabajan muchas horas frente a la computadora.",
      pasos: [
        {   
            pose: "Oreja al hombro",
            guia: "Llevá la oreja derecha al hombro derecho. Mano suave sobre la cabeza.",
            animacion: "/static/assets/numa_cuello_der.mp4"
        },
        { 
            pose: "Oreja al hombro (izq)",
            guia: "Cambiá de lado suavemente. Respirá en la tensión.",
            animacion: "/static/assets/numa_cuello_izq.mp4"
        },
        { 
            pose: "Mentón al pecho", 
            guia: "Entrelazá manos detrás de la nuca y dejá caer el peso de los brazos.",
            animacion: "/static/assets/haciaAtras.mp4" },
        { 
            pose: "Apertura de pecho",
            guia: "Brazos atrás, abrí el pecho y mirá ligeramente arriba.",
            animacion: "/static/assets/pecho.mp4" 
        }
      ]
    },
    {
      id: "yoga_ansiedad",
      nombre: "Enraizar (Grounding)",
      descripcion: "Posturas bajas para bajar la energía de la ansiedad.",
      pasos: [
        { 
            pose: "Postura del Niño",
            guia: "Rodillas al suelo, frente al piso, brazos estirados adelante.",
            animacion: "/static/assets/pos_nino.mp4" 
        },
        { 
            pose: "Gato - Vaca",
            guia: "En 4 apoyos, arqueá la espalda mirando arriba (inhalá), curvá mirando al ombligo (exhalá).",
            animacion: "/static/assets/gatomalo_bueno.mp4" 
        },
        { 
            pose: "Flexión adelante",
            guia: "De pie, doblate hacia adelante, rodillas flexionadas, soltá la cabeza.",
            animacion: "/static/assets/haciaAdelante.mp4"
        }
      ]
    }
  ]
};