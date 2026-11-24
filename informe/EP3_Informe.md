# EP3 — Despliegue y Optimización de Sistema IA Empresarial

- **Integrantes (Equipo 1):** Martin Higuera, Gabriel Durán, Francisco Salazar
- **Repositorio:** https://github.com/snozzono/ep3-recomendador
- **Fecha de entrega:** [COMPLETAR EQUIPO]

## 1. Caso empresarial y objetivos

ShopFast, un comercio electrónico de productos industriales y científicos, necesita sugerir a cada cliente productos que puedan interesarle. El sistema de recomendación diseñado en EP1 y EP2 se implementa en este EP3 como un servicio desplegado en la nube: el modelo se entrena en Amazon SageMaker, se publica como artefacto en S3 y se consume mediante una API REST en AWS (Lambda + API Gateway).

Objetivos de esta etapa:

- Entrenar un modelo de filtrado colaborativo sobre un dataset real y publicarlo en AWS (IE1, IE4).
- Exponer las recomendaciones mediante una API REST documentada, con autenticación por clave (IE7).
- Medir calidad del modelo (ranking frente a un baseline de popularidad) y rendimiento de la API (IE10).

El alcance es un prototipo académico. No hay usuarios reales de ShopFast ni integración con su catálogo: la API devuelve identificadores de producto (`parent_asin`), no nombres.

## 2. Modelo de IA implementado (IE1, IE2)

**Tipo y framework.** Filtrado colaborativo implícito con factorización de matrices por mínimos cuadrados alternos (ALS implícito, Hu et al., 2008). El entrenamiento corre en Amazon SageMaker con la implementación en numpy de `aws/02_entrenar_sagemaker.py`. La evaluación local usa la librería `implicit` (`modelo/ALS_eval.py`) como verificación cruzada. El nombre del job (`ep3-svd-…`) y del archivo (`modelo_svd-….npz`) son nombres heredados: el algoritmo es ALS, no SVD.

**Dataset.** Amazon Reviews 2023, categoría *Industrial_and_Scientific*, versión 5-core (Hou et al., 2024). Tras cargar y filtrar: 412 947 interacciones, 50 985 usuarios y 25 848 productos. La densidad de la matriz usuario-producto es de 0,031 %. El filtro 5-core no eliminó filas. La licencia del dataset no está declarada en la fuente; el equipo lo usa solo con fines académicos [COMPLETAR EQUIPO: confirmar términos de uso].

**Proceso y parámetros.**

| Parámetro | Valor |
|---|---|
| Partición | Aleatoria 80/20, semilla 42 (entrenamiento 330 358; prueba 82 589) |
| Factores latentes (k) | 32 |
| Regularización | 0,01 |
| Iteraciones | 15 |
| Confianza | Valor de rating en entrenamiento |
| Candidatos por usuario | Productos no vistos en entrenamiento |

**Entrenamiento en SageMaker.** Job `ep3-svd-2026-11-24-15-45-45-251` en estado *Completed*, instancia `ml.t3.large`, duración de 215 s. El modelo publicado es `s3://ep2-equipo1-128688195152/modelos/modelo_svd-20261124-155354.npz`, con matrices U (usuarios × k) y V (productos × k), identificadores y el historial de productos vistos.

**Interpretabilidad para la decisión.** La puntuación de un producto para un usuario es el producto punto entre el vector latente del usuario y el del producto (`score = U_u · V_i`). Los productos ya vistos se excluyen antes de ordenar. La API devuelve el `score` junto a cada producto, de modo que el equipo de negocio puede priorizar campañas por puntuación. El score no se traduce a una explicación en lenguaje natural: es una medida de afinidad, no una razón de compra. En la versión local, si el archivo del modelo no existe, la API responde con un respaldo por popularidad; la Lambda no implementa ese respaldo.

**Resultados de clasificación y ranking** (partición de prueba; 36 454 usuarios con al menos un producto relevante, rating ≥ 4; 942 millones de pares candidatos evaluados):

| Métrica | ALS (k=32) | Popularidad |
|---|---|---|
| Precision@5 | **0,0101** | 0,0046 |
| Precision (agregada) | **0,0101** | 0,0046 |
| Recall (agregado) | **0,0258** | 0,0118 |
| F1 | **0,0145** | 0,0066 |
| Recall@5 (media por usuario) | **0,0269** | 0,0125 |
| Accuracy | 0,9997 | 0,9997 |

