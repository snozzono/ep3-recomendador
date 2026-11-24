# EP3 — Despliegue y Optimización de Sistema IA Empresarial

- **Integrantes (Equipo 1):** Martin Higuera, Gabriel Durán, Francisco Salazar
- **Repositorio:** https://github.com/snozzono/ep3-recomendador
- **Fecha de entrega:** martes 01 de diciembre de 2026
- **Reparto del equipo:** Martin Higuera (secciones 1–4, pipeline de entrenamiento, Lambda y API Gateway, evidencia de costos); Gabriel Durán (secciones 5–8, referencias APA, métricas del modelo, servicio FastAPI y pruebas); Francisco Salazar (seguridad, RabbitMQ, pruebas de carga, CloudWatch y declaración de uso de IA). Detalle en `presentacion/EP3_Reparto_Video.md`.

## 1. Caso empresarial, contexto y objetivos

ShopFast es un comercio electrónico de productos industriales y científicos. Su necesidad es sugerir a cada cliente productos que puedan interesarle, con una lista ordenada que el equipo de negocio pueda usar para priorizar campañas. El sistema de recomendación diseñado en EP1 y EP2 se implementa en esta etapa como un servicio desplegado en la nube: el modelo se entrena en Amazon SageMaker, se publica como artefacto en Amazon S3 y se consume mediante una API REST en AWS (API Gateway + Lambda).

Objetivos de esta etapa, con su relación con los indicadores de logro de la pauta:

- Entrenar un modelo de filtrado colaborativo sobre un dataset real y publicarlo en AWS (IE1, IE2, IE4, IE5; IL3.1, IL3.2).
- Exponer las recomendaciones mediante una API REST documentada en OpenAPI, con autenticación por clave (IE7; IL3.3).
- Integrar la comunicación asíncrona de eventos mediante RabbitMQ en la versión de contenedores (IE7; IL3.3).
- Medir calidad del modelo frente a un baseline de popularidad y el rendimiento de la API (IE10; IL3.4).

El alcance es un prototipo académico. No hay usuarios reales de ShopFast ni integración con su catálogo. La API devuelve identificadores de producto (`parent_asin`), no nombres, y las recomendaciones son una medida de afinidad, no una garantía de compra. El valor para la decisión empresarial está en ordenar productos por afinidad estimada, no en predecir con certeza qué comprará cada cliente.

**Uso en el proceso de decisión (IE3).** El flujo propuesto para el equipo de negocio tiene cuatro pasos:

1. Un sistema consumidor (por ejemplo, la tienda o un panel interno) llama a `GET /recomendar` para un usuario.
2. La API devuelve diez productos con su `score`, sin productos que el usuario ya haya visto.
3. El equipo de negocio usa el orden y el score para elegir qué productos destacar en una campaña o en una página de recomendaciones.
4. El resultado se compara con la métrica de popularidad, que es la decisión sin modelo, antes de asignar presupuesto. El modelo se justifica solo si supera ese baseline.

Este flujo no se probó con usuarios reales de ShopFast. Es la forma prevista de consumo, y es coherente con los datos medidos.

## 2. Arquitectura de la solución (IE3, IE5)

La solución tiene dos versiones que comparten el mismo modelo y el mismo contrato de API:

| Componente | Tecnología | Función | Versión |
|---|---|---|---|
| Datos | CSV Amazon Reviews 2023 (Industrial_and_Scientific, 5-core) | Fuente de interacciones usuario-producto | AWS y local |
| Entrenamiento | Amazon SageMaker, `ml.t3.large`, SKLearn 1.2-1 py3 | Ejecuta `aws/02_entrenar_sagemaker.py` (ALS en numpy) | AWS |
| Almacenamiento del modelo | Amazon S3 (`modelos/modelo_svd-20261124-155354.npz`, 11,2 MiB) | Artefacto con matrices U y V, identificadores e historial visto | AWS |
| Inferencia | AWS Lambda `ep3-recomendador`, Python 3.12, 512 MB, timeout 30 s | Valida la clave, carga el modelo, calcula el top-10 | AWS |
| Entrada | API Gateway HTTP API `ep3-recomendador-api` (ID `5uli1pw7qf`), ruta `GET /recomendar` | Termina HTTPS y reenvía a la Lambda | AWS |
| Observabilidad | CloudWatch Logs `/aws/lambda/ep3-recomendador` | Duración, memoria y fase de inicialización de cada invocación | AWS |
| API local | FastAPI (`servicio/app.py`) con Swagger en `/docs` y dashboard en `/dashboard` | Mismo servicio con `n` variable y respaldo por popularidad | Local / Docker |
| Mensajería | RabbitMQ (cola durable `interacciones`), publicador con `pika` (`servicio/mensajeria.py`) | Desacopla el registro de eventos de la respuesta HTTP | Local / Docker |
| Consumidor | `servicio/consumidor.py` | Lee la cola y escribe `eventos.jsonl` | Local / Docker |

**Conexiones.** El entrenamiento lee el dataset, escribe el modelo en S3 y termina. La Lambda lee el modelo desde S3 en su primera invocación y lo conserva en una variable global de la instancia. API Gateway es el único punto de entrada público de la versión AWS. En la versión local, el cliente llama a FastAPI; FastAPI publica cada evento de interacción en RabbitMQ y el consumidor lo registra en disco.

**Figura 1 (pendiente): diagrama de arquitectura.** Debe dibujarse en PlantUML o Mermaid a partir de la tabla anterior. Aún no existe render; no se incluye como imagen en este informe.

**Desviación respecto del encargo.** La pauta menciona "endpoints configurados" en SageMaker. El equipo no desplegó un endpoint de inferencia de SageMaker. SageMaker se usó para entrenar; la inferencia corre en Lambda detrás de API Gateway. La justificación está en la sección 4.

**Decisiones de arquitectura (IE8).** Cada decisión tiene una alternativa y una consecuencia que el equipo debe defender en la presentación:

| Decisión | Alternativa descartada | Motivo | Consecuencia |
|---|---|---|---|
| Entrenamiento en SageMaker (job batch) | Entrenar en un equipo local | Plataforma AIaaS exigida por el encargo; el job deja registro de estado y de duración | Costo por job; 215 s facturados en `ml.t3.large` |
| Inferencia en Lambda | Endpoint de SageMaker en tiempo real | Pago por invocación; la inferencia es una multiplicación de matrices y una ordenación | Arranque en frío (778 ms de init); sin endpoint dedicado |
| Artefacto en S3 | Incluir el modelo en el paquete de la Lambda | Desacopla el reentrenamiento del código; el modelo (11,2 MiB) se carga una vez por instancia | Latencia extra en la primera invocación |
| ALS implícito | SVD con ceros en los no observados | Precision@5 de 0,0101 frente a 0,0061 | Nombres heredados `svd` en el job y el archivo |
| API key en cabecera | Autenticación de usuario (OAuth, Cognito) | Simple de verificar con `curl` en un prototipo | No identifica usuarios individuales; sin rotación automática |
| RabbitMQ con `pika` (local) | Kafka | El encargo acepta RabbitMQ o Kafka; el equipo implementó RabbitMQ y `pika` | No hay mensajería en la versión AWS |

## 3. Modelo de IA implementado (IE1, IE2)

**Tipo y framework.** Filtrado colaborativo implícito con factorización de matrices por mínimos cuadrados alternos (ALS, Hu et al., 2008). El entrenamiento corre en SageMaker con la implementación en numpy de `aws/02_entrenar_sagemaker.py`. La evaluación local usa la librería `implicit` (`modelo/ALS_eval.py`) como verificación cruzada. El nombre del job (`ep3-svd-…`) y del archivo (`modelo_svd-….npz`) son nombres heredados: el algoritmo es ALS, no SVD.

