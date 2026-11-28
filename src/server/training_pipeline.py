"""
Pipeline de TREINAMENTO.

    1. Extração   lê data/metadata.csv, segmenta cada foto (mesma segmentação da ESP32)
                  e calcula os descritores da peça -> data/features.csv
    2. Divisão    separa treino e teste POR PEÇA FÍSICA (piece_id)
    3. Treino     k-means (k_means.py), k-NN e SVM, com hiperparâmetros por validação
                  cruzada agrupada no treino; avaliação no teste
    4. Compressão (offline) acurácia e bytes da E1 em cada nível de bits e da E2,
                  nas mesmas peças de teste -> curva de compromisso para o relatório
    5. Modelo     melhor configuração treinada com todos os dados -> server/models/

Uso
    python training_pipeline.py
    python training_pipeline.py --model svm --features hu shape
    python training_pipeline.py --train-bits 4      # treina com imagens como chegam na E1 com 4 bits
    python training_pipeline.py --no-compression    # pula a etapa 4
"""

import argparse
import csv
import json
import cv2
import joblib
import matplotlib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import (ConfusionMatrixDisplay, accuracy_score, classification_report, confusion_matrix, f1_score)
from sklearn.model_selection import GridSearchCV, StratifiedGroupKFold, StratifiedKFold
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
import src.server.config as config
import src.server.gi_decoder as gi_decoder
import src.server.image_process as ip
from src.server.k_means import KMeansClassifier

matplotlib.use("Agg")
import matplotlib.pyplot as plt 

# Constantes da imagem
GROUPS = {"hu": ip.HU_NAMES, "shape": ip.SHAPE_NAMES, "size": ip.SIZE_NAMES}

# modelos treinados
MODELS = {
    "kmeans": (KMeansClassifier(n_init=10, random_state=0), {"clf__n_clusters": [5, 8, 10, 15, 20]}),
    "knn": (KNeighborsClassifier(), {"clf__n_neighbors": [1, 3, 5, 7, 9]}),
    "svm": (SVC(), {"clf__C": [0.1, 1, 10, 100], "clf__kernel": ["linear", "rbf"]}),
}


# Extração
class Extractor:
    """Carrega fotos e fundos do dataset e devolve os descritores da peça de cada foto."""

    def __init__(self, data_dir):
        self.paths = config.paths(data_dir)
        self._backgrounds = {}

    def rows(self):
        if not self.paths["metadata"].exists():
            raise SystemExit(f"Não achei {self.paths['metadata']}. Monte o dataset com capture_dataset.py.")
        
        with open(self.paths["metadata"]) as f:
            return [r for r in csv.DictReader(f) if r["mode"] == "individual"]

    def background(self, session):
        if session not in self._backgrounds:
            self._backgrounds[session] = ip.load_background(self.paths["background"], session)
        return self._backgrounds[session]

    def image(self, row, bits=8):
        img = cv2.imread(str(self.paths["raw"] / row["file"]), cv2.IMREAD_GRAYSCALE)
        if img is not None and bits < 8:
            img = gi_decoder.quantize(img, bits)  # exatamente o que a E1 entrega após descomprimir
        return img

    def features(self, rows, bits=8, save_masks=False):
        out, discarded = [], []
        for row in rows:
            img = self.image(row, bits)
            if img is None:
                discarded.append((row["file"], "arquivo não encontrado"))
                continue
            objects, _, _ = ip.process_image(img, self.background(row["session"]), ignore_border=True)
            if len(objects) != 1:
                discarded.append((row["file"], f"{len(objects)} peças segmentadas"))
                continue
            out.append({"file": row["file"], "label": row["label"], "piece_id": row["piece_id"],
                        "session": row["session"], **objects[0]["features"]})
            if save_masks:
                dest = self.paths["processed"] / row["file"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(dest), objects[0]["mask"])
        return pd.DataFrame(out), discarded


# Divisão por peça física
def make_cv(y, g, n_max):
    n = min(n_max, min(len(set(g[y == c])) for c in np.unique(y)))
  
    if n >= 2:
        return StratifiedGroupKFold(n_splits=n, shuffle=True, random_state=0), True
  
    print("AVISO: poucas peças físicas por classe; usando divisão por foto (resultado otimista).")
    
    return StratifiedKFold(n_splits=3, shuffle=True, random_state=0), False