La accuracy no sirve como argumento: el 99,9 % de los pares son negativos verdaderos, así que cualquier modelo que no recomiende nada obtiene una accuracy casi igual. El criterio útil es precision, recall y F1. ALS mejora a popularidad en las tres métricas, aunque en términos absolutos la mejora es modesta, consistente con un catálogo de 25 848 productos y una matriz muy dispersa.

**Baseline SVD.** Una descomposición SVD sobre la matriz con ceros en los no observados da Precision@5 de 0,0061 (sobre popularidad 0,0046; ALS sigue siendo superior). Su RMSE de predicción de rating es 4,56 sin recorte y 3,61 recortado a [1, 5], frente a 1,08 de predecir la media global. El modelo se optimiza para ranking de productos observados, no para predecir ratings; por eso el sistema se compara por ranking y no por error de rating.

## 3. Despliegue en AWS (IE4, IE5)

| Componente | Recurso | Estado verificado |
|---|---|---|
| Entrenamiento | SageMaker, `ml.t3.large` | Job *Completed* en 215 s |
| Artefacto | S3 `modelos/modelo_svd-20261124-155354.npz` | Publicado |
| Cómputo | Lambda `ep3-recomendador`, Python 3.12, 512 MB | Activa, con `API_KEY` en variables de entorno |
| Entrada | API Gateway HTTP API `ep3-recomendador-api` (`b10f7xg6u4`) | Rutas respondiendo; HTTPS terminado aquí |
| Registros | CloudWatch `/aws/lambda/ep3-recomendador` | [COMPLETAR EQUIPO: captura] |

**Flujo de consumo.** (1) El cliente envía `GET /recomendar?usuario=<id>` con la cabecera `X-API-Key` a API Gateway por HTTPS. (2) API Gateway invoca la Lambda. (3) La Lambda valida la clave; si falta o es incorrecta responde 401 sin consultar el modelo. (4) Sin el parámetro `usuario` responde 400. (5) Si es válida, la Lambda carga el modelo desde S3 en la primera invocación y lo guarda en una variable global, de modo que las invocaciones siguientes en la misma instancia no lo vuelven a descargar. Calcula U·Vᵀ para el usuario, excluye los productos ya vistos y devuelve los 10 con mayor score. (6) Si el usuario no existe, responde 404. La versión desplegada **no** acepta el parámetro `n`: devuelve siempre 10. El parámetro `n` (1–100) solo existe en la versión local.

**Pruebas de despliegue.** Sin clave: 401. Con clave y usuario existente: 200 con 10 recomendaciones. Con clave y usuario inexistente (999 999 999): 404. Ejemplo de respuesta para el usuario `AFNT6Z…` [COMPLETAR EQUIPO: pegar ID completo y JSON completo]:

```json
{"usuario": "AFNT6Z…", "recomendaciones": [{"parent_asin": "…", "score": 0.0}, "… 10 elementos …"]}
```

**Estrategia de despliegue y consumo.** Entrenamiento batch en SageMaker, publicación del artefacto en S3 y servicio ligero en Lambda. La inferencia es una multiplicación de matrices y una ordenación, sin necesidad de GPU ni de un contenedor dedicado. Un endpoint de SageMaker en tiempo real cobra por hora aunque nadie consulte, mientras que la Lambda cobra por invocación. [COMPLETAR EQUIPO: confirmar que esta es la justificación del grupo y añadir la alternativa comparada, si la hubo.]

**Escalabilidad y costos (IE4).** La Lambda escala por concurrencia de forma automática. [COMPLETAR EQUIPO: costo mensual estimado o real del Learner Lab por servicio (SageMaker, Lambda, API Gateway, S3, CloudWatch), con captura de Cost Explorer o Billing.] No se midió el comportamiento de escalado bajo carga en AWS: la prueba de carga descrita en la sección 5 se ejecutó contra el servicio local.

## 4. Integración de servicios y seguridad (IE7)