**Dataset.** Amazon Reviews 2023, categoría *Industrial_and_Scientific*, versión 5-core (Hou et al., 2024). Tras cargar y filtrar: 412 947 interacciones, 50 985 usuarios y 25 848 productos. La densidad de la matriz usuario-producto es de 0,031 %. El filtro 5-core no eliminó filas, porque el archivo ya cumplía esa condición. Una matriz densa en float64 costaría unos 10,5 GB, por eso el modelo usa matrices dispersas CSR. La licencia del dataset no está declarada en la fuente; el equipo lo usa solo con fines académicos.

El archivo tiene cuatro columnas: `user_id`, `parent_asin` (identificador del producto), `rating` (de 1 a 5) y `timestamp` (en milisegundos desde la época Unix). Las fechas van del 4 de julio de 2001 al 25 de agosto de 2023. El archivo no incluye texto de reseñas ni nombres de producto, porque se usó la versión *rating-only*. La distribución de calificaciones, contada directamente del CSV, es:

| Rating | Interacciones | Proporción |
|---|---|---|
| 1 | 20 970 | 5,1 % |
| 2 | 12 900 | 3,1 % |
| 3 | 23 792 | 5,8 % |
| 4 | 56 718 | 13,7 % |
| 5 | 298 567 | 72,3 % |

El 86,0 % de las interacciones tienen rating 4 o 5, y en la partición de prueba la proporción es la misma: 71 052 positivos de 82 589 interacciones (86,0 %). Por eso el umbral de relevancia (rating ≥ 4) casi no filtra: casi toda interacción observada cuenta como positiva. Esto no cambia la comparación entre modelos, porque todos se evalúan con el mismo criterio, pero sí explica por qué el resultado debe leerse como un ranking relativo y no como una tasa de acierto absoluta. La probabilidad de que un candidato no visto sea positivo es mucho menor (71 052 positivos entre 942 millones de candidatos).

**Proceso de entrenamiento.** El conjunto se divide de forma aleatoria 80/20 con semilla 42: 330 358 interacciones para entrenamiento y 82 589 para prueba. En el entrenamiento, la confianza de cada par observado es el rating. El modelo tiene k = 32 factores latentes y 15 iteraciones de ALS con regularización 0,01.

| Parámetro | Valor |
|---|---|
| Partición | Aleatoria 80/20, semilla 42 (entrenamiento 330 358; prueba 82 589) |
| Factores latentes (k) | 32 |
| Regularización | 0,01 |
| Iteraciones | 15 |
| Confianza | Valor de rating en entrenamiento |
| Candidatos por usuario | Productos no vistos en entrenamiento |
| Relevancia en prueba | Rating ≥ 4 |

**Pipeline de datos y entrenamiento.** El flujo es el mismo en la preparación local y en SageMaker:

1. Carga del CSV (412 947 filas) y verificación de duplicados (0 eliminados).
2. Filtro k-core de 5 por usuario y por producto. El archivo ya era 5-core, así que no quitó filas.
3. Partición aleatoria 80/20 con semilla 42.
4. Construcción de la matriz de interacciones en formato disperso CSR (usuario × producto), con confianza igual al rating.
5. Entrenamiento de ALS con k = 32, regularización 0,01 y 15 iteraciones.
6. Evaluación en prueba: candidatos no vistos, top-5 y relevancia con rating ≥ 4; comparación con popularidad y SVD.
7. Publicación del artefacto `.npz` en S3 y actualización de la variable `MODEL_KEY` de la Lambda.

**Entrenamiento en SageMaker.** Job `ep3-svd-2026-11-24-15-45-45-251` en estado *Completed*, instancia `ml.t3.large`, 215 s facturados, con el hiperparámetro k = 32. El modelo publicado es `s3://ep2-equipo1-128688195152/modelos/modelo_svd-20261124-155354.npz`, con matrices U (usuarios × k) y V (productos × k), identificadores y el historial de productos vistos.

**Interpretabilidad para la decisión (IE2).** La puntuación de un producto para un usuario es el producto punto entre el vector latente del usuario y el del producto (`score = U_u · V_i`). Los productos ya vistos se excluyen antes de ordenar. La API devuelve el `score` junto a cada producto, de modo que el equipo de negocio puede priorizar campañas por puntuación. El score no es una explicación en lenguaje natural: es una medida de afinidad, no una razón de compra. Un producto con score alto es uno cuyo perfil latente se parece al del usuario según las compras y calificaciones del conjunto de entrenamiento.

**3.1 Metodología de evaluación.** El protocolo se aplica igual a todos los modelos comparados (ALS, popularidad y SVD), para que las diferencias se deban al modelo y no a la partición:

| Etapa | Decisión | Detalle verificable |
|---|---|---|
| Datos | Dataset completo, sin muestreo | 412 947 interacciones; 0 duplicados eliminados |
| Partición | Aleatoria 80/20, semilla 42 | Entrenamiento 330 358; prueba 82 589 |
| Usuarios evaluados | Solo quien tiene ≥ 1 positivo en prueba | 36 454 usuarios; 71 052 positivos (rating ≥ 4) |
| Candidatos | Todos los productos no vistos en entrenamiento | 942 019 848 pares evaluados |
| Predicción | Top-5 de los candidatos por puntaje | Precision@5 y Recall@5 (media por usuario) |
| Métricas agregadas | TP, FP, FN, TN sobre todos los pares | Precision, recall, F1, accuracy |
| Control de fuga | Ningún positivo de prueba aparece en entrenamiento | Chequeo = 0 en la salida del script |

Tiempos de cada corrida, leídos de los archivos de resultados: ALS numpy, 39,4 s de entrenamiento y 84,3 s en total; ALS implícito, 2,0 s de entrenamiento y 28,8 s en total; baseline SVD y popularidad, 28,6 s en total. Los scripts son `modelo/metricas_clasificacion.py`, `modelo/ALS_eval.py` y `modelo/baseline_eval.py`; sus salidas están en `modelo/*_resultados.txt`.

**Limitación del protocolo.** Es una partición aleatoria, no temporal. Un usuario puede tener interacciones posteriores en el conjunto de prueba, por lo que la evaluación no simula un despliegue real con datos futuros. Tampoco se hizo validación cruzada ni búsqueda de hiperparámetros: los resultados son de una sola partición y una sola semilla.

**Resultados de clasificación y ranking** (partición de prueba):

| Métrica | ALS (k=32, numpy) | Popularidad | ALS implícito (`implicit`) |
|---|---|---|---|
| Precision@5 | **0,0101** | 0,0046 | 0,0100 |
| Precision (agregada) | **0,0101** | 0,0046 | — |
| Recall (agregado) | **0,0258** | 0,0118 | — |
| Recall@5 (media por usuario) | **0,0269** | 0,0125 | — |
| F1 | **0,0145** | 0,0066 | — |
| Accuracy | 0,9997 | 0,9997 | — |

**Definiciones.** Sea R(u) el conjunto de productos relevantes del usuario u en prueba y P(u) sus cinco primeros recomendados. Precision@5 es la fracción de P(u) que está en R(u), promediada sobre los usuarios. Precision, recall y F1 se calculan sobre la tabla agregada de pares (TP, FP, FN, TN): precisión = TP / (TP + FP); recall = TP / (TP + FN); F1 = 2 · precisión · recall / (precisión + recall); accuracy = (TP + TN) / total.

ALS mejora a popularidad en precision, recall y F1. En Precision@5 la mejora es de unas 2,2 veces. En términos absolutos, la mejora es modesta, consistente con un catálogo de 25 848 productos y una matriz muy dispersa. La versión de `implicit` (0,0100) confirma el resultado de la implementación numpy.

**Por qué la accuracy no sirve como argumento.** El 99,9 % de los pares evaluados son negativos verdaderos. Un modelo que no recomendara nada obtendría una accuracy casi igual (0,9997 frente a 0,9997). El criterio útil es precision, recall y F1, que se concentran en los positivos.

