# Entrenamiento ALS implicito en numpy (SKLearn 1.2-1 no trae `implicit`). Entrada: canal "datos". Salida: modelo_svd.npz en SM_MODEL_DIR.
import argparse
import glob
import os

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix

REGULARIZACION = 0.01
ITERACIONES = 15
SEMILLA = 42
BLOQUE = 2000


def leer_ratings(directorio):
    archivos = sorted(f for f in glob.glob(os.path.join(directorio, "*")) if os.path.isfile(f))
    if not archivos:
        raise FileNotFoundError(f"sin archivos en {directorio}")
    origen = archivos[0]
    print("leyendo", origen, flush=True)
    if "jsonl" in origen or origen.endswith(".json"):
        df = pd.read_json(origen, lines=True)
    else:
        df = pd.read_csv(origen)
    df = df[["user_id", "parent_asin", "rating"]].dropna()
    return df.drop_duplicates(["user_id", "parent_asin"], keep="last")


def _resolver(C, F, reg):
    n, k = C.shape[0], F.shape[1]
    W = C.copy()
    W.data -= 1.0
    FF = (F[:, :, None] * F[:, None, :]).reshape(len(F), k * k)
    base = F.T @ F + reg * np.eye(k)
    out = np.empty((n, k))
    for ini in range(0, n, BLOQUE):
        fin = min(ini + BLOQUE, n)
        A = (W[ini:fin] @ FF).reshape(-1, k, k) + base
        b = C[ini:fin] @ F
        out[ini:fin] = np.linalg.solve(A, b[:, :, None])[:, :, 0]
    return out


def entrenar_als(R, k, reg=REGULARIZACION, iteraciones=ITERACIONES, semilla=SEMILLA):
    rng = np.random.RandomState(semilla)
    Rt = R.T.tocsr()
    V = rng.normal(scale=1 / np.sqrt(k), size=(R.shape[1], k))
    for _ in range(iteraciones):
        U = _resolver(R, V, reg)
        V = _resolver(Rt, U, reg)
    return U, V


def main():
    p = argparse.ArgumentParser()
    p.add_argument("-k", "--k", type=int, default=32)
    args = p.parse_args()

    canal = os.environ.get("SM_CHANNEL_DATOS", "/opt/ml/input/data/datos")
    modelo_dir = os.environ.get("SM_MODEL_DIR", "/opt/ml/model")
    os.makedirs(modelo_dir, exist_ok=True)

    df = leer_ratings(canal)
    u_cod, u_ids = pd.factorize(df["user_id"])
    i_cod, i_ids = pd.factorize(df["parent_asin"])
    R = csr_matrix(
        (df["rating"].to_numpy(dtype=np.float64), (u_cod, i_cod)),
        shape=(len(u_ids), len(i_ids)),
    )
    print(f"ratings={len(df)} usuarios={len(u_ids)} productos={len(i_ids)} k={args.k}", flush=True)

    U, V = entrenar_als(R, args.k)
    print("ALS terminado", flush=True)

    np.savez_compressed(
        os.path.join(modelo_dir, "modelo_svd.npz"),
        U=U.astype(np.float32),
        V=V.astype(np.float32),
        user_ids=np.asarray(u_ids, dtype=str),
        item_ids=np.asarray(i_ids, dtype=str),
        vistos_ptr=R.indptr,
        vistos=R.indices,
    )
    print("modelo guardado en", modelo_dir, flush=True)


if __name__ == "__main__":
    main()
