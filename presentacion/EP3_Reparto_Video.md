# EP3 Equipo 1: reparto del video

**Integrantes:** Martin Higuera, Gabriel Durán, Francisco Salazar.
**Fecha de entrega:** martes 01 de diciembre de 2026.
**Formato:** video grabado por partes, cada integrante graba su bloque y luego se une. Tope sugerido: 15 min (confirmar con el docente).
**Captura por consola:** las capturas salen de CloudShell con `aws/09_evidencia.sh` (un bloque `=== [N]` por captura).

## Bloques del video

| Parte | Responsable | Tiempo | Qué muestra |
|---|---|---|---|
| 1 | Martin | 0:00-4:00 | Problema, dataset, arquitectura (diagrama) y pipeline de entrenamiento en SageMaker |
| 2 | Gabriel | 4:00-9:00 | Modelo (métricas P@5, recall, F1 vs popularidad), servicio FastAPI, Swagger y dashboard |
| 3 | Francisco | 9:00-13:00 | RabbitMQ y consumidor (Docker local), seguridad (API key, rate limit), pruebas de carga Locust (local) y CloudWatch |
| 4 | Martin | 13:00-15:00 | Demo en vivo con curl en AWS (401, 200, 404, 400), costo real (USD 0,026) y cierre |

## Tareas (1-12)

| # | Tarea | Responsable | Qué mostrar en el video | Captura |
|---|---|---|---|---|
| 1 | Pipeline de datos y entrenamiento (`02_run.py`) | Martin | Job SageMaker Completed y su log | [2] |
| 2 | Publicación del modelo y Lambda (`03`, `04`) | Martin | Modelo en S3 y configuración de la Lambda | [3], [4] |
| 3 | Métricas del modelo (P@5, recall, F1) | Gabriel | Tabla comparativa con popularidad | (figura del informe) |
| 4 | Servicio FastAPI y pruebas pytest | Gabriel | `/docs` y resultado de pytest (47 pasan) | — |
| 5 | Dashboard y Swagger/OpenAPI | Gabriel | Dashboard en la página y Swagger | — |
| 6 | RabbitMQ y consumidor (`docker compose`, `05`, `06`) | Francisco | POST /interacciones 202 y log del consumidor registrando el evento | — |
| 7 | Seguridad: API key, rate limit, TLS | Francisco | 401 sin clave, 429 con exceso | [6]-[9] |
| 8 | CloudWatch: logs y métricas de API GW | Francisco | Logs de la Lambda y Count de API GW | [10], [11] |
| 9 | Capturas de evidencia y costo real | Martin | Costo del mes en Billing | [12] |
| 10 | Informe, secciones 1-4 | Martin | Solo mención en el video | — |
| 11 | Informe, secciones 5-8 y referencias APA | Gabriel | Solo mención en el video | — |
| 12 | Presentación, guion y declaración de uso de IA | Francisco | Cierre y declaración | — |

## Preguntas del docente (preparación)

1. ¿Por qué Lambda y no un endpoint de SageMaker? Entrenamiento en SageMaker; inferencia en Lambda por costo y latencia en el laboratorio.
2. ¿Cuál es el p95 de la API? Locust local (10 usuarios, 20 s): p95 180 ms; p50 62 ms; p99 290 ms. En AWS no se midió (pendiente, se declara).
3. ¿Por qué P@5 es bajo? Densidad 0,031%; el modelo duplica a popularidad (0,0101 vs 0,0046).
4. ¿El modelo excluye productos ya comprados? Sí, en la Lambda y en el servicio.
5. ¿Cómo se protege la API? X-API-Key, rate limit 60/min, TLS en el borde.
6. ¿Qué pasa si RabbitMQ cae? POST /interacciones responde 503.
7. ¿Licencia del dataset? No declarada; se cita al autor (arXiv 2403.03952).
8. ¿Costo mensual? Cifra real del Learner Lab (captura [12]).
9. ¿Por qué ALS y no deep learning? Con 412.947 interacciones y densidad 0,031%, la factorización basta y es verificable.
10. ¿Cómo se reentrena? Nuevo job de SageMaker y `03_publicar_modelo.sh`.
11. ¿Qué mide CloudWatch? Count y 4xx de API GW, logs y duración de la Lambda.
12. ¿Qué no funciona aún? Locust contra AWS, JMeter, throttling de API GW sin verificar y desglose de costos por servicio: se declaran en el informe.

## Pendientes antes de grabar

- Confirmar tope de tiempo con el docente.
- Ejecutar `09_evidencia.sh` en CloudShell (con `API_KEY` exportada) y tomar las capturas.
- Capturas pendientes del informe (Figuras 3-10): SageMaker, Lambda, API GW, curl, dashboard, Swagger, CloudWatch, Cost Explorer.
- Fecha de entrega: martes 01 de diciembre de 2026.