**Baseline SVD.** Una descomposición SVD (scipy, k = 32) sobre la matriz con ceros en los no observados da Precision@5 de 0,0061, por encima de popularidad (0,0046) pero por debajo de ALS. Su RMSE de predicción de rating es 4,56 sin recorte y 3,61 recortado a [1, 5], frente a 1,08 de predecir la media global de entrenamiento (4,45). El modelo se optimiza para ranking de productos observados, no para predecir ratings; por eso el sistema se compara por ranking y no por error de rating.

## 4. Despliegue en AWS y estrategia de consumo (IE1, IE4, IE5)

| Componente | Recurso | Estado verificado |
|---|---|---|
| Entrenamiento | SageMaker, `ml.t3.large` | Job *Completed* en 215 s |
| Artefacto | S3 `modelos/modelo_svd-20261124-155354.npz` | Publicado (11,2 MiB) |
| Cómputo | Lambda `ep3-recomendador`, Python 3.12, 512 MB, timeout 30 s | Activa, con variables `BUCKET`, `MODEL_KEY` y `API_KEY` |
| Entrada | API Gateway HTTP API `ep3-recomendador-api` (`5uli1pw7qf`), `GET /recomendar`, sin authorizer | Responde; HTTPS terminado aquí |
| Registros | CloudWatch `/aws/lambda/ep3-recomendador` | Logs revisados; captura pendiente |

**Flujo de consumo.** (1) El cliente envía `GET /recomendar?usuario=<id>` con la cabecera `X-API-Key` a API Gateway por HTTPS. (2) API Gateway invoca la Lambda sin autorizador propio. (3) La Lambda valida la clave; si falta o es incorrecta responde 401 sin consultar el modelo. (4) Sin el parámetro `usuario` responde 400. (5) Si la clave es válida, la Lambda carga el modelo desde S3 en la primera invocación y lo guarda en una variable global, de modo que las invocaciones siguientes en la misma instancia no lo vuelven a descargar. Calcula el producto U·Vᵀ para el usuario, excluye los productos ya vistos y devuelve los 10 con mayor score. (6) Si el usuario no existe en el modelo, responde 404.

**Respuestas verificadas en el despliegue:**

| Caso | Petición | Respuesta |
|---|---|---|
| Sin clave | `GET /recomendar?usuario=…` sin `X-API-Key` | 401 |
| Clave correcta, usuario existente | usuario `AFNT6ZJCYQN3WDIKUSWHJDXNND2Q` | 200, 10 recomendaciones; la primera es `B07KYVGGTK` con score 0,2074 |
| Clave correcta, usuario inexistente | usuario `999999999` | 404, "usuario sin historial" |
| Clave correcta, sin parámetro | `GET /recomendar` | 400, "falta el parametro usuario" |

**Comprobación con curl en AWS.** Son los comandos del punto de control del `aws/README.md`, con la variable `API_ID` del despliegue y la clave en `API_KEY`:

```bash
URL="https://$API_ID.execute-api.us-east-1.amazonaws.com/recomendar"
curl -s -o /dev/null -w "%{http_code}\n" "$URL?usuario=<ID_EXISTENTE>"                          # 401 sin clave
curl -s -o /dev/null -w "%{http_code}\n" -H "X-API-Key: $API_KEY" "$URL?usuario=<ID_EXISTENTE>" # 200
curl -s -o /dev/null -w "%{http_code}\n" -H "X-API-Key: $API_KEY" "$URL?usuario=999999999"      # 404
```

El caso 400 se obtiene con la clave correcta y sin el parámetro `usuario`.

Ejemplo de respuesta para el usuario `AFNT6ZJCYQN3WDIKUSWHJDXNND2Q` (inicio del JSON; los demás elementos están en la captura pendiente):

```json
{"usuario": "AFNT6ZJCYQN3WDIKUSWHJDXNND2Q", "recomendaciones": [{"parent_asin": "B07KYVGGTK", "score": 0.2074}, "… 9 elementos más …"]}
```

**Figura 6 (pendiente): captura de respuestas 401, 200, 400 y 404** con `curl`, y la respuesta JSON completa.

**Estrategia de despliegue y consumo.** La separación es entrenamiento batch en SageMaker, publicación del artefacto en S3 y servicio ligero en Lambda. La inferencia es una multiplicación de matrices y una ordenación, sin necesidad de GPU ni de un contenedor dedicado. Un endpoint de SageMaker en tiempo real cobra por hora de instancia encendida aunque nadie consulte; la Lambda cobra por invocación y por tiempo de ejecución. Para un prototipo con consultas esporádicas, eso reduce el costo fijo. La alternativa descartada fue un endpoint de SageMaker, por costo y latencia en el laboratorio. El equipo no lo desplegó y no midió su costo.

**Justificación de plataforma AIaaS (IE4, IL3.2).** SageMaker aporta un entorno administrado para entrenar, con instancias y almacenamiento que se pagan solo durante el job. Lambda aporta escalado automático por concurrencia y pago por invocación. El compromiso es la latencia de arranque en frío (sección 8) y la falta de un endpoint dedicado de SageMaker. Esa decisión queda abierta para una versión con tráfico sostenido.

**Escalabilidad y costos (IE4).** La Lambda escala por concurrencia de forma automática, pero no se midió su comportamiento de escalado en AWS: la prueba de carga de la sección 8 se ejecutó contra el servicio local. El costo del Learner Lab del mes, consultado en Cost Explorer el 24-11-2026, es de USD 0,026. Billing muestra SageMaker como servicio principal del mes. El desglose por servicio está en la sección 9.

## 5. Servicio, endpoints y documentación (IE7)

La versión local (`servicio/app.py`, FastAPI) expone los siguientes endpoints. El esquema OpenAPI exportado está en `docs/openapi.json`.

| Método y ruta | Autenticación | Descripción | Respuestas documentadas |
|---|---|---|---|
| `GET /salud` | No | Estado del servicio | 200 |
| `GET /recomendar?usuario=&n=` | `X-API-Key` | Top-n de productos no vistos, con score | 200, 401, 404, 422, 429 |
| `POST /interacciones` | `X-API-Key` | Registra un evento usuario-producto con rating y timestamp | 202, 401, 422, 503 |
| `GET /docs` | No | Swagger UI | 200 |
| `GET /openapi.json` | No | Esquema OpenAPI | 200 |
| `GET /dashboard` | No | Panel HTML con métricas y gráficos | 200 |

En la versión local, `n` va de 1 a 100 y su valor por defecto es 5. La versión desplegada en AWS **no** acepta `n` y devuelve siempre 10 productos. Esa diferencia es intencional para mantener la Lambda simple, pero el contrato no es idéntico y debe declararse ante quien consuma la API.

**Contrato por versión.** El consumidor de la API debe conocer estas diferencias:

| Aspecto | Versión local (FastAPI + Docker) | Versión AWS (Lambda + API Gateway) |
|---|---|---|
| URL base | `http://localhost:8000` (HTTP) | `https://<API_ID>.execute-api.us-east-1.amazonaws.com` (HTTPS) |
| Parámetro `n` | Opcional, 1 a 100, por defecto 5 | No existe; devuelve siempre 10 |
| Usuario sin historial | 404 | 404, con mensaje "usuario sin historial" |
| Usuario vacío | 422 (`test_recomendar_usuario_vacio_422`) | No verificado |
| Sin parámetro `usuario` | No verificado en local | 400, con mensaje "falta el parametro usuario" |
| Límite de tasa | 60 peticiones/min por IP, con 429 | No verificado (pendiente) |
| Respaldo por popularidad | Sí, si el archivo del modelo no existe | No |
| Mensajería | `POST /interacciones` a RabbitMQ | No desplegada |
| Documentación | `/docs` (Swagger) y `/openapi.json` | `docs/openapi.json` exportado; Swagger en AWS no verificado |

**Códigos de respuesta y cuerpos de error.** Los cuerpos de la versión local son los que documenta el README del repositorio; los de AWS son los que devolvió la API desplegada.

