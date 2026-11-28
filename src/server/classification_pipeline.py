"""
Pipeline de CLASSIFICAÇÃO com a ESP32.

    E1: ESP32 captura e comprime a imagem (GI)  ->  servidor descomprime, segmenta,
        extrai descritores e classifica
    E2: ESP32 captura, segmenta e comprime a máscara (GI)  ->  servidor descomprime,
        extrai descritores e classifica

Modos
    ao vivo      mostra cada quadro classificado na tela
    experimento  repete cada configuração N vezes sobre uma cena fixa e grava um CSV

Uso
    python classification_pipeline.py                        # ao vivo, E2
    python classification_pipeline.py --strategy e1          # frame original com as peças identificadas
    python classification_pipeline.py --strategy e1 --bits 4
    python classification_pipeline.py --experiment --repetitions 30
    python classification_pipeline.py --experiment --bits 2 4 8 --no-jpeg

Teclas no modo ao vivo
    1 / 2      troca para E1 / E2
    + / -      muda os bits da E1
    o          mostra o frame original (/raw) também na E2 e na E1 com menos de 8 bits
    f          captura o fundo na ESP32 (bandeja vazia)
    s          salva a imagem e o resultado atuais
    q          sai
"""
import argparse
import csv
import time
from datetime import datetime

import cv2
import joblib
import numpy as np
import pandas as pd

import src.server.config as config
import src.server.image_process as ip
from src.server.esp32_client import ESP32

FIELDS = ["strategy", "param", "repetition", "bytes_received", "raw_bytes", "compression_ratio",
          "t_capture_ms", "t_edge_ms", "t_request_ms", "t_network_ms", "t_decompress_ms",
          "t_segment_ms", "t_descriptors_ms", "t_classify_ms", "t_server_ms", "t_total_ms",
          "n_pieces", "labels", "threshold"]


class Classifier:
    def __init__(self, path=config.MODEL_PATH):
        try:
            package = joblib.load(path)
        except FileNotFoundError:
            raise SystemExit(f"Modelo não encontrado em {path}. Rode o training_pipeline.py antes.")
        self.model = package["model"]
        self.features = package["features"]
        self.info = {k: package.get(k) for k in ("type", "params", "train_bits")}

    def __call__(self, objects):
        if not objects:
            return []
        X = np.array([[o["features"][c] for c in self.features] for o in objects], dtype=np.float64)
        return list(self.model.predict(X))


def process_frame(frame, background, classifier):
    """Etapas do servidor para um quadro. Devolve (objetos, classes, máscara, tempos)."""
    t = {}
    t0 = time.perf_counter()
    if frame.mask is None:  # E1: o servidor segmenta
        mask, frame.threshold = ip.segment(frame.img, background)
    else:                   # E2: a máscara já veio pronta
        mask = frame.mask
    t1 = time.perf_counter()
    objects = ip.process_mask(mask)
    t2 = time.perf_counter()
    labels = classifier(objects)
    t3 = time.perf_counter()
    t["t_segment_ms"] = (t1 - t0) * 1000
    t["t_descriptors_ms"] = (t2 - t1) * 1000
    t["t_classify_ms"] = (t3 - t2) * 1000
    return objects, labels, mask, t


def request(esp, strategy, param):
    if strategy == "E1":
        return esp.e1(param)
    if strategy == "E1-JPEG":
        return esp.e1_jpeg(param)
    if strategy == "E2-bits":
        return esp.e2("bits")
    return esp.e2("gi")


def csv_row(frame, strategy, param, rep, objects, labels, t):
    t_server = frame.t_decompress_ms + sum(t.values())
    return {
        "strategy": strategy, "param": param, "repetition": rep,
        "bytes_received": frame.bytes_received, "raw_bytes": frame.raw_bytes,
        "compression_ratio": round(frame.compression_ratio, 2),
        "t_capture_ms": round(frame.t_capture_ms, 2), "t_edge_ms": round(frame.t_edge_ms, 2),
        "t_request_ms": round(frame.t_request_ms, 2),
        "t_network_ms": round(frame.t_request_ms - frame.t_capture_ms - frame.t_edge_ms, 2),
        "t_decompress_ms": round(frame.t_decompress_ms, 2),
        **{k: round(v, 2) for k, v in t.items()},
        "t_server_ms": round(t_server, 2), "t_total_ms": round(frame.t_request_ms + t_server, 2),
        "n_pieces": len(objects), "labels": ";".join(labels), "threshold": frame.threshold,
    }


# ============================================================
# Modo experimento
# ============================================================

