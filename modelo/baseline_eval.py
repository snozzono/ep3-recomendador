import os
import time

import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.sparse.linalg import svds

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "..", "datos", "Industrial_and_Scientific.csv")
OUT = os.path.join(BASE, "baseline_resultados.txt")

K = 32
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
log(f"Usuarios unicos (crudo): {df['user_id'].nunique()}")
log(f"Items unicos (crudo): {df['parent_asin'].nunique()}")

dup = df.duplicated(["user_id", "parent_asin"]).sum()
df = df.drop_duplicates(["user_id", "parent_asin"]).reset_index(drop=True)
log(f"Pares usuario-item duplicados eliminados: {dup}")

rondas = 0
while True:
    uc = df.groupby("user_id")["rating"].transform("size")
    ic = df.groupby("parent_asin")["rating"].transform("size")
    keep = (uc >= MIN_INTERACCIONES) & (ic >= MIN_INTERACCIONES)
    rondas += 1
    if keep.all():
        break
    df = df[keep].reset_index(drop=True)
log(f"Filtro k-core (>= {MIN_INTERACCIONES} por usuario e item): {rondas} ronda(s), "
    f"el archivo ya era 5-core asi que no deberia quitar filas")

u_codes, u_uniques = pd.factorize(df["user_id"])
i_codes, i_uniques = pd.factorize(df["parent_asin"])
df["u"] = u_codes
df["i"] = i_codes
n_users = len(u_uniques)
n_items = len(i_uniques)
n_inter = len(df)
log(f"Tras filtro: usuarios={n_users}, items={n_items}, interacciones={n_inter}")
log(f"Densidad: {n_inter / (n_users * n_items):.6%}")
dense_gb = n_users * n_items * 8 / 1e9
log(f"Matriz densa float64 costaria {dense_gb:.2f} GB -> se usa scipy.sparse (CSR)")

rng = np.random.RandomState(SEED)
perm = rng.permutation(n_inter)
n_test = int(round(TEST_SIZE * n_inter))
test = df.iloc[perm[:n_test]]
train = df.iloc[perm[n_test:]]
log(f"Split aleatorio 80/20 (semilla {SEED}): train={len(train)}, test={len(test)}")
log(f"Usuarios en test sin ninguna interaccion en train: "
    f"{len(set(test['u']) - set(train['u']))}")
log(f"Items en test sin ninguna interaccion en train: "
    f"{len(set(test['i']) - set(train['i']))}")

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

mu = train["rating"].mean()
log(f"Media global de train: {mu:.4f}")

U, s, Vt = svds(R_train.astype(np.float64), k=K, random_state=SEED)
order = np.argsort(-s)
U, s, Vt = U[:, order], s[order], Vt[order, :]
log(f"SVD (scipy svds, k={K}) sobre matriz train con ceros en no observados")
log(f"Valores singulares: max={s[0]:.4f}, min={s[-1]:.4f}")

Us = U * s
ut = test["u"].values
it = test["i"].values
r_test = test["rating"].values
pred_raw = (Us[ut] * Vt[:, it].T).sum(axis=1)
pred_clip = np.clip(pred_raw, 1.0, 5.0)
rmse_svd_raw = np.sqrt(np.mean((pred_raw - r_test) ** 2))
rmse_svd = np.sqrt(np.mean((pred_clip - r_test) ** 2))
rmse_media = np.sqrt(np.mean((mu - r_test) ** 2))

log("")
log("== RMSE (sobre todas las interacciones de test) ==")
log(f"Media global: {rmse_media:.4f}")
log(f"SVD (sin recorte):   {rmse_svd_raw:.4f}")
log(f"SVD (recortado 1-5): {rmse_svd:.4f}")

pop = np.asarray(R_train.getnnz(axis=0)).ravel().astype(np.float64)
train_items_by_user = R_train.tocsr()

test_users = np.unique(Rel_test.nonzero()[0])
hits_svd = 0.0
hits_pop = 0.0
n_eval = 0
for start in range(0, len(test_users), BATCH):
    bu = test_users[start:start + BATCH]
    scores_svd = Us[bu] @ Vt
    scores_pop = np.broadcast_to(pop, (len(bu), n_items)).copy()
    Rtr_b = train_items_by_user[bu].tocoo()
    scores_svd[Rtr_b.row, Rtr_b.col] = -np.inf
    scores_pop[Rtr_b.row, Rtr_b.col] = -np.inf
    top_svd = np.argpartition(-scores_svd, TOP_N, axis=1)[:, :TOP_N]
    top_pop = np.argpartition(-scores_pop, TOP_N, axis=1)[:, :TOP_N]
    rows = np.repeat(bu, TOP_N)
    hits_svd += np.asarray(Rel_test[rows, top_svd.ravel()]).ravel().sum()
    hits_pop += np.asarray(Rel_test[rows, top_pop.ravel()]).ravel().sum()
    n_eval += len(bu)

p5_svd = hits_svd / (n_eval * TOP_N)
p5_pop = hits_pop / (n_eval * TOP_N)

log("")
log("== Ranking (Precision@5) ==")
log(f"Usuarios evaluados (con >=1 item relevante en test, rating>={RELEVANTE_MIN}): {n_eval}")
log(f"Relevantes en test: {Rel_test.nnz}")
log("Candidatos: items no vistos por el usuario en train")
log(f"Precision@5 SVD:        {p5_svd:.4f}")
log(f"Precision@5 Popularidad:{p5_pop:.4f}")
log(f"Tiempo total: {time.time() - t0:.1f} s")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