| Código | Cuando ocurre | Cuerpo |
|---|---|---|
| 200 | Recomendación calculada | `{usuario, recomendaciones: [{parent_asin, score}], modelo}` (local); `{usuario, recomendaciones}` (AWS) |
| 202 | Evento de interacción publicado | `{estado: "aceptado"}` |
| 400 | Falta `usuario` (solo AWS) | Texto "falta el parametro usuario" |
| 401 | Clave ausente o incorrecta (AWS: también se responde antes de consultar el modelo) | `{"error": "no autorizado"}` en AWS |
| 404 | Usuario sin historial | "usuario sin historial" en AWS; en local, usuario inexistente |
| 422 | `n` fuera de 1 a 100, usuario vacío o evento inválido (solo local) | Error de validación de FastAPI |
| 429 | Más de 60 peticiones por minuto desde una IP (local) | Cabecera `Retry-After` |
| 500 | `API_KEY` no configurada (local) | Mensaje de configuración |
| 503 | RabbitMQ no disponible (local) | Error del publicador |

**Rutas públicas.** `/salud`, `/docs`, `/openapi.json` y `/dashboard` no exigen clave. La prueba `test_dashboard_carga_metricas_y_carga_estaticas` verifica que el dashboard carga las métricas y los archivos estáticos.

**Figura 7 (pendiente): captura del dashboard** con las métricas y **Figura 8 (pendiente): captura de Swagger** (`/docs`).

## 6. Mensajería con RabbitMQ (IE7, IL3.3)

Los eventos de interacción se registran por `POST /interacciones`. El flujo es el siguiente: la API valida el JSON (producto, usuario, rating y timestamp); el publicador (`servicio/mensajeria.py`, con `pika`) envía el mensaje a la cola durable `interacciones`; el consumidor (`servicio/consumidor.py`) lo lee, lo valida y lo agrega a `eventos.jsonl`. Ese archivo alimenta el respaldo por popularidad de la versión local.

Reglas de comportamiento:

- Si la publicación se completa, la API responde 202.
- El publicador reintenta una vez si la conexión se cae.
- Si RabbitMQ no responde, la API responde 503 y el evento no se pierde silenciosamente: el cliente recibe el error y puede reintentar.
- El consumidor rechaza mensajes inválidos sin escribirlos y responde *nack* sin reencolar, para no dejarlos en bucle.

Las pruebas de este flujo están en `tests/test_mensajeria_consumidor.py` (6 casos) y en `tests/test_api.py`, con el publicador simulado. La prueba de integración con RabbitMQ real se describe en la sección 8 con su estado de verificación.

**Alcance en la nube.** RabbitMQ no está desplegado en AWS para la demostración. En `aws/05_rabbitmq_ec2.sh` y `aws/06_probar_rabbitmq.sh` hay scripts para levantar un broker en EC2, pero el flujo de recomendación verificado en la nube no depende de él. No se usa Kafka.

**Flujo de secuencia de eventos (texto).**

1. El cliente envía `POST /interacciones` con `X-API-Key`, usuario, producto, rating y timestamp.
2. La API valida la clave y el cuerpo. Si la clave falta o es incorrecta, responde 401 y no publica nada (prueba `test_interaccion_sin_clave_401_y_no_publica`). Si el cuerpo es inválido, responde 422 (rating fuera de rango, producto numérico o timestamp mal formado).
3. El publicador abre la conexión con RabbitMQ y publica el mensaje JSON en la cola durable `interacciones`. Si la conexión cae, reintenta una vez.
4. Si la publicación se completa, la API responde 202. Si el broker no responde, responde 503.
5. El consumidor lee el mensaje, valida su contenido y lo escribe en `eventos.jsonl`. Si el mensaje es inválido, lo descarta con *nack* y no lo reencola.

**Figura 2 (pendiente): diagrama de secuencia** del flujo anterior en PlantUML o Mermaid. El texto de arriba es la especificación para ese diagrama.

## 7. Seguridad (IE7, IL3.3)

**Autenticación.** En ambas versiones, `/recomendar` e `/interacciones` exigen la cabecera `X-API-Key`. Sin clave, o con clave incorrecta, responden 401. En la versión local, la comparación usa `hmac.compare_digest` para evitar ataques de temporización. Si el servicio arranca sin `API_KEY` configurada, responde 500 en lugar de dejar la ruta abierta: el fallo es cerrado. La clave de la Lambda se guarda como variable de entorno; no hay un gestor de secretos, y eso es una limitación declarada.

**Cifrado en tránsito (TLS).** En AWS, API Gateway termina TLS: el endpoint público es HTTPS. En la versión local con Docker el servicio responde en HTTP plano; esto se declara como limitación y no se considera un despliegue seguro.

**Limitación de tasa (rate limiting).** En la versión local, un limitador en memoria permite 60 peticiones por minuto por IP (`RATE_LIMIT_POR_MINUTO`) y responde 429 con `Retry-After`. Sus límites son conocidos: el contador vive en cada proceso, y detrás de un proxy cuenta la IP del proxy. La prueba automatizada `test_rate_limit_responde_429_con_retry_after` lo verifica.

**En la API desplegada en AWS no se verificó un límite de tasa.** [PENDIENTE: revisar en la consola de API Gateway la configuración de *throttling* del stage por defecto. Si no está configurado, se declara como no activo.]

**Pruebas de interoperabilidad (IE7).** Verifican que los componentes se comunican con el contrato acordado. Son pruebas de la versión que cada fila indica.

| Interacción | Prueba | Resultado |
|---|---|---|
| Cliente → API Gateway → Lambda (clave válida) | `GET /recomendar` con `X-API-Key` correcta | 200 con 10 productos (verificado en AWS) |
| Cliente → API Gateway → Lambda (clave ausente) | `GET /recomendar` sin cabecera | 401 (verificado en AWS) |
| Lambda → S3 (carga del modelo) | Primera invocación tras el despliegue | Respuestas 200 con datos del modelo; init de 778 ms en logs. La lectura de S3 se infiere de ese init y no se midió por separado |
| Cliente → FastAPI → RabbitMQ | `POST /interacciones` con broker disponible | 202 (registro del equipo, Docker local) |
| FastAPI → RabbitMQ caído | `test_post_con_broker_caido_responde_503` | 503 (prueba automatizada) |
| RabbitMQ → consumidor → `eventos.jsonl` | `test_consumidor_registra_evento_en_jsonl` | Registro escrito (prueba automatizada) |
| Cliente → FastAPI → Lambda (mismo contrato) | Mismo usuario en ambas versiones | No comparado en esta redacción: pendiente |

**Riesgos y controles.**

| Riesgo | Control | Estado |
|---|---|---|
| Acceso no autorizado a recomendaciones | `X-API-Key` en la Lambda y en la versión local | Verificado (401 sin clave) |
| Ataque por temporización de la clave | `hmac.compare_digest` | Local |
| Abuso o fuerza bruta de la clave | Rate limit 60/min | Local; AWS pendiente |
| Escucha de tráfico | HTTPS en API Gateway | AWS; local sin TLS |
| Caída del broker | Respuesta 503, reintento en el publicador | Prueba automatizada |
| Fuga de la clave | Clave en variables de entorno, no en el repositorio | Parcial (sin gestor de secretos) |

## 8. Pruebas y calidad (IE10)

**8.1 Pruebas unitarias y de API.** Comando: `.venv\Scripts\python.exe -m pytest tests -q`, desde la carpeta `EP3`, con Python 3.12.10 y el entorno virtual del proyecto (fastapi 0.165.0 ya instalado; no fue necesario reinstalar `servicio\requirements.txt`). Resultado real de la última ejecución:

```
...............................................                          [100%]
47 passed, 1 warning in 3.78s
```

El único aviso es de deprecación de `starlette.testclient` (uso de `httpx`); no afecta el resultado. Las 47 pruebas pasan. Son 41 funciones `def test_`, de las cuales 35 están en `tests/test_api.py` y 6 en `tests/test_mensajeria_consumidor.py`; las funciones parametrizadas suman los 47 casos.

Casos de prueba seleccionados (nombres tomados de `tests/`):