**Arquitectura de servicios.** Además de la API en AWS, el repositorio incluye una versión de contenedores con Docker Compose: API FastAPI, consumidor y RabbitMQ (cola `interacciones`). Los eventos de interacción (`POST /interacciones`) se publican en RabbitMQ con `pika` y el consumidor los registra en `eventos.jsonl`, que alimenta el respaldo por popularidad. La mensajería no se usa en la demostración AWS: RabbitMQ en EC2 es opcional en el repositorio y no forma parte del flujo de recomendación verificado en la nube. No se usa Kafka.

**Autenticación.** `/recomendar` e `/interacciones` exigen la cabecera `X-API-Key`. Sin clave o con clave incorrecta responden 401. La comparación usa `hmac.compare_digest` para evitar ataques de temporización. Las rutas públicas son `/salud`, `/docs`, `/openapi.json` y `/dashboard`.

**Cifrado en tránsito.** En AWS, API Gateway termina TLS (HTTPS). En la versión local con Docker el servicio responde en HTTP plano; esto se declara como limitación.

**Limitación de tasa (rate limiting).** En la versión local, un limitador en memoria permite 60 peticiones por minuto por IP (`RATE_LIMIT_POR_MINUTO`) y responde 429 con `Retry-After`. Sus límites: el contador es por proceso y, detrás de un proxy, cuenta la IP del proxy. **En la API desplegada en AWS no se verificó un límite de tasa**: [COMPLETAR EQUIPO: indicar si se configuró throttling en API Gateway o declarar que no está activo].

**Documentación de la interfaz.** El esquema OpenAPI exportado (`docs/openapi.json`) describe `/salud`, `/recomendar` e `/interacciones`. Swagger está disponible en `/docs` en la versión local.

**Flujo de secuencia (texto).** Cliente → API Gateway (HTTPS, valida ruta) → Lambda (valida `X-API-Key`) → S3 (carga del `.npz` si no está en caché) → modelo (U·Vᵀ, excluye vistos, top-n) → respuesta JSON al cliente. [COMPLETAR EQUIPO: insertar diagrama de secuencia en PlantUML con el flujo anterior.]

## 5. Pruebas y calidad (IE10)

**Pruebas unitarias y de API.** `python -m pytest tests -q` ejecuta 43 pruebas con Python 3.12, todas aprobadas. Cubren el recomendador (incluido que `recomendar` excluye productos vistos), la autenticación (401 sin clave y con clave incorrecta, 200 con clave correcta), el límite de tasa (429), la validación de entrada (422) y el publicador/consumidor de RabbitMQ con el publicador simulado.

**Pruebas de integración en Docker.** `docker compose up -d --build` levanta RabbitMQ, API y consumidor. Verificado en local: `/recomendar` sin clave → 401, con clave → 200; `/salud` → 200; `/dashboard` → 200; `/interacciones` sin clave → 401, con clave → 202.

**Pruebas de carga (Locust, local).** 20 usuarios concurrentes durante 30 s, con clave, sobre la API local (`http://localhost:8000`). La corrida usó `RATE_LIMIT_POR_MINUTO=100000`, porque 20 usuarios desde una misma IP superan el límite por defecto (60/min); con el límite por defecto, una corrida de prueba devolvió 429 en el 94 % de las peticiones (esa corrida no quedó guardada en el repositorio).

| Endpoint | Peticiones | Fallos | Mediana | p95 | p99 | Máximo |
|---|---|---|---|---|---|---|
| `GET /recomendar` | 787 | 0 | 30 ms | 160 ms | 210 ms | 330 ms |
| `POST /interacciones` | 169 | 0 | 63 ms | 220 ms | 240 ms | 350 ms |
| **Agregado** | **956** | **0** | **36 ms** | **170 ms** | **220 ms** | **350 ms** |

Throughput agregado: 32,5 peticiones/s. Latencia media agregada: 52,5 ms. Estas cifras son de la máquina de desarrollo sobre Docker/Windows; **no son latencias de AWS**. [COMPLETAR EQUIPO: si se ejecuta Locust contra API Gateway, reemplazar o añadir la tabla con p50, p95 y p99 de AWS.]

**Métricas del modelo.** Véase la sección 2. Cumplen los cuatro indicadores exigidos: accuracy (con la advertencia ya indicada), precision, recall y F1.

**Oportunidades de optimización.**

