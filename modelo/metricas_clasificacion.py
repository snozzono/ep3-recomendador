import importlib.util
import os
import time

import numpy as np
import pandas as pd
import scipy.sparse as sp

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "..", "datos", "Industrial_and_Scientific.csv")
ENTRENAMIENTO = os.path.join(BASE, "..", "aws", "02_entrenar_sagemaker.py")
OUT = os.path.join(BASE, "metricas_clasificacion_resultados.txt")

FACTORS = 32
SEED = 42
TEST_SIZE = 0.2
TOP_N = 5
RELEVANTE_MIN = 4.0
BATCH = 1000

spec = importlib.util.spec_from_file_location("entrenar_sagemaker", ENTRENAMIENTO)
entrenar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entrenar)

lines = []


def log(texto=""):
    print(texto)
    lines.append(str(texto))


t0 = time.time()
df = pd.read_csv(DATA, dtype={"user_id": str, "parent_asin": str})
log(f"Archivo: {os.path.normpath(DATA)}")
log(f"Filas cargadas: {len(df)}")
df = df.drop_duplicates(["user_id", "parent_asin"]).reset_index(drop=True)

u_codes, u_uniques = pd.factorize(df["user_id"])
i_codes, i_uniques = pd.factorize(df["parent_asin"])
df["u"] = u_codes
df["i"] = i_codes
n_users = len(u_uniques)
n_items = len(i_uniques)
n_inter = len(df)
log(f"Tras filtro: usuarios={n_users}, items={n_items}, interacciones={n_inter}")

rng = np.random.RandomState(SEED)
perm = rng.permutation(n_inter)
n_test = int(round(TEST_SIZE * n_inter))
test = df.iloc[perm[:n_test]]
train = df.iloc[perm[n_test:]]
log(f"Split aleatorio 80/20 (semilla {SEED}): train={len(train)}, test={len(test)}")

R_train = sp.csr_matrix(
    (train["rating"].values.astype(np.float64), (train["u"].values, train["i"].values)),
    shape=(n_users, n_items),
).tocsr()
Rel_test = sp.csr_matrix(
    ((test["rating"].values >= RELEVANTE_MIN).astype(np.float64),
     (test["u"].values, test["i"].values)),
    shape=(n_users, n_items),
)
Rel_test.eliminate_zeros()
Rel_test = Rel_test.tocsr()

pop = np.asarray(R_train.getnnz(axis=0)).ravel().astype(np.float64)
rel_por_usuario = np.asarray(Rel_test.getnnz(axis=1)).ravel()
usuarios_eval = np.unique(Rel_test.nonzero()[0])
log(f"Usuarios evaluados (>=1 item relevante en test, rating>={RELEVANTE_MIN}): {len(usuarios_eval)}")
log(f"Positivos reales en test (rating>={RELEVANTE_MIN}): {Rel_test.nnz}")

log(f"ALS numpy (aws/02_entrenar_sagemaker.py): k={FACTORS}, reg={entrenar.REGULARIZACION}, "
    f"iteraciones={entrenar.ITERACIONES}, semilla={entrenar.SEMILLA}, confianza = rating de train")
t1 = time.time()
U, V = entrenar.entrenar_als(R_train, FACTORS)
log(f"Entrenamiento ALS: {time.time() - t1:.1f} s")

conteo = {
    "ALS": np.zeros(4, dtype=np.int64),
    "Popularidad": np.zeros(4, dtype=np.int64),
}
tp_u_als = 0.0
tp_u_pop = 0.0
recall_u_als = 0.0
recall_u_pop = 0.0
candidatos_total = 0
rel_vistos_train = 0

for start in range(0, len(usuarios_eval), BATCH):
    bu = usuarios_eval[start:start + BATCH]
    b = len(bu)

    seen = np.zeros((b, n_items), dtype=bool)
    tr = R_train[bu].tocoo()
    seen[tr.row, tr.col] = True
    cand = ~seen
    rel = Rel_test[bu].astype(bool).toarray()
    rel_vistos_train += int(np.count_nonzero(rel & seen))
    candidatos_total += int(cand.sum())

    filas = np.arange(b)[:, None]
    for nombre, puntajes in (
        ("ALS", U[bu] @ V.T),
        ("Popularidad", np.broadcast_to(pop, (b, n_items)).copy()),
    ):
        puntajes[seen] = -np.inf
        top = np.argpartition(-puntajes, TOP_N - 1, axis=1)[:, :TOP_N]
        pred = np.zeros((b, n_items), dtype=bool)
        pred[filas, top] = True

        tp = np.count_nonzero(pred & rel)
        fp = np.count_nonzero(pred & ~rel & cand)
        fn = np.count_nonzero(~pred & rel & cand)
        tn = np.count_nonzero(~pred & ~rel & cand)
        conteo[nombre] += np.array([tp, fp, fn, tn], dtype=np.int64)

        tp_u = (pred & rel).sum(axis=1)
        if nombre == "ALS":
            tp_u_als += tp_u.sum()
            recall_u_als += (tp_u / rel_por_usuario[bu]).sum()
        else:
            tp_u_pop += tp_u.sum()
            recall_u_pop += (tp_u / rel_por_usuario[bu]).sum()

n_eval = len(usuarios_eval)
log("")
log("== Definición ==")
log("Candidatos por usuario: items no vistos en train (todos los ítems del catálogo menos los de train).")
log(f"Predicción positiva: ítem en el top-{TOP_N} de candidatos. Positivo real: ítem en test con rating>={RELEVANTE_MIN}.")
log(f"Candidatos evaluados (suma sobre usuarios): {candidatos_total}")
log(f"Chequeo: positivos de test que ya estaban en train: {rel_vistos_train} (debe ser 0)")

for nombre in ("ALS", "Popularidad"):
    tp, fp, fn, tn = (int(x) for x in conteo[nombre])
    total = tp + fp + fn + tn
    accuracy = (tp + tn) / total
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    log("")
    log(f"== Clasificación agregada: {nombre} ==")
    log(f"TP={tp}  FP={fp}  FN={fn}  TN={tn}  total={total}")
    log(f"Accuracy={accuracy:.6f}")
    log(f"Precision={precision:.6f}")
    log(f"Recall={recall:.6f}")
    log(f"F1={f1:.6f}")
    if nombre == "ALS":
        p5 = tp_u_als / (n_eval * TOP_N)
        r5 = recall_u_als / n_eval
    else:
        p5 = tp_u_pop / (n_eval * TOP_N)
        r5 = recall_u_pop / n_eval
    log(f"Precision@{TOP_N}={p5:.4f}")
    log(f"Recall@{TOP_N} (media por usuario)={r5:.4f}")

log("")
log(f"Tiempo total: {time.time() - t0:.1f} s")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