| # | Caso | Qué verifica | Resultado esperado |
|---|---|---|---|
| 1 | `test_salud_responde_ok` | `/salud` responde | 200 |
| 2 | `test_recomendar_sin_clave_401` | Ruta protegida sin clave | 401 |
| 3 | `test_recomendar_clave_incorrecta_401` | Clave errónea | 401 |
| 4 | `test_recomendar_con_clave_correcta_200` | Clave válida | 200 |
| 5 | `test_sin_clave_configurada_responde_500` | Servicio sin `API_KEY` | 500 (fallo cerrado) |
| 6 | `test_rate_limit_responde_429_con_retry_after` | Exceso de peticiones | 429 con `Retry-After` |
| 7 | `test_recomendar_usuario_inexistente_404` | Usuario fuera del modelo | 404 |
| 8 | `test_recomendar_usuario_vacio_422` | Usuario vacío | 422 |
| 9 | `test_recomendar_excluye_productos_vistos` | Ningún producto visto en el top | Verdadero |
| 10 | `test_recomendar_scores_en_orden_descendente` | Orden del ranking | Descendente |
| 11 | `test_post_interaccion_valida_202_y_publica` | Evento válido | 202 y publicado |
| 12 | `test_post_con_broker_caido_responde_503` | RabbitMQ caído | 503 |
| 13 | `test_consumidor_rechaza_mensaje_invalido_sin_escribir` | Mensaje inválido | No se escribe |
| 14 | `test_fallback_sin_modelo_arranca_con_popularidad` | Sin archivo de modelo | Arranca con popularidad |
| 15 | `test_swagger_y_openapi_disponibles` | Documentación | 200 |
| 16 | `test_dashboard_sirve_html` | Dashboard | 200 y HTML |

La lista es una selección de los casos más relevantes; la suite completa está en `tests/test_api.py` y `tests/test_mensajeria_consumidor.py`.

**Inventario de la suite.** Por conteo directo de las funciones `def test_` del directorio `tests/`, hay 41 funciones: 35 en `tests/test_api.py` y 6 en `tests/test_mensajeria_consumidor.py`. Las funciones parametrizadas generan varios casos cada una, y la ejecución de pytest confirma 47 casos aprobados.

| Archivo | Funciones | Qué cubre |
|---|---|---|
| `tests/test_api.py` | 35 | Autenticación (401, 500 sin clave configurada), límite de tasa (429), recomendación (orden, n, exclusión de vistos, 404, 422), eventos (202, 422, 503), documentación y dashboard, respaldo por popularidad y ruta del modelo |
| `tests/test_mensajeria_consumidor.py` | 6 | Publicador (cola durable, reintento), consumidor (registro en JSONL, mensaje inválido, ack y nack sin reencolar) |

**8.2 Pruebas de despliegue en AWS.** Las cuatro respuestas de la sección 4 (401, 200, 404 y 400) son casos reales contra la API de API Gateway, no contra un simulador. Cubren autenticación, ruta válida, usuario inexistente y validación de parámetros.

**8.3 Pruebas de integración con Docker.** `docker compose up -d --build` levanta RabbitMQ, la API y el consumidor. El registro del equipo indica: `/recomendar` sin clave → 401, con clave → 200; `/salud` → 200; `/dashboard` → 200; `/interacciones` sin clave → 401, con clave → 202. Esta comprobación no quedó con captura ni log en el repositorio y no se volvió a ejecutar para este informe. [PENDIENTE: ejecutar de nuevo y guardar la salida.]

**8.4 Pruebas de carga local (Locust).** Corrida de 20 usuarios concurrentes durante 30 s, con clave, sobre la API local (`http://localhost:8000`). Los datos provienen de `tests/resultados_locust_stats.csv`. La corrida usó `RATE_LIMIT_POR_MINUTO=100000`, porque 20 usuarios desde una misma IP superan el límite por defecto (60/min). Con el límite por defecto, una corrida de prueba devolvió 429 en el 94 % de las peticiones; esa corrida no quedó guardada en el repositorio.

| Endpoint | Peticiones | Fallos | p50 (mediana) | p95 | p99 | Máximo |
|---|---|---|---|---|---|---|
| `GET /recomendar` | 787 | 0 | 30 ms | 160 ms | 210 ms | 330 ms |
| `POST /interacciones` | 169 | 0 | 63 ms | 220 ms | 340 ms | 346 ms |
| **Agregado** | **956** | **0** | **36 ms** | **170 ms** | **220 ms** | **346 ms** |

Throughput agregado: 32,5 peticiones/s (26,8 en `/recomendar` y 5,7 en `/interacciones`). Latencia media agregada: 52,5 ms. Tasa de errores: 0 %. Las cifras provienen de `tests/resultados_locust_stats.csv`; los percentiles son los de las columnas 50 %, 95 % y 99 % de Locust. Estas cifras son de la máquina de desarrollo sobre Docker en Windows. **No son latencias de AWS.**

**Metodología de la carga (de `tests/locustfile.py`).** Cada usuario virtual (`UsuarioTienda`) espera entre 0,1 y 1,0 s entre tareas. La tarea `recomendar` tiene peso 4 y consulta `/recomendar` con un usuario elegido al azar de `tests/usuarios_muestra.txt` y `n = 5`. La tarea `registrar_interaccion` tiene peso 1 y envía un `POST /interacciones` con usuario, producto (de `productos_muestra.txt`), rating aleatorio de 1 a 5 y la hora actual en UTC. Una respuesta cuenta como fallo si el código no es 200 (recomendar) o 202 (interacción). La proporción de peticiones (787 de recomendación y 169 de interacción) es coherente con el peso 4 frente a 1. La prueba con el parámetro `n = 5` no aplica a la versión AWS, que devuelve siempre 10 productos.

**Resultados presentados en el dashboard.** El dashboard del servicio local lee dos archivos estáticos: `servicio/static/metricas.json` (fuente: `modelo/metricas_clasificacion_resultados.txt`) y `servicio/static/carga.json` (fuente: `tests/resultados_locust_stats.csv`). Ambos archivos contienen las mismas cifras de esta sección; si cambia la corrida de Locust, hay que regenerar `carga.json`.

**8.5 Pruebas de carga pendientes.** Las siguientes mediciones no se ejecutaron y se declaran como PENDIENTE:

- **PENDIENTE — Locust contra API Gateway:** p50, p95, p99, throughput y tasa de errores sobre `https://5uli1pw7qf.execute-api…/recomendar`. Es la única medición que refleja la latencia real de la versión desplegada.
- **PENDIENTE — JMeter:** no se ejecutó. El encargo acepta JMeter o Locust; el equipo usó Locust.
- **PENDIENTE — Latencia de arranque en frío:** medir la primera invocación tras un cambio de configuración de la Lambda, separando la carga desde S3.

**Lectura de los percentiles.** El p50 describe la experiencia típica y el p95 y p99 describen la cola: cuántas peticiones tardan más de lo esperado. En la corrida local, `/recomendar` tuvo 787 muestras, así que su p99 depende de unas 8 peticiones lentas. `/interacciones` tuvo 169 muestras: su p99 (340 ms) depende de unas 2 peticiones, y no es estable. Por eso el informe reporta el percentil junto con el número de peticiones y no lo presenta como una garantía de servicio. Una cifra confiable de p99 necesita una corrida más larga y con más peticiones.

**8.6 Métricas del modelo.** Véase la sección 3: accuracy (con la advertencia ya indicada), precision, recall y F1, frente a popularidad y SVD.

**8.7 Oportunidades de optimización (IL3.4).**

