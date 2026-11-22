import os
import time

import numpy as np
import pandas as pd
import scipy.sparse as sp
from implicit.cpu.als import AlternatingLeastSquares

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "..", "datos", "Industrial_and_Scientific.csv")
OUT = os.path.join(BASE, "als_resultados.txt")

FACTORS = 32
SEED = 42
MIN_INTERACCIONES = 5
TEST_SIZE = 0.2
TOP_N = 5
RELEVANTE_MIN = 4.0
BATCH = 1000

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
    (train["rating"].values, (train["u"].values, train["i"].values)),
    shape=(n_users, n_items),
)
Rel_test = sp.csr_matrix(
    ((test["rating"].values >= RELEVANTE_MIN).astype(np.float64),
     (test["u"].values, test["i"].values)),
    shape=(n_users, n_items),
)
Rel_test.eliminate_zeros()

pop = np.asarray(R_train.getnnz(axis=0)).ravel().astype(np.float64)
R_train_csr = R_train.tocsr()
test_users = np.unique(Rel_test.nonzero()[0])

log(f"ALS implicit: factors={FACTORS}, regularization=0.01 (defecto), iterations=15 (defecto), "
    f"confianza = rating de train")
t1 = time.time()
model = AlternatingLeastSquares(factors=FACTORS, random_state=SEED)
model.fit(R_train_csr, show_progress=False)
log(f"Entrenamiento ALS: {time.time() - t1:.1f} s")

hits_als = 0.0
hits_pop = 0.0
n_eval = 0
for start in range(0, len(test_users), BATCH):
    bu = test_users[start:start + BATCH]
    ids, _ = model.recommend(bu, R_train_csr[bu], N=TOP_N, filter_already_liked_items=True)
    scores_pop = np.broadcast_to(pop, (len(bu), n_items)).copy()
    Rtr_b = R_train_csr[bu].tocoo()
    scores_pop[Rtr_b.row, Rtr_b.col] = -np.inf
    top_pop = np.argpartition(-scores_pop, TOP_N, axis=1)[:, :TOP_N]
    rows = np.repeat(bu, TOP_N)
    hits_als += np.asarray(Rel_test[rows, ids.ravel()]).ravel().sum()
    hits_pop += np.asarray(Rel_test[rows, top_pop.ravel()]).ravel().sum()
    n_eval += len(bu)

p5_als = hits_als / (n_eval * TOP_N)
p5_pop = hits_pop / (n_eval * TOP_N)

log("")
log("== Ranking (Precision@5) ==")
log(f"Usuarios evaluados (con >=1 item relevante en test, rating>={RELEVANTE_MIN}): {n_eval}")
log(f"Relevantes en test: {Rel_test.nnz}")
log("Candidatos: items no vistos por el usuario en train")
log(f"Precision@5 ALS (implicit, {FACTORS} factores): {p5_als:.4f}")
log(f"Precision@5 Popularidad:  {p5_pop:.4f}")
log(f"ALS supera a popularidad: {'SI' if p5_als > p5_pop else 'NO'}")
log(f"Tiempo total: {time.time() - t0:.1f} s")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
