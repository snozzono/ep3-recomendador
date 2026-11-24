# EP3 Equipo 1: libreto del video

**Integrantes:** Martin Higuera, Gabriel Durán, Francisco Salazar.
**Entrega:** martes 01 de diciembre de 2026.
**Tope:** 15 minutos. Repositorio: https://github.com/snozzono/ep3-recomendador

## Antes de grabar: pantallas y comandos listos

- CloudShell con `cd ~/ep3/aws && source ~/venv-sm/bin/activate` y `export API_KEY=<clave>` (no mostrar la clave en pantalla: usar `export API_KEY=...` fuera de cuadro o cubrirla).
- `bash 09_evidencia.sh` ya ejecutado; capturas de los bloques [1] a [12].
- Terminal local en el repo con `.venv` activo: `python -m pytest tests -q` (47 passed).
- Terminal local con `uvicorn` (127.0.0.1:8000) o `docker compose up -d` listo.
- Navegador en `http://127.0.0.1:8000/docs` (Swagger) y `http://127.0.0.1:8000/dashboard`.
- Consola de SageMaker (job ep3-svd-2026-11-24-15-45-45-251) y de Lambda/API Gateway, abiertas en pestañas.
- Informe y presentación en PDF listos para mostrar.

## Bloque 1 · Martin · 0:00 a 4:00

**Tiempo:** 4 min. **Tema:** problema, dataset, arquitectura y entrenamiento.

**Texto:**
"Somos el equipo 1. Nuestro sistema recomienda productos industriales y científicos a partir de reseñas de Amazon. Usamos el dataset Amazon Reviews 2023, categoría Industrial and Scientific, en su versión 5-core: 412.947 interacciones, 50.985 usuarios y 25.848 productos. La densidad es muy baja, 0,031 %, así que el problema es difícil. La arquitectura tiene cuatro piezas: entrenamiento en SageMaker, un modelo publicado en S3, una Lambda que calcula recomendaciones y una API HTTP en API Gateway. Además, un servicio FastAPI local y RabbitMQ para registrar interacciones. El entrenamiento usa factorización ALS implícita con 32 factores, y corrió como job de SageMaker en una instancia ml.t3.large."

**[PANTALLA]:** diagrama de arquitectura del informe → consola SageMaker, job `ep3-svd-2026-11-24-15-45-45-251` en estado Completed (captura [2]).

## Bloque 2 · Gabriel · 4:00 a 9:00

**Tiempo:** 5 min. **Tema:** modelo, servicio, pruebas y dashboard.

**Texto:**
"Evaluamos con partición 80/20 y semilla 42. La métrica principal es Precision@5: de los cinco productos recomendados, cuántos resultan relevantes, con relevancia igual a rating 4 o más, y solo entre productos no vistos. El modelo ALS obtiene 0,0101, frente a 0,0046 de la popularidad. Es más del doble, aunque el valor absoluto es bajo por la densidad del dataset. Recall es 0,0258 contra 0,0118, y F1 0,0145 contra 0,0066. La exactitud, 0,9997, no sirve como argumento porque casi todos los productos son negativos. El servicio expone GET /recomendar, POST /interacciones, /salud, /docs y el dashboard. Esta corrida de pytest pasó 47 pruebas."

**[PANTALLA]:** `python -m pytest tests -q` → `47 passed` → `http://127.0.0.1:8000/docs` (Swagger) → `/dashboard`.

## Bloque 3 · Francisco · 9:00 a 13:00

**Tiempo:** 4 min. **Tema:** RabbitMQ, seguridad, carga y CloudWatch.

**Texto:**
"Las interacciones se publican en la cola de RabbitMQ y un consumidor las registra. Aquí publicamos un evento: la API responde 202, y el consumidor lo registra en su log. Si RabbitMQ cae, la API responde 503. Para seguridad, cada petición lleva X-API-Key; sin clave la respuesta es 401. Hay un límite de 60 peticiones por minuto por IP, y al excederlo responde 429 con Retry-After. En AWS, API Gateway termina HTTPS. Para carga usamos Locust en local, con 10 usuarios durante 20 segundos: 246 peticiones, cero fallos, p50 62 ms, p95 180 ms y p99 290 ms. En AWS no hicimos esa medición y lo declaramos en el informe. Por último, CloudWatch muestra la duración de la Lambda, que va de 1,9 ms a 1,1 s en las invocaciones registradas, y el conteo de peticiones de API Gateway."

**[PANTALLA]:** `docker compose up -d` → `curl -X POST .../interacciones` (202) → `docker compose logs consumidor` → Locust (tabla de resultados) → CloudWatch (captura [10] y [11]).

## Bloque 4 · Martin · 13:00 a 15:00

**Tiempo:** 2 min. **Tema:** demo en AWS y cierre.

**Texto:**
"Esta es la demo en AWS. Sin clave, la API responde 401. Con clave y un usuario existente, responde 200 con diez recomendaciones. Con un usuario que no existe, responde 404, y sin el parámetro usuario, 400. El costo del Learner Lab en este mes es de 0,026 dólares. El informe, el libreto y el repositorio están en GitHub. Gracias."

**[PANTALLA]:** `bash 09_evidencia.sh` bloques [6] a [9] (401, 200, 404, 400) → captura [12] (costo).

## Checklist de grabación

- Resolución 1080p, formato MP4, subido a AVA con el nombre `EP3_Video_Equipo1.mp4`.
- Cada integrante graba su bloque por separado y luego se unen.
- Verificar antes de grabar que la API key no aparezca en pantalla.
- Mostrar en portada nombres y RUT de los tres integrantes.
- Los tiempos de cada bloque deben cuadrar con el total de 15 minutos.
- Si la demo en AWS falla durante la grabación, usar las capturas ya tomadas y decirlo en el video.