1. Medir el arranque en frío (descarga del `.npz` desde S3 y construcción del diccionario de usuarios). La Lambda registra una fase de inicialización de 778 ms en los logs; si el arranque en frío domina la latencia, conviene ajustar la memoria o usar concurrencia aprovisionada. El modelo ya se cachea entre invocaciones de la misma instancia.
2. Ajustar k y la regularización con validación cruzada: el modelo se entrenó con k = 32 y reg = 0,01 sin búsqueda de hiperparámetros.
3. Reducir la brecha de cobertura: el 99,9 % de los pares son negativos y el modelo recomienda sobre un catálogo grande. Un re-ranking por categoría o por popularidad reciente podría mejorar el recall.
4. Medir costos y latencia en AWS con carga real antes de decidir el tamaño de la Lambda (512 MB).
5. Automatizar el reentrenamiento a partir de `eventos.jsonl`, que hoy se registra pero no se usa para reentrenar.

**8.8 Plan de mejora continua (IL3.4).** Cada hallazgo de la medición tiene una acción y un criterio de cierre:

| Hallazgo | Evidencia | Acción | Criterio de cierre |
|---|---|---|---|
| Latencia de AWS desconocida | Solo hay medición local | Locust contra API Gateway con la misma corrida de 20 usuarios y 30 s | p50, p95 y p99 publicados en la tabla de la sección 8.4 |
| Límite de tasa sin verificar en AWS | Solo local (429 probado) | Revisar el *throttling* del stage y probar con exceso de peticiones | Respuesta 429 observada desde la URL pública |
| Arranque en frío | Init de 778 ms | Medir la primera invocación tras una actualización de la Lambda | Duración de la primera invocación separada del resto |
| Métricas del modelo bajas | Precision@5 de 0,0101 | Ajustar k y regularización con validación cruzada | Mejora de Precision@5 frente a 0,0101 en la misma partición |
| Eventos sin uso en el modelo | `eventos.jsonl` se escribe, no se reentrena | Definir un job de reentrenamiento periódico | Un nuevo artefacto en S3 generado desde los eventos |

## 9. Evidencias, CloudWatch y costos (IE4, IE5)

**Logs de CloudWatch de la Lambda.** Los registros `REPORT` de `/aws/lambda/ep3-recomendador` muestran:

| Métrica | Valor observado |
|---|---|
| Duración de invocación | 1,9 ms y 1 114 ms |
| Fase de inicialización (*Init Duration*) | 778 ms |
| Memoria máxima usada | 111 MB a 145 MB, de 512 MB configurados |

Cada línea `REPORT` de CloudWatch tiene los campos *Duration* (tiempo de ejecución del handler), *Billed Duration* (tiempo que se factura), *Memory Size* (configurado), *Max Memory Used* (usado) e *Init Duration* (solo en arranque en frío, es decir, cuando la instancia se crea). Con esa definición, la invocación de 1,9 ms corresponde a una instancia ya caliente, y la de 1 114 ms es la más larga. Su relación con la carga inicial del modelo desde S3 es una interpretación: confirmarla con el registro completo de esa invocación. La memoria usada equivale a entre el 22 % y el 28 % de la configurada, lo que sugiere que 512 MB tiene margen.

**Métricas de API Gateway.** La métrica de conteo de peticiones de API Gateway (`Count`) y los errores 4xx se consultan en la consola; quedan en la Figura 9 (pendiente).

**Costos.** El costo del Learner Lab del mes, consultado en Cost Explorer el 24-11-2026, es de **USD 0,026**. Billing muestra SageMaker como servicio principal, lo que es coherente con el job de entrenamiento de 215 s en `ml.t3.large`. El desglose por servicio (SageMaker, Lambda, API Gateway, S3 y CloudWatch) no se extrajo en esta etapa. [PENDIENTE: captura de Cost Explorer con desglose por servicio.] No se estima el costo futuro sin una tarifa verificada en la consola.

**Análisis de costos y decisión de plataforma (IE4, IL3.2).** La tabla compara los factores de costo de las dos alternativas de inferencia. No incluye precios: el equipo no verificó tarifas de AWS y no las estima.

| Factor | Lambda + API Gateway (elegida) | Endpoint de SageMaker en tiempo real |
|---|---|---|
| Cobro | Por invocación y tiempo de ejecución | Por hora de instancia encendida |
| Uso esporádico | Costo casi nulo cuando no hay consultas | El endpoint cobra igual sin consultas |
| Memoria necesaria | 111 a 145 MB de los 512 MB configurados | Requiere instancia dimensionada para el modelo |
| Latencia de arranque | Init de 778 ms en frío | Sin arranque en frío, pero siempre encendido |
| Escalado | Automático por concurrencia | Configurable con *auto-scaling* de la instancia |
| Estado observado | Desplegado y probado | No desplegado |

**Evidencias exigidas y estado.**

| Evidencia | Estado |
|---|---|
| Job de SageMaker *Completed* (log y estado) | Figura 3 (pendiente): captura |
| Lambda: runtime, memoria y variables | Figura 4 (pendiente): captura |
| API Gateway: ruta `GET /recomendar`, sin authorizer | Figura 5 (pendiente): captura |
| Respuestas 401, 200, 400 y 404 con `curl` | Figura 6 (pendiente): captura |
| Dashboard con resultados | Figura 7 (pendiente): captura |
| Swagger (`/docs`) | Figura 8 (pendiente): captura |
| Logs de CloudWatch de la Lambda | Figura 9 (pendiente): captura; datos ya medidos arriba |
| Costos (Cost Explorer) | Figura 10 (pendiente): captura; total ya medido arriba |

Las capturas se generan con `aws/09_evidencia.sh` desde CloudShell, con la clave exportada como `API_KEY`.

## 10. Limitaciones

- **Dispersión y catálogo grande.** Densidad de 0,031 %. Las métricas absolutas son bajas (Precision@5 de 0,0101). La mejora frente a popularidad es real pero pequeña.
- **Sin endpoint de SageMaker.** La inferencia corre en Lambda. Es una desviación explícita respecto de la pauta, justificada por costo y latencia en el laboratorio.
- **Versión desplegada.** La Lambda devuelve siempre 10 productos y no acepta el parámetro `n`. No tiene el respaldo por popularidad de la versión local.
- **Nombres de producto.** La API devuelve `parent_asin`. Los nombres requieren el archivo de metadatos del dataset, que no se descargó.
- **Exclusión de vistos.** El código de la Lambda y del servicio local excluye los productos vistos antes de ordenar, y la prueba `test_recomendar_excluye_productos_vistos` lo cubre. Esa prueba es parte de la suite que no se volvió a ejecutar en esta redacción (sección 8.1).
- **Mensajería en la nube.** RabbitMQ no está desplegado en AWS. El flujo de eventos se verificó en Docker local según el registro del equipo, sin captura ni re-ejecución.
- **TLS y límite de tasa.** TLS termina en API Gateway. El límite de tasa se verificó solo en el servicio local; en AWS está pendiente.
- **Carga en AWS.** Las pruebas de carga se hicieron en local. No hay medición de escalado ni de latencia en AWS, y JMeter no se ejecutó.
- **Clave de API.** Se guarda en variables de entorno de la Lambda, sin rotación automática ni gestor de secretos.
- **Reentrenamiento.** Los eventos de interacción se registran, pero el modelo no se reentrena automáticamente.
- **Licencia del dataset.** No declarada en la fuente; uso académico.

## 11. Preguntas previstas para la defensa (IE13)

Respuestas preparadas por el equipo, con las cifras de este informe:

1. **¿Por qué Lambda y no un endpoint de SageMaker?** SageMaker entrena el modelo; la inferencia es ligera y se paga por invocación. La alternativa descartada es un endpoint en tiempo real, que cobra por hora aunque no haya consultas. Véase la sección 9.
2. **¿Cuál es el p95 de la API?** En local, 170 ms agregado (160 ms en `/recomendar`). En AWS está pendiente de medición.
3. **¿Por qué Precision@5 es bajo?** Por la densidad de 0,031 % y el tamaño del catálogo. El modelo duplica a popularidad (0,0101 frente a 0,0046; unas 2,2 veces).
4. **¿El modelo excluye productos ya calificados?** Sí. Los productos vistos en entrenamiento se excluyen antes de ordenar, en la Lambda y en el servicio local.
5. **¿Cómo se protege la API?** Con `X-API-Key`, límite de 60 peticiones por minuto en la versión local y HTTPS en API Gateway. El límite en AWS está pendiente.
6. **¿Qué pasa si RabbitMQ cae?** `POST /interacciones` responde 503 (prueba automatizada).
7. **¿Cuál es la licencia del dataset?** No está declarada en la fuente. Se cita a los autores (Hou et al., 2024) y se usa con fines académicos.
8. **¿Cuál es el costo?** USD 0,026 en el Learner Lab hasta el 24-11-2026. El desglose por servicio está pendiente.
9. **¿Por qué ALS y no deep learning?** Con 412 947 interacciones y una densidad de 0,031 %, la factorización basta y sus resultados son verificables.
10. **¿Cómo se reentrena?** Con un nuevo job de SageMaker y la publicación del artefacto con `aws/03_publicar_modelo.sh`. Hoy es manual.
11. **¿Qué mide CloudWatch?** El conteo y los errores 4xx de API Gateway, y los logs y la duración de la Lambda.
12. **¿Qué no está verificado?** La ejecución de Docker y RabbitMQ en esta redacción, y Locust contra AWS. Ambos están declarados como pendientes.

## 12. Conclusiones

El sistema queda desplegado en AWS con un modelo entrenado en SageMaker, publicado en S3 y servido por una API REST con autenticación por clave. El modelo supera a un baseline de popularidad en precision, recall y F1, y la API responde los casos de prueba reales (401, 200, 400 y 404). La versión local agrega RabbitMQ, dashboard, documentación OpenAPI y rate limiting.

**Lecciones del despliegue.** Cuatro hechos del trabajo fueron decisivos y quedan registrados aquí para la próxima iteración. Primero, el nombre del algoritmo debe coincidir con el del archivo: el job y el artefacto siguen llamándose `svd`, aunque el modelo es ALS, y eso confunde a quien revisa el repositorio. Segundo, el límite de tasa por defecto (60/min por IP) hace fallar cualquier prueba de carga desde una sola máquina; la corrida válida requirió subir ese límite, y eso debe documentarse junto con la prueba. Tercero, la exclusión de productos vistos se corrigió en la Lambda antes de la entrega y ahora tiene una prueba automatizada. Cuarto, el identificador de la API (`5uli1pw7qf`) debe figurar en la documentación y en los comandos de prueba; si cambia, hay que actualizarlos todos.

Para la decisión empresarial, el aporte es un orden de productos por afinidad estimada, con un score que puede usarse para priorizar. La mejora frente a popularidad es modesta, así que el valor real depende de validar el modelo con datos de negocio. Los puntos débiles son la magnitud de la mejora, la falta de medición de carga en AWS, la ausencia de límite de tasa verificado en la nube y la falta de endpoint dedicado en SageMaker. Esas son las prioridades del siguiente ciclo.

## 13. Referencias

Hou, Y., Li, J., He, Z., Yan, A., Chen, X., & McAuley, J. (2024). *Bridging language and items for retrieval and recommendation* (arXiv:2403.03952). arXiv. https://doi.org/10.48550/arXiv.2403.03952

Hu, Y., Koren, Y., & Volinsky, C. (2008). Collaborative filtering for implicit feedback datasets. En *Proceedings of the 8th IEEE International Conference on Data Mining (ICDM)* (pp. 263–272). IEEE. https://doi.org/10.1109/ICDM.2008.22

Koren, Y., Bell, R., & Volinsky, C. (2009). Matrix factorization techniques for recommender systems. *Computer, 42*(8), 30–37. https://doi.org/10.1109/MC.2009.263

## 14. Declaración de uso de IA generativa

El equipo usó un asistente de IA (modelo de lenguaje) para redactar borradores de este informe y de la presentación, y para generar parte del código de las herramientas de generación de PDF y del servicio. La versión extendida de este informe también se redactó con asistencia de IA a partir de los archivos del repositorio. Las cifras se tomaron de los archivos del repositorio (`modelo/`, `tests/`, `aws/`, `servicio/`) y de la ejecución en AWS (SageMaker, Lambda, API Gateway, CloudWatch y Cost Explorer), y fueron verificadas por el equipo contra esos archivos. Las decisiones de diseño, las conclusiones y las pruebas pendientes son responsabilidad del equipo.

## Anexo A. Scripts del repositorio y reproducción

El repositorio `https://github.com/snozzono/ep3-recomendador` contiene los siguientes scripts de despliegue, todos ejecutados desde AWS CloudShell (región us-east-1):

| Script | Función |
|---|---|
| `aws/00_preparar.sh` | Clona el repositorio y crea el entorno virtual de SageMaker |
| `aws/00_verificar.sh` | Muestra qué recursos faltan (dataset, job, modelos, Lambda, API) |
| `aws/01_datos.sh` | Sube el dataset a S3 (solo si el bucket está vacío) |
| `aws/02_run.py` y `aws/02_entrenar_sagemaker.py` | Lanza el job de entrenamiento en SageMaker |
| `aws/03_publicar_modelo.sh` | Copia el artefacto a `modelos/` en S3 e imprime `MODEL_KEY` |
| `aws/04_lambda_api.sh` | Crea o actualiza la Lambda `ep3-recomendador` y la API `ep3-recomendador-api` |
| `aws/05_rabbitmq_ec2.sh` y `aws/06_probar_rabbitmq.sh` | Levantan y prueban un broker RabbitMQ en EC2 (opcional) |
| `aws/07_limpieza.sh` | Borra Lambda, API, EC2 y sus grupos de seguridad; no borra datos ni modelos en S3 |
| `aws/09_evidencia.sh` | Imprime las respuestas 200, 401 y 404 para las capturas |

**Matriz de cumplimiento de la pauta.**

| Indicador | Dónde se responde | Estado |
|---|---|---|
| IE1 Modelo funcional en cloud con endpoints | Secciones 3, 4 | Modelo y API en AWS; endpoint de inferencia en API Gateway (no SageMaker) |
| IE2 Consumo en aplicación con interpretabilidad | Secciones 1, 3, 5 | Score por producto; uso previsto, sin prueba con usuarios reales |
| IE4 Plataforma AIaaS con escalabilidad y costos | Secciones 4, 9 | Escalado no medido en AWS; costo total USD 0,026 |
| IE5 Infraestructura mínima | Secciones 2, 4 | Desplegada; capturas pendientes |
| IE7 APIs REST, interoperabilidad y seguridad | Secciones 5, 6, 7 | API y OpenAPI; rate limit en AWS pendiente |
| IE10 Testeo funcional y de rendimiento | Sección 8 | Suite de 41 funciones; carga local; carga AWS pendiente |
| IE3, IE9, IE6, IE8, IE11, IE12, IE13 | Presentación, secciones 1, 2, 11 | Defensa en vivo fuera de este documento |

Las dependencias del servicio están en `servicio/requirements.txt`: FastAPI, Uvicorn, pika, numpy, pydantic, pytest, httpx y Locust. Las pruebas se ejecutan con `python -m pytest tests -q` y la carga con Locust sobre `tests/locustfile.py`.

**Advertencia del repositorio.** La nota del README principal indica que el paso 2 podía quedar en estado *FAULTY*. Este informe usa el estado *Completed* del job `ep3-svd-2026-11-24-15-45-45-251`, verificado en SageMaker. La nota debe actualizarse en el repositorio.

## Anexo B. Procedimiento de reproducción local

Los comandos son los del README del repositorio, ejecutados en PowerShell desde la carpeta `EP3`. Requieren Python 3.12.