# Treino e avaliação
def train(name, X_tr, y_tr, g_tr, n_classes):
    clf, grid = MODELS[name]
    
    if name == "kmeans":  # pelo menos um grupo por classe e não mais grupos que amostras
        grid = {"clf__n_clusters": [k for k in grid["clf__n_clusters"] if n_classes <= k <= len(y_tr) // 2] or [n_classes]}
    
    cv, _ = make_cv(y_tr, g_tr, n_max=4)
    search = GridSearchCV(Pipeline([("scaler", StandardScaler()), ("clf", clone(clf))]), grid, cv=cv, scoring="f1_macro", n_jobs=-1)
    search.fit(X_tr, y_tr, groups=g_tr)
    
    return search

def save_confusion_matrix(y_true, pred, classes, title, path):
    disp = ConfusionMatrixDisplay(confusion_matrix(y_true, pred, labels=classes), display_labels=classes)
    disp.plot(cmap="Blues", colorbar=False, xticks_rotation=30)
    plt.title(title)
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


# Compressão (offline)
def evaluate_compression(ext, test_rows, models, columns, classes, out_dir, plot_model):
    """Acurácia e tamanho médio do pacote para cada nível da E1 e para a E2, nas peças de teste."""
  
    results = []
    configs = ([("E1", b) for b in config.E1_BITS] + [("E1-JPEG", q) for q in config.E1_JPEG_Q] + [("E2", "gi")])

    for strategy, param in configs:
        sizes, feats, y = [], [], []
        
        for row in test_rows:
            original = ext.image(row, 8)
        
            if original is None:
                continue
        
            background = ext.background(row["session"])
        
            if strategy == "E1":
                sizes.append(gi_decoder.compressed_size(original, param))
                objects, _, _ = ip.process_image(gi_decoder.quantize(original, param), background)
        
            elif strategy == "E1-JPEG":
                _, buf = cv2.imencode(".jpg", original, [cv2.IMWRITE_JPEG_QUALITY, param])
                sizes.append(len(buf))
                objects, _, _ = ip.process_image(cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE), background)
        
            else:  # E2: a placa segmenta a imagem original e manda a máscara sem perdas
                mask, _ = ip.segment(original, background)
                sizes.append(gi_decoder.compressed_size((mask > 0).astype(np.uint8), 8))
                objects = ip.process_mask(mask)
            
            feats.append([objects[0]["features"][c] for c in columns] if len(objects) == 1 else None)
            y.append(row["label"])

        raw_size = original.size if strategy != "E2" else (original.size + 7) // 8
        valid = [i for i, f in enumerate(feats) if f is not None]
        X = np.array([feats[i] for i in valid], dtype=np.float64)
        y_valid = np.array([y[i] for i in valid])
        
        for name, model in models.items():
            pred = model.predict(X) if len(X) else np.array([])
            hits = int((pred == y_valid).sum()) if len(X) else 0  # falha de segmentação conta como erro
            results.append({
                "strategy": strategy, "param": param, "model": name,
                "mean_bytes": round(float(np.mean(sizes)), 1),
                "raw_bytes": raw_size,
                "accuracy": round(hits / len(y), 4) if y else None,
                "f1_macro": round(float(f1_score(y_valid, pred, average="macro", labels=classes, zero_division=0)), 4) if len(X) else 0.0,
                "segmentation_failures": len(y) - len(valid),
            })

    df = pd.DataFrame(results)
    df.to_csv(out_dir / "compression_offline.csv", index=False)

    # curva de compromisso: bytes x acurácia
    fig, ax = plt.subplots(figsize=(7, 4.5))
    d = df[(df.model == plot_model) & (df.strategy == "E1")]
    ax.plot(d.mean_bytes, d.accuracy, "o-", label="E1: imagem em GI (bits por pixel)")
    
    for _, r in d.iterrows():
        ax.annotate(f"{r.param}b", (r.mean_bytes, r.accuracy), fontsize=7, textcoords="offset points", xytext=(3, 3))
    
    d = df[(df.model == plot_model) & (df.strategy == "E1-JPEG")]
    ax.plot(d.mean_bytes, d.accuracy, "s--", alpha=0.6, label="E1: imagem em JPEG (OpenCV)")
    d = df[(df.model == plot_model) & (df.strategy == "E2")]
    ax.plot(d.mean_bytes, d.accuracy, "*", markersize=14, label="E2: máscara em GI")
    ax.set_xscale("log")
    ax.set_xlabel("bytes por quadro (escala log)")
    ax.set_ylabel("acurácia no teste")
    ax.set_title(f"Compromisso entre tamanho transmitido e acurácia ({plot_model})")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(out_dir / "tradeoff_curve.png", dpi=150)
    plt.close(fig)
   
    return df

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(config.DATA_DIR))
    ap.add_argument("--features", nargs="+", default=["hu", "shape", "size"], choices=list(GROUPS))
    ap.add_argument("--model", default="kmeans", choices=list(MODELS), help="modelo salvo para a classificação")
    ap.add_argument("--train-bits", type=int, default=8, choices=range(1, 9), help="treinar com as imagens quantizadas como chegam na E1 (8 = originais)")
    ap.add_argument("--no-compression", action="store_true", help="pula a avaliação offline da compressão")
    ap.add_argument("--no-masks", action="store_true", help="não salva as máscaras em data/processed")
    
    args = ap.parse_args()

    out_dir = config.RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    columns = [c for g in args.features for c in GROUPS[g]]

    # 1. extração 
    ext = Extractor(args.data)
    rows = ext.rows()
    
    print(f"[1/5] Extraindo descritores de {len(rows)} fotos (bits = {args.train_bits})...")
    df, discarded = ext.features(rows, args.train_bits, save_masks=not args.no_masks)
    
    if df.empty:
        raise SystemExit("Nenhuma peça extraída: confira a segmentação.")
    
    df.to_csv(ext.paths["features"], index=False)
    classes = [c for c in config.CLASSES if c in set(df.label)]
    
    for c in classes:
        d = df[df.label == c]
        print(f"{c:20s} {len(d):4d} fotos de {d.piece_id.nunique():2d} peças")
    
    if discarded:
        print(f"{len(discarded)} fotos descartadas (ex.: {discarded[0][0]}: {discarded[0][1]})")

    X = df[columns].to_numpy(np.float64)
    y = df.label.to_numpy()
    g = df.piece_id.to_numpy()

    # 2. divisão
    splitter, grouped = make_cv(y, g, n_max=5)
    idx_tr, idx_te = next(splitter.split(X, y, g))
    print(f"[2/5] Treino: {len(idx_tr)} fotos | teste: {len(idx_te)} fotos"
          f"{' (peças diferentes)' if grouped else ''}")

    # 3. treino 
    print("[3/5] Treinando...")
    summary, best = {}, {}

    for name in MODELS:
        search = train(name, X[idx_tr], y[idx_tr], g[idx_tr], len(classes))
        pred = search.predict(X[idx_te])
        acc = accuracy_score(y[idx_te], pred)
        f1 = f1_score(y[idx_te], pred, average="macro")
        best[name] = search.best_estimator_
        summary[name] = {"params": search.best_params_, "f1_cv": round(float(search.best_score_), 4), "test_accuracy": round(float(acc), 4), "test_f1": round(float(f1), 4)}
        
        print(f"{name:6s} acurácia {acc:.3f} | F1 {f1:.3f} | {search.best_params_}")
        save_confusion_matrix(y[idx_te], pred, classes, f"{name}: acurácia {acc:.2f}", out_dir / f"confusion_matrix_{name}.png")
    
    print(classification_report(y[idx_te], best[args.model].predict(X[idx_te]), labels=classes, zero_division=0))

    # 4. compressão 
    if not args.no_compression:
        print("[4/5] Avaliando a compressão nas peças de teste (offline)...")
        test_files = set(df.iloc[idx_te].file)
        test_rows = [r for r in rows if r["file"] in test_files]
        comp = evaluate_compression(ext, test_rows, best, columns, classes, out_dir, args.model)
        print(comp[comp.model == args.model][["strategy", "param", "mean_bytes", "accuracy", "segmentation_failures"]].to_string(index=False))
    
    else:
        print("[4/5] Avaliação da compressão pulada.")

    # 5. modelo final 
    final = clone(best[args.model]).fit(X, y)
    package = {"model": final, "features": columns, "classes": classes, "type": args.model, "params": summary[args.model]["params"], "train_bits": args.train_bits}
    joblib.dump(package, config.MODEL_PATH)
    
    with open(out_dir / "training_summary.json", "w") as f:
        json.dump({"features": columns, "train_bits": args.train_bits, "models": summary}, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"[5/5] Modelo '{args.model}' salvo em {config.MODEL_PATH}")
    print(f"Resultados em {out_dir}")

if __name__ == "__main__":
    main()