def run_experiment(esp, background, clf, args):
    configs = [("E1", b) for b in args.bits]
    if not args.no_jpeg:
        configs += [("E1-JPEG", q) for q in config.E1_JPEG_Q]
    configs += [("E2", "gi"), ("E2-bits", "sem compressão")]

    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = config.RESULTS_DIR / f"experiment_{datetime.now():%Y%m%d_%H%M%S}.csv"
    print(f"{len(configs)} configurações x {args.repetitions} repetições -> {out_file}\n")

    with open(out_file, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        request(esp, *configs[0])  # aquecimento: abre a conexão, não entra na medição
        for strategy, param in configs:
            for rep in range(1, args.repetitions + 1):
                frame = request(esp, strategy, param)
                objects, labels, _, t = process_frame(frame, background, clf)
                w.writerow(csv_row(frame, strategy, param, rep, objects, labels, t))
            print(f"  {strategy:8s} {str(param):>15s}: {frame.bytes_received:7d} bytes | "
                  f"{frame.t_request_ms:6.1f} ms | {len(objects)} peças | {', '.join(labels)}")

    df = pd.read_csv(out_file)
    summary = df.groupby(["strategy", "param"], sort=False).agg(
        bytes=("bytes_received", "mean"), ratio=("compression_ratio", "mean"),
        edge_ms=("t_edge_ms", "mean"), network_ms=("t_network_ms", "mean"),
        server_ms=("t_server_ms", "mean"), total_ms=("t_total_ms", "mean"),
        total_std=("t_total_ms", "std"), pieces=("n_pieces", "mean")).round(1)
    print("\nMédias por configuração:\n" + summary.to_string())
    summary.to_csv(out_file.with_name(out_file.stem + "_summary.csv"))


# ============================================================
# Modo ao vivo
# ============================================================

# Uma cor por classe (BGR), na ordem de config.CLASSES
COLORS = [(245, 135, 66), (0, 170, 255), (60, 200, 60), (220, 60, 220), (0, 220, 255),
          (255, 255, 0), (120, 120, 255)]


def class_color(name):
    return COLORS[config.CLASSES.index(name) % len(COLORS)] if name in config.CLASSES else (200, 200, 200)


def draw_label(vis, text, x, y, color):
    """Texto com fundo colorido, acima de (x, y) ou abaixo se não couber."""
    (tw, th), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    y0 = y - th - base - 4 if y - th - base - 4 >= 0 else y + 2
    x0 = max(0, min(x, vis.shape[1] - tw - 6))
    cv2.rectangle(vis, (x0, y0), (x0 + tw + 6, y0 + th + base + 4), color, -1)
    cv2.putText(vis, text, (x0 + 3, y0 + th + 2), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA)


def draw_scene(img, objects, labels, cut_objects, info_lines):
    """Frame em cinza com cada peça contornada e identificada pela classe."""
    vis = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img.copy()
    pad = config.CROP_PAD

    for o, label in zip(objects, labels):
        x, y, w, h = o["bbox"]
        color = class_color(label)
        contours, _ = cv2.findContours((o["mask"] > 0).astype(np.uint8), cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE, offset=(x - pad, y - pad))
        cv2.drawContours(vis, contours, -1, color, 2, cv2.LINE_AA)
        cv2.rectangle(vis, (x - 4, y - 4), (x + w + 4, y + h + 4), color, 1)
        draw_label(vis, label.replace("_", " "), x - 4, y - 4, color)

    for o in cut_objects:  # peças encostadas na borda: aparecem, mas não são classificadas
        x, y, w, h = o["bbox"]
        cv2.rectangle(vis, (x, y), (x + w, y + h), (150, 150, 150), 1)
        draw_label(vis, "cortada pela borda", x, y, (150, 150, 150))

    if not objects:
        msg = "nenhuma peca na cena" if not cut_objects else "peca cortada: centralize na bandeja"
        (tw, th), _ = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
        cv2.putText(vis, msg, ((vis.shape[1] - tw) // 2, (vis.shape[0] + th) // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2, cv2.LINE_AA)

    # faixa de informações acima da imagem e ajuda abaixo, sem cobrir a cena
    width = vis.shape[1]
    top = np.zeros((8 + 18 * len(info_lines), width, 3), np.uint8)
    for i, text in enumerate(info_lines):
        cv2.putText(top, text, (8, 18 + 18 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    bottom = np.zeros((22, width, 3), np.uint8)
    cv2.putText(bottom, "1/2: E1/E2  +/-: bits  o: frame original  f: fundo  s: salvar  q: sair",
                (8, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 200), 1, cv2.LINE_AA)
    return np.vstack([top, vis, bottom])


def run_live(esp, background, clf, args):
    strategy = "E1" if args.strategy == "e1" else "E2"
    bits = args.bits[0]
    show_original = args.original_frame
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        try:
            frame = request(esp, strategy, bits if strategy == "E1" else "gi")
        except Exception as e:
            print("Erro no pedido:", e)
            time.sleep(0.5)
            continue
        objects, labels, mask, t = process_frame(frame, background, clf)
        row = csv_row(frame, strategy, bits, 0, objects, labels, t)
        cut_objects = [o for o in ip.components(mask) if o["touches_border"]]

        # Qual imagem mostrar:
        #   E1: o frame recebido (com 8 bits é idêntico ao original; com menos bits, quantizado)
        #   E2: a placa só manda a máscara
        #   'o' ligado: busca o frame original em /raw só para exibir (fora das medidas de tempo)
        if show_original and not (strategy == "E1" and bits == 8):
            try:
                base, source = esp.raw().img, "original (/raw, fora das medidas)"
            except Exception:
                base, source = (frame.img if frame.img is not None else mask), "recebido"
        elif frame.img is not None:
            base = frame.img
            source = "original" if bits == 8 else f"recebido ({bits} bits)"
        else:
            base, source = mask, "mascara recebida"

        counts = ", ".join(f"{labels.count(c)}x {c.replace('_', ' ')}" for c in dict.fromkeys(labels))
        info = [f"{strategy}{f' | {bits} bits' if strategy == 'E1' else ''} | "
                f"{row['bytes_received']} B ({row['compression_ratio']}:1) | imagem: {source}",
                f"borda {row['t_edge_ms']:.0f} ms | rede {max(row['t_network_ms'], 0):.0f} ms | "
                f"servidor {row['t_server_ms']:.0f} ms | total {row['t_total_ms']:.0f} ms",
                f"{len(objects)} peca(s): {counts or '-'}"]
        vis = draw_scene(base, objects, labels, cut_objects, info)
        cv2.imshow("Classificacao", vis)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("1"):
            strategy = "E1"
        elif key == ord("2"):
            strategy = "E2"
        elif key in (ord("+"), ord("=")):
            bits = min(8, bits + 1)
        elif key == ord("-"):
            bits = max(1, bits - 1)
        elif key == ord("o"):
            show_original = not show_original
        elif key == ord("f"):
            print("ESP32:", esp.capture_background())
            background = esp.background()
        elif key == ord("s"):
            name = config.RESULTS_DIR / f"frame_{datetime.now():%Y%m%d_%H%M%S}"
            cv2.imwrite(f"{name}.png", vis)
            print(f"Salvo {name}.png | {row}")
    cv2.destroyAllWindows()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=config.ESP32_URL)
    ap.add_argument("--model", default=str(config.MODEL_PATH))
    ap.add_argument("--strategy", default="e2", choices=["e1", "e2"], help="modo ao vivo")
    ap.add_argument("--original-frame", action="store_true",
                    help="ao vivo: mostra o frame original (/raw) mesmo na E2 ou na E1 com menos de 8 bits")
    ap.add_argument("--bits", nargs="+", type=int, default=None,
                    help="bits da E1 (ao vivo: o primeiro; experimento: todos)")
    ap.add_argument("--experiment", action="store_true")
    ap.add_argument("--repetitions", type=int, default=20)
    ap.add_argument("--no-jpeg", action="store_true", help="experimento sem as rodadas de JPEG")
    args = ap.parse_args()
    if args.bits is None:
        args.bits = config.E1_BITS if args.experiment else [8]

    esp = ESP32(args.url)
    status = esp.status()
    expected = {"obj_claro": config.BRIGHT_OBJECT, "gauss_k": config.GAUSS_K,
                "open_k": config.OPEN_K, "close_k": config.CLOSE_K}
    diff = {k: (status.get(k), v) for k, v in expected.items() if status.get(k) != v}
    if diff:
        print("ATENÇÃO: segmentação da ESP32 diferente do config.py (ESP32, Python):", diff)

    background = esp.background()  # a E1 usa o mesmo fundo que a placa usa na E2
    print(f"ESP32 em {args.url} | ROI {status.get('largura')}x{status.get('altura')} | "
          f"fundo: {'sim' if background is not None else 'não'}")
    clf = Classifier(args.model)
    print(f"Modelo: {clf.info}")

    if args.experiment:
        run_experiment(esp, background, clf, args)
    else:
        run_live(esp, background, clf, args)


if __name__ == "__main__":
    main()
