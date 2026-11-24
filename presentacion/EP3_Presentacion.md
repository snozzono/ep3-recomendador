# EP3 — Recomendador de productos desplegado en AWS

ITY1102 · Arquitectura de Sistemas de IA · Equipo 1
Martin Higuera · Gabriel Durán · Francisco Salazar
Defensa: 15 minutos + demostración en vivo

---

## Caso y arquitectura desplegada (IE3)

- **Caso:** ShopFast necesita sugerir productos industriales y científicos a cada cliente.
- **Flujo:** SageMaker entrena → S3 guarda el modelo → Lambda calcula → API Gateway expone → cliente consume.
- **Estrategia:** entrenamiento batch y servicio ligero. Sin servidor encendido: el costo sigue al uso.
- **Aporte a la decisión:** top 10 por usuario con score de afinidad, sin productos ya vistos.

---

## Modelo: ALS implícito y resultados (IE1, IE10)

Dataset: Amazon Reviews 2023, Industrial and Scientific, 5-core (Hou et al., 2024). 412 947 interacciones · 50 985 usuarios · 25 848 productos.

| Métrica | ALS (k=32) | Popularidad |
|---|---|---|
| Precision@5 | **0,0101** | 0,0046 |
| Recall | **0,0258** | 0,0118 |
| F1 | **0,0145** | 0,0066 |
| Accuracy | 0,9997 | 0,9997 |

Accuracy no es argumento: el 99,9 % de los pares son negativos. Criterio útil: precision, recall y F1.

---

## Demo en vivo y evidencias (IE9)

1. `curl` sin `X-API-Key` → **401**
2. `curl` con clave y usuario existente → **200**, 10 recomendaciones
3. `curl` con usuario inexistente → **404**
4. Swagger / OpenAPI (`docs/openapi.json`) y consola de SageMaker
5. Dashboard con resultados: [COMPLETAR EQUIPO: versión local, o alojar en AWS]

Respaldo: capturas en el informe (sección 6).

---

## Calidad, seguridad y límites (IE8, IE11)

- **Pruebas:** 47 pruebas unitarias y de API aprobadas (incluye 401, 200, 429).
- **Carga (Locust, local, 20 usuarios, 30 s):** 956 peticiones, 0 fallos, p50 36 ms, p95 170 ms, p99 220 ms.
- **Seguridad:** clave `X-API-Key` (comparación en tiempo constante), TLS en API Gateway.
- **Límites:** la versión AWS no devuelve parámetro `n` y no tiene límite de tasa verificado. RabbitMQ no está en AWS para esta demo. Las cifras de carga son locales, no de AWS.

---

## Decisiones, costos y mejora continua (IE6, IE11)

- **Por qué AWS AIaaS:** SageMaker para el entrenamiento, Lambda para el servicio. Costo: [COMPLETAR EQUIPO: costo real del Learner Lab].
- **Próximo paso:** medir arranque en frío y carga real en AWS; ajustar k y regularización.
- **Preguntas:** [COMPLETAR EQUIPO: preguntas del docente].

Gracias