1. Medir el arranque en frío (descarga del `.npz` desde S3 y construcción del diccionario de usuarios) y, si es alto, ajustar la memoria de la Lambda o usar concurrencia aprovisionada. El modelo ya se cachea entre invocaciones de la misma instancia.
2. Ajustar k y la regularización con validación cruzada: el modelo se entrenó con k=32 y reg=0,01 sin búsqueda de hiperparámetros.
3. Reducir la brecha de cobertura: el 99,9 % de los pares son negativos y el modelo recomienda sobre un catálogo grande; un re-ranking por categoría o por popularidad reciente podría mejorar el recall.
4. Medir costos y latencia en AWS con carga real antes de decidir el tamaño de la Lambda (512 MB).

## 6. Evidencias

| Evidencia exigida | Estado |
|---|---|
| Captura: job de SageMaker *Completed* | [COMPLETAR EQUIPO] |
| Captura: Lambda y configuración (runtime, memoria) | [COMPLETAR EQUIPO] |
| Captura: API Gateway (rutas, integración) | [COMPLETAR EQUIPO] |
| Captura: respuestas 401, 200 y 404 (curl o Postman) | [COMPLETAR EQUIPO] |
| Captura: dashboard con resultados | [COMPLETAR EQUIPO] |
| Logs de CloudWatch de la Lambda | [COMPLETAR EQUIPO] |
| Captura de costos (Billing o Cost Explorer) | [COMPLETAR EQUIPO] |

## 7. Limitaciones

- **Dispersión y catálogo grande.** Densidad de 0,031 %. Las métricas absolutas son bajas (Precision@5 de 0,0101); la mejora frente a popularidad es real pero pequeña.
- **Versión desplegada.** La Lambda devuelve siempre 10 productos y no tiene el parámetro `n` ni el respaldo por popularidad de la versión local.
- **Nombres de producto.** La API devuelve `parent_asin`. Los nombres requieren el archivo de metadatos del dataset, que no se descargó.
- **Exclusión de vistos.** La versión inicial de la Lambda no excluía los productos ya vistos. Se corrigió antes de la entrega y el criterio se cubre con una prueba automatizada en el repositorio.
- **Mensajería en la nube.** RabbitMQ no está desplegado en AWS para la demostración: el flujo de eventos se verificó solo en Docker local.
- **TLS y límite de tasa.** TLS termina en API Gateway. El límite de tasa se verificó solo en el servicio local.
- **Carga en AWS.** Las pruebas de carga se hicieron en local; no hay medición de escalado en AWS.
- **Reentrenamiento.** Los eventos de interacción se registran, pero el modelo no se reentrena automáticamente.
- **Licencia del dataset.** No declarada en la fuente; uso académico.

## 8. Conclusiones

El sistema queda desplegado en AWS con un modelo entrenado en SageMaker, publicado en S3 y servido por una API REST con autenticación. El modelo supera a un baseline de popularidad en precision, recall y F1, y la API responde los tres casos de prueba (401, 200, 404). Los puntos débiles son la magnitud de la mejora, la falta de medición de carga en AWS y la ausencia de límite de tasa verificado en la nube. [COMPLETAR EQUIPO: decisión de equipo o aprendizajes, si se quiere cerrar con una reflexión propia.]

## 9. Referencias

Hou, Y., Li, J., He, Z., Yan, A., Chen, X., & McAuley, J. (2024). *Bridging language and items for retrieval and recommendation* (arXiv:2403.03952). arXiv. https://doi.org/10.48550/arXiv.2403.03952

Hu, Y., Koren, Y., & Volinsky, C. (2008). Collaborative filtering for implicit feedback datasets. En *Proceedings of the 8th IEEE International Conference on Data Mining (ICDM)* (pp. 263–272). IEEE. https://doi.org/10.1109/ICDM.2008.22

Koren, Y., Bell, R., & Volinsky, C. (2009). Matrix factorization techniques for recommender systems. *Computer, 42*(8), 30–37. https://doi.org/10.1109/MC.2009.263

## 10. Declaración de uso de IA generativa

El equipo usó un asistente de IA (modelo de lenguaje) para redactar borradores de este informe y de la presentación, y para generar parte del código de las herramientas de generación de PDF y del servicio. Todas las cifras se tomaron de los archivos del repositorio (`modelo/`, `tests/`, `aws/`) y de la ejecución en AWS, y fueron verificadas por el equipo. Las decisiones de diseño y las conclusiones son responsabilidad del equipo.
