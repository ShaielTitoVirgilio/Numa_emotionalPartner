// frontend/ejerciciosData.js

export const CATALOGO_EJERCICIOS = {
  respiracion: [
    {
      id: "respiracion_box",
      nombre: "Respiración Cuadrada",
      descripcion: "Técnica usada por los Navy SEALs para recuperar el control y la concentración en situaciones de alto estrés.",
      cientifico: "Regula el sistema nervioso autónomo imponiendo un ritmo constante en las cuatro fases.",
      patron: { inhalar: 4, retener: 4, exhalar: 4, esperar: 4 },
      instruccion: "Imaginá un cuadrado. Cada lado es una fase de igual duración."
    },
    {
      id: "respiracion_478",
      nombre: "Técnica 4-7-8",
      descripcion: "Desarrollada por el Dr. Andrew Weil, actúa como un tranquilizante natural para el sistema nervioso.",
      cientifico: "La exhalación larga estimula el nervio vago, reduciendo la frecuencia cardíaca rápidamente.",
      patron: { inhalar: 4, retener: 7, exhalar: 8, esperar: 0 },
      instruccion: "Inhalá suave, retené el aire y soltalo lento. Hacelo con calma."
    },
    {
      id: "respiracion_balance",
      nombre: "Coherencia Cardíaca",
      descripcion: "Respiración rítmica para sincronizar corazón y cerebro. Ideal para momentos de tensión.",
      cientifico: "Mejora la Variabilidad de la Frecuencia Cardíaca (VFC), asociada con la estabilidad emocional.",
      patron: { inhalar: 5, retener: 0, exhalar: 5, esperar: 0 },
      instruccion: "Fluida, como olas del mar. Sin pausas forzadas. Dejate llevar."
    },
    {
      id: "respiracion_suspiro",
      nombre: "Suspiro Fisiológico",
      descripcion: "La técnica más rápida validada en laboratorio para reducir la ansiedad. Descubierta en Stanford.",
      cientifico: "El sorbito extra de aire colapsa los alvéolos, maximizando el intercambio de CO₂ y activando la calma en segundos.",
      patron: { inhalar: 5, retener: 1, exhalar: 10, esperar: 2 },
      instruccion: "Al inhalar: llenate los pulmones y tomá un sorbito rápido extra. Al exhalar: soltá todo lento."
    },
    {
      id: "respiracion_exhale",
      nombre: "Exhale Extendido",
      descripcion: "Simple y poderoso: exhalar el doble del tiempo que inhalás activa el freno natural del cuerpo.",
      cientifico: "La exhalación prolongada activa el nervio vago y eleva la variabilidad de frecuencia cardíaca (VFC).",
      patron: { inhalar: 4, retener: 0, exhalar: 8, esperar: 0 },
      instruccion: "Sin pausas ni retenciones. Solo inhalá natural y exhalá el doble de tiempo."
    },
    {
      id: "respiracion_activante",
      nombre: "Respiración Activante",
      descripcion: "Para salir del adormecimiento mental. Útil antes de una presentación, reunión o cuando necesitás enfoco.",
      cientifico: "El ritmo rápido aumenta la activación simpática controlada y la oxigenación del córtex prefrontal.",
      patron: { inhalar: 2, retener: 0, exhalar: 2, esperar: 1 },
      instruccion: "Rápida y con intención. Inhalá fuerza, exhalá tensión. Mantené el ritmo."
    }
  ],
  meditacion: [
    {
      id: "meditacion_bodyscan",
      nombre: "Escaneo Corporal",
      descripcion: "Para liberar tensión física acumulada por estrés o ansiedad.",
      cientifico: "El escaneo corporal activa el sistema nervioso parasimpático, reduciendo los niveles de cortisol.",
      pasos: [
        { pose: "Cerrá los ojos",         guia: "Llevá la atención a los pies. Notá si hay tensión, sin juzgar." },
        { pose: "Soltá al exhalar",        guia: "Con cada exhalación, dejá que la tensión se vaya de tus pies y pantorrillas." },
        { pose: "Subí por las piernas",    guia: "Llevá la atención a las rodillas, muslos y caderas. Observá sin hacer nada." },
        { pose: "Relajá el abdomen",       guia: "Soltá cualquier contracción en el vientre. Dejá que la respiración lo mueva suavemente." },
        { pose: "Liberá el pecho",         guia: "Notá el ritmo de tu corazón. Relajá los músculos que rodean las costillas." },
        { pose: "Soltá los hombros",       guia: "Dejálos caer hacia abajo, lejos de las orejas. Es donde más cargamos el estrés." },
        { pose: "Relajá el rostro",        guia: "Soltá la mandíbula, la frente, los párpados. Que todo esté suave." },
        { pose: "Cuerpo completo",         guia: "Sentí todo tu cuerpo al mismo tiempo. Pesado, cálido, en paz. Respirá profundo." }
      ]
    },
    {
      id: "meditacion_mindfulness",
      nombre: "Atención Plena",
      descripcion: "Para salir del bucle de pensamientos repetitivos y volver al presente.",
      cientifico: "El mindfulness reduce la actividad en la red neuronal por defecto (DMN), responsable del rumiar mental.",
      pasos: [
        { pose: "Sin poner la mente en blanco", guia: "No es eso la meditación. Solo observá lo que hay. Pensamientos, sensaciones, sonidos." },
        { pose: "Los pensamientos son nubes",   guia: "Imaginá que sos el cielo. Los pensamientos son nubes que pasan. Vos no sos los pensamientos." },
        { pose: "Observá sin juzgar",            guia: "Si aparece preocupación, miedo o distracción, notalo: 'ahí está'. Y dejalo ir." },
        { pose: "La respiración como ancla",     guia: "Cuando te perdás, volvé a sentir el aire entrando y saliendo. Es tu punto de regreso." },
        { pose: "Estás aquí",                    guia: "No en el pasado, no en el futuro. En este aliento, en este momento. Eso es todo." }
      ]
    },
    {
      id: "meditacion_lugar_seguro",
      nombre: "Lugar Seguro",
      descripcion: "Visualización guiada para crear un refugio mental de paz y calma profunda.",
      cientifico: "La visualización activa las mismas redes neuronales que la experiencia real, generando respuestas fisiológicas de relajación.",
      tiempoPorPaso: 22,
      pasos: [
        { pose: "Tres respiraciones",      guia: "Cerrá los ojos. Inhalá profundo, exhalá despacio. Hacelo tres veces, soltando el día con cada exhalación." },
        { pose: "Imaginá un lugar",        guia: "Dejá que aparezca un lugar donde te sentís completamente seguro y en paz. Puede ser real o inventado." },
        { pose: "Los colores y la luz",    guia: "¿Qué colores ves? ¿Hay luz natural? Dejá que la imagen se vuelva más nítida, más detallada." },
        { pose: "Los sonidos",             guia: "¿Qué escuchás en ese lugar? Puede ser silencio, viento, agua, pájaros. Escuchalos con atención." },
        { pose: "El aire y la temperatura",guia: "¿Cómo es el aire? ¿Hay brisa? ¿Es cálido o fresco? Sentí esa temperatura sobre tu piel." },
        { pose: "Explorá despacio",        guia: "Caminá mentalmente por ese lugar. Notá los detalles: el suelo, las texturas, lo que te rodea." },
        { pose: "Este lugar es tuyo",      guia: "Guardá este lugar en tu memoria. Podés volver cuando lo necesites, en cualquier momento." },
        { pose: "Regresá suavemente",      guia: "Mové suavemente los dedos. Tomá una respiración profunda. Cuando estés listo, abrí los ojos." }
      ]
    },
    {
      id: "meditacion_rio",
      nombre: "El Río de los Pensamientos",
      descripcion: "Para cuando la mente no para: observá tus pensamientos fluir sin engancharte en ellos.",
      cientifico: "La distancia cognitiva reduce la fusión con los pensamientos, un mecanismo clave en la Terapia de Aceptación y Compromiso (ACT).",
      pasos: [
        { pose: "Posición cómoda",         guia: "Sentate con la espalda recta. Apoyá las manos sobre las rodillas. Cerrá suavemente los ojos." },
        { pose: "Imaginá un río",          guia: "Visualizá un río tranquilo. El agua fluye suave y constante. Vos estás sentado en la orilla, observando." },
        { pose: "Las hojas en el agua",    guia: "Cada pensamiento que aparezca, ponelo mentalmente sobre una hoja. Mirá cómo flota río abajo." },
        { pose: "Sin aferrarte",           guia: "No intentes detener las hojas ni empujarlas. Solo observalas pasar. Los pensamientos no son vos." },
        { pose: "Si te perdés",            guia: "Si te enganchás en un pensamiento, no hay problema. Volvé a la orilla del río. Eso es exactamente meditar." },
        { pose: "La corriente sigue",      guia: "Los pensamientos siguen fluyendo. Vos permanecés en la orilla, quieto, en calma, en paz." },
        { pose: "Regresá al cuerpo",       guia: "Sentí el peso de tu cuerpo. Escuchá los sonidos del ambiente. Abrí los ojos despacio." }
      ]
    },
    {
      id: "meditacion_metta",
      nombre: "Amor y Compasión (Metta)",
      descripcion: "Cultivá amor incondicional hacia vos y hacia otros. Ideal para aliviar la autocrítica.",
      cientifico: "La meditación Metta aumenta las emociones positivas y la conectividad en regiones cerebrales vinculadas a la empatía.",
      tiempoPorPaso: 22,
      pasos: [
        { pose: "Preparación",             guia: "Cerrá los ojos. Ponete cómodo. Llevá tu atención al centro de tu pecho, donde sentís las emociones." },
        { pose: "Amor hacia vos",          guia: "Decite mentalmente: 'Que esté bien. Que esté sano. Que esté en paz.' Sentí el peso de esas palabras." },
        { pose: "Calidez en el corazón",   guia: "Imaginá un calor suave expandiéndose en tu pecho. Una luz que crece con cada respiración." },
        { pose: "Alguien querido",         guia: "Traé a alguien que amás. Enviáles esa calidez. 'Que estés bien. Que estés en paz.'" },
        { pose: "Alguien neutral",         guia: "Pensá en alguien conocido pero no cercano. Un vecino, un compañero. Enviáles la misma calidez." },
        { pose: "Alguien difícil",         guia: "Si podés, pensá en alguien con quien tenés conflicto. No hay que resolver nada. Solo: 'Que estés bien.'" },
        { pose: "Toda la humanidad",       guia: "Expandí ese amor a todos los seres. En este momento, alguien más también sufre. Y también merece paz." },
        { pose: "Volvé a vos",             guia: "Regresá al calor en tu pecho. Ese amor empieza y termina en vos. Respirá profundo y abrí los ojos." }
      ]
    },
    {
      id: "meditacion_stop",
      nombre: "Pausa STOP",
      descripcion: "Una pausa de un minuto para resetear en medio de cualquier momento difícil.",
      cientifico: "La técnica STOP (Stop, Take a breath, Observe, Proceed) es una práctica basada en MBSR usada para interrumpir el ciclo del estrés agudo.",
      tiempoPorPaso: 18,
      pasos: [
        { pose: "S — Stop",                guia: "Detené lo que estás haciendo. Por estos minutos, no hay nada más importante que este momento." },
        { pose: "T — Tomá aire",           guia: "Inhalá profundo por la nariz. Exhalá lento por la boca. Tres veces. Sin apuro." },
        { pose: "O — Observá el cuerpo",   guia: "¿Dónde sentís tensión? ¿En el cuello, la mandíbula, el pecho? Solo notalo, sin cambiarlo." },
        { pose: "O — Observá la mente",    guia: "¿Qué pensamientos están ahí? ¿Qué emociones? Nombralos mentalmente: 'preocupación', 'cansancio', 'apuro'." },
        { pose: "P — Presente",            guia: "Sentí los tres puntos de contacto: pies en el piso, espalda en el asiento, manos donde están." },
        { pose: "Aquí y ahora",            guia: "El pasado ya fue. El futuro aún no llegó. En este instante, estás bien. Respirá eso." },
        { pose: "Seguís adelante",         guia: "Tomá una última respiración consciente. Ahora podés volver a tu día, más centrado y más vos." }
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
            animacion: "/static/assets/haciaAtras.mp4"
        },
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
  ],
  lectura: [
    {
      id: "lectura_motivacion",
      nombre: "Motivación",
      emoji: "🔥",
      descripcion: "Frases para encender la acción, el coraje y las ganas de seguir.",
      quotes: [
        { quote: "No esperés el momento perfecto. Tomá el momento y hacélo perfecto.", author: "Anónimo" },
        { quote: "Todo lo que querés está del otro lado del miedo.", author: "Jack Canfield" },
        { quote: "Empezá desde donde estás. Usá lo que tenés. Hacé lo que podés.", author: "Arthur Ashe" },
        { quote: "Un año después vas a desear haber empezado hoy.", author: "Karen Lamb" },
        { quote: "Caé siete veces, levantate ocho.", author: "Proverbio japonés" },
        { quote: "El dolor de la disciplina pesa onzas. El dolor del arrepentimiento pesa toneladas.", author: "Jim Rohn" },
        { quote: "El éxito no es definitivo, el fracaso no es fatal. Lo que cuenta es el coraje de continuar.", author: "Winston Churchill" },
        { quote: "Sos capaz de cosas increíbles. Empezá por creerlo.", author: "Anónimo" },
        { quote: "La acción es el antídoto del miedo.", author: "Robin Sharma" },
        { quote: "No te preocupés por los fracasos. Preocupate por las chances que perdés cuando ni siquiera intentás.", author: "Jack Canfield" }
      ]
    },
    {
      id: "lectura_diaria",
      nombre: "Lectura Diaria",
      emoji: "🌅",
      descripcion: "Reflexiones simples para arrancar el día o encontrar calma en cualquier momento.",
      quotes: [
        { quote: "Cada día es un nuevo comienzo. Cada momento, una oportunidad.", author: "Anónimo" },
        { quote: "La gratitud transforma lo que tenemos en suficiente.", author: "Melodie Beattie" },
        { quote: "Pequeños progresos cada día suman grandes resultados.", author: "Anónimo" },
        { quote: "Cuidarte a vos mismo no es egoísmo. Es supervivencia.", author: "Audre Lorde" },
        { quote: "La vida es 10% lo que nos pasa y 90% cómo respondemos.", author: "Charles R. Swindoll" },
        { quote: "Quien mira afuera, sueña. Quien mira adentro, despierta.", author: "Carl Jung" },
        { quote: "Hacé lo mejor que puedas hasta que sepas más. Cuando sepas más, hacelo mejor.", author: "Maya Angelou" },
        { quote: "Hace falta coraje para crecer y convertirte en quien realmente sos.", author: "E.E. Cummings" },
        { quote: "La felicidad no es un destino. Es una forma de viajar.", author: "Margaret Lee Runbeck" },
        { quote: "Una cosa a la vez, un día a la vez. Eso es todo lo que se puede pedir.", author: "Anónimo" }
      ]
    },
    {
      id: "lectura_espiritual",
      nombre: "Espiritualidad",
      emoji: "✨",
      descripcion: "Sabiduría estoica, budista y contemplativa para el crecimiento interior.",
      quotes: [
        { quote: "No son las cosas las que nos perturban, sino las opiniones que tenemos de ellas.", author: "Epicteto" },
        { quote: "El obstáculo es el camino.", author: "Marco Aurelio" },
        { quote: "La mente es todo. En lo que pensás, te convertís.", author: "Buda" },
        { quote: "Entre el estímulo y la respuesta hay un espacio. En ese espacio está nuestra libertad.", author: "Viktor Frankl" },
        { quote: "Tenés poder sobre tu mente, no sobre los eventos exteriores. Date cuenta y encontrarás fuerza.", author: "Marco Aurelio" },
        { quote: "Cuando soltás lo que sos, te convertís en lo que podrías ser.", author: "Lao Tzu" },
        { quote: "La llama que me quema también me ilumina.", author: "Viktor Frankl" },
        { quote: "No podés detener las olas, pero podés aprender a surfear.", author: "Jon Kabat-Zinn" },
        { quote: "El presente siempre será. Eso es todo lo que necesitás saber.", author: "Eckhart Tolle" },
        { quote: "Vive como si todo estuviera orquestado a tu favor.", author: "Rumi" }
      ]
    },
    {
      id: "lectura_autocompasion",
      nombre: "Autocompasión",
      emoji: "💚",
      descripcion: "Amor propio, sanación y gentileza hacia uno mismo.",
      quotes: [
        { quote: "Tratate con la misma amabilidad con la que tratarías a un buen amigo.", author: "Kristin Neff" },
        { quote: "No tenés que ganarte el derecho a descansar.", author: "Anónimo" },
        { quote: "Sos humano. Cometés errores. Aprendés. Crecés. Eso es todo lo que se te pide.", author: "Anónimo" },
        { quote: "La gentileza hacia vos mismo es el principio de toda sanación.", author: "Thich Nhat Hanh" },
        { quote: "Merecés el amor que tanto intentás darles a los demás.", author: "Rupi Kaur" },
        { quote: "Tu imperfección no es un defecto. Es parte de lo que te hace real.", author: "Brené Brown" },
        { quote: "Sanar no es lineal. Algunos días retrocedés. Eso también es parte del camino.", author: "Anónimo" },
        { quote: "Nadie puede estar en paz con el mundo si no está en paz con sí mismo.", author: "Dalai Lama" },
        { quote: "El amor que le das al mundo empieza con el amor que te das a vos mismo.", author: "Anónimo" },
        { quote: "Herirte con la autocrítica no te hace mejor. Te hace más pequeño.", author: "Tara Brach" }
      ]
    }
  ]
};