**1. Entorno y dependencias.**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r servicio\requirements.txt
```

**2. Pruebas.** `python -m pytest tests -q` (no requiere RabbitMQ: el publicador se simula). Resultado esperado: `47 passed`.

**3. Métricas del modelo.** `python modelo\metricas_clasificacion.py` escribe `modelo\metricas_clasificacion_resultados.txt`, con las cifras de la sección 3.

**4. API local.** Desde `servicio\`, con la clave definida en el entorno:

```powershell
$env:API_KEY = "<clave>"
$env:MODEL_PATH = "..\modelo\modelo.npz"
$env:RABBITMQ_URL = "amqp://guest:guest@localhost:5672/"
uvicorn app:app --reload --port 8000
```

Si `MODEL_PATH` no existe, la API arranca con el respaldo por popularidad y lo registra en el log.

**5. Consumidor** (con RabbitMQ en marcha): `python consumidor.py`, desde `servicio\`.

**6. Docker.** Con un archivo `.env` junto a `docker-compose.yml` que contenga `API_KEY=<clave>`, ejecutar `docker compose up -d --build`. Quedan disponibles la API en `http://localhost:8000`, el dashboard en `/dashboard`, Swagger en `/docs` y el panel de RabbitMQ en `http://localhost:15672`.

**7. Comprobaciones.** Con `curl.exe` (no `curl` de PowerShell):

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" "http://localhost:8000/recomendar?usuario=<ID>"                      # 401 sin clave
curl.exe -s -o NUL -w "%{http_code}\n" -H "X-API-Key: <clave>" "http://localhost:8000/recomendar?usuario=<ID>"  # 200
curl.exe -s -o NUL -w "%{http_code}\n" -H "X-API-Key: <clave>" "http://localhost:8000/salud"                  # 200
```

**8. Carga (Locust).** Con la API en marcha y la misma clave:

```powershell
$env:API_KEY = "<clave>"
$env:RATE_LIMIT_POR_MINUTO = "100000"
python -m locust -f tests\locustfile.py --host http://localhost:8000 --headless -u 20 -r 20 -t 30s --csv tests\resultados_locust --only-summary
```

El límite se sube solo para la carga: con 60 peticiones por minuto desde una IP, casi todas responden 429. Se usa `python -m locust` porque `locust.exe` puede estar bloqueado por políticas de Windows.

**9. Esquema OpenAPI.** Con la API levantada: `curl.exe -H "X-API-Key: <clave>" http://localhost:8000/openapi.json -o docs\openapi.json`. Debe repetirse si cambia un endpoint; `curl.exe` evita que PowerShell escriba UTF-16.

**Nota de consistencia.** El README del repositorio indica "43 pasan" en la sección de pruebas. La ejecución verificada en este informe da 47 casos aprobados; el README debe actualizarse.

## Anexo C. Estructura del repositorio y variables de entorno

**Estructura** (según el README del repositorio):

```
EP3/
├── docker-compose.yml        # rabbitmq + api + consumidor
├── datos/                    # dataset (no versionado)
├── docs/openapi.json         # esquema OpenAPI exportado
├── modelo/                   # ALS_eval.py, baseline_eval.py, metricas_clasificacion.py, modelo.npz
├── servicio/                 # app.py, modelo.py, mensajeria.py, consumidor.py, schemas.py, Dockerfile
│   └── static/               # dashboard.html, metricas.json, carga.json
├── aws/                      # scripts de despliegue (00 a 09) y README de AWS
├── tests/                    # test_api.py, test_mensajeria_consumidor.py, locustfile.py, resultados de Locust
├── presentacion/             # guion y reparto del video
└── informe/                  # EP3_Informe.md (fuente de este PDF)
```

**Variables de entorno de la API y el consumidor:**

| Variable | Valor por defecto | Uso |
|---|---|---|
| `API_KEY` | Sin valor (las rutas protegidas responden 500). En compose: `cambiar-esta-clave` | Clave para la cabecera `X-API-Key`. Debe cambiarse antes de desplegar |
| `RATE_LIMIT_POR_MINUTO` | 60 | Peticiones máximas por minuto y por IP |
| `MODEL_PATH` | `../modelo/modelo.npz` | Archivo `.npz` con `U`, `V`, `user_ids`, `item_ids`, `vistos_ptr` y `vistos` |
| `EVENTOS_PATH` | `servicio/eventos.jsonl` | Eventos del consumidor; alimenta el respaldo por popularidad |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | Conexión a RabbitMQ para la API y el consumidor |

La clave del compose se lee de un archivo `.env` que no se versiona. El `.gitignore` del repositorio lo excluye.

## Anexo D. Trazabilidad de las cifras

Cada cifra del informe tiene una fuente o una comprobación. La columna "Cómo reproducirla" indica el paso del anexo B o la evidencia pendiente.

| Cifra o afirmación | Valor | Fuente | Cómo reproducirla |
|---|---|---|---|
| Interacciones, usuarios, productos | 412 947; 50 985; 25 848 | `modelo/metricas_clasificacion_resultados.txt` | Paso 3 del anexo B |
| Precision@5 ALS y popularidad | 0,0101 y 0,0046 | `modelo/metricas_clasificacion_resultados.txt` | Paso 3 del anexo B |
| Precision@5 ALS implícito | 0,0100 | `modelo/als_resultados.txt` | `modelo/ALS_eval.py` |
| Precision@5 SVD con ceros | 0,0061 | `modelo/baseline_resultados.txt` | `modelo/baseline_eval.py` |
| RMSE de media, SVD y SVD recortado | 1,0815; 4,5579; 3,6118 | `modelo/baseline_resultados.txt` | `modelo/baseline_eval.py` |
| Chequeo de fuga de positivos | 0 | `modelo/metricas_clasificacion_resultados.txt` | Paso 3 del anexo B |
| Pruebas aprobadas | 47 | Salida de pytest (sección 8.1) | Paso 2 del anexo B |
| Latencias p50, p95, p99 locales | 36, 170, 220 ms (agregado) | `tests/resultados_locust_stats.csv` | Paso 8 del anexo B |
| Throughput local | 32,5 peticiones/s | `tests/resultados_locust_stats.csv` | Paso 8 del anexo B |
| Distribución de ratings | 86,0 % con rating ≥ 4 | `datos/Industrial_and_Scientific.csv` | Recuento directo de la columna `rating` |
| Job de entrenamiento | Completed, 215 s, `ml.t3.large` | Consola de SageMaker | Figura 3 (pendiente) |
| Duración y memoria de Lambda | 1,9 ms y 1 114 ms; init 778 ms; 111 a 145 MB | Logs de CloudWatch | Figura 9 (pendiente) |
| Respuestas de la API en AWS | 401, 200, 404 y 400 | Consulta a API Gateway | Comandos de la sección 4; Figura 6 (pendiente) |
| Costo del mes | USD 0,026 | Cost Explorer, 24-11-2026 | Figura 10 (pendiente) |
| Repositorio | `snozzono/ep3-recomendador` | GitHub | URL de la portada |

## Anexo E. Glosario

- **ALS (Alternating Least Squares):** factorización de la matriz de interacciones en factores latentes de usuarios y productos, resolviendo alternadamente cada conjunto con los demás fijos.
- **Filtrado colaborativo implícito:** modelo que aprende de interacciones observadas (compras, calificaciones) sin ratings negativos explícitos.
- **5-core:** filtro que conserva solo usuarios y productos con al menos 5 interacciones.
- **CSR (Compressed Sparse Row):** formato de matriz dispersa que guarda solo los valores no nulos por fila.
- **Precision@5 y Recall@5:** fracción de los cinco primeros recomendados que son relevantes, y fracción de los relevantes que aparecen en los cinco primeros, promediadas por usuario.
- **Baseline de popularidad:** recomendar a todos los usuarios los productos con más interacciones en entrenamiento, sin personalización.
- **Arranque en frío (cold start):** primera invocación de una instancia de Lambda, que incluye la inicialización del código y la carga del modelo.
- **p50, p95, p99:** percentiles de latencia; el valor bajo el cual cae el 50, 95 y 99 % de las peticiones.
- **Rate limiting:** límite de peticiones por unidad de tiempo y por cliente; las peticiones que lo exceden reciben 429.
- **Fallo cerrado (fail closed):** si falta la configuración de seguridad, la ruta protegida rechaza la petición en lugar de permitirla.
