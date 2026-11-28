"""
Confere se a segmentação da ESP32 (E2) é idêntica à do Python (E1 e treino)
e se a compressão GI das rotas /e1 e /e2 volta sem erro.

Para cada repetição pede /paridade (imagem em cinza + máscara do MESMO quadro),
segmenta a imagem em Python, compara pixel a pixel e mostra numa janela:

    quadro em cinza | máscara da ESP32 | máscara do Python | diferenças

Nas diferenças, vermelho = só a ESP32 marcou, verde = só o Python marcou.
O esperado é 0 pixels diferentes.

Uso
    python parity_test.py
    python parity_test.py --times 10
    python parity_test.py --no-window       # só texto (ex.: via SSH)
    python parity_test.py --save            # grava os painéis em results/parity/

Teclas na janela: qualquer tecla avança, q encerra.
"""

import argparse
from datetime import datetime

import cv2
import numpy as np

import config as config
from esp32_client import ESP32
from image_process import segment

def add_title(img, text):
    out = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img.copy()
    cv2.rectangle(out, (0, 0), (out.shape[1], 24), (0, 0, 0), -1)
    cv2.putText(out, text, (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
    return out

def make_panel(gray, mask_esp, mask_py, thres_esp, thres_py, n_diff):
    m_esp = mask_esp.astype(bool)
    m_py = mask_py > 0
    diff = np.zeros(gray.shape + (3,), np.uint8)
    diff[m_esp & m_py] = (90, 90, 90)        # iguais (peça): cinza
    diff[m_esp & ~m_py] = (0, 0, 255)        # só ESP32: vermelho
    diff[~m_esp & m_py] = (0, 255, 0)        # só Python: verde
    top = np.hstack([add_title(gray, "quadro (cinza)"),
                     add_title(m_esp.astype(np.uint8) * 255, f"mascara ESP32 (limiar {thres_esp})")])
    bottom = np.hstack([add_title(m_py.astype(np.uint8) * 255, f"mascara Python (limiar {thres_py})"),
                        add_title(diff, f"diferencas: {n_diff} px")])
    grid = np.vstack([top, bottom])
    if grid.shape[1] > 1400:  # cabe na tela
        scale = 1400 / grid.shape[1]
        grid = cv2.resize(grid, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        
    return grid

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=config.ESP32_URL)
    ap.add_argument("--times", type=int, default=5)
    ap.add_argument("--no-window", action="store_true")
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()

    esp = ESP32(args.url)
    status = esp.status()
    expected = {"obj_claro": config.BRIGHT_OBJECT, "gauss_k": config.GAUSS_K,
                "open_k": config.OPEN_K, "close_k": config.CLOSE_K}
    diff = {k: (status.get(k), v) for k, v in expected.items() if status.get(k) != v}
    if diff:
        print("ATENÇÃO: constantes diferentes entre firmware e config.py (ESP32, Python):", diff)
    background = esp.background()
    print(f"Fundo na ESP32: {'sim' if background is not None else 'não'}")

    out_dir = config.RESULTS_DIR / "parity"
    if args.save:
        out_dir.mkdir(parents=True, exist_ok=True)

    ok = True
    for i in range(args.times):
        gray, mask_esp, h = esp.parity()
        mask_py, thres_py = segment(gray, background if h.get("X-Fundo") == "1" else None)
        n_diff = int(np.count_nonzero(mask_esp.astype(bool) != (mask_py > 0)))
        thres_esp = int(h["X-Threshold"])
        print(f"[{i + 1}] limiar ESP32 {thres_esp} | Python {thres_py} | pixels diferentes: {n_diff}")
        ok &= n_diff == 0 and thres_esp == thres_py

        vis = make_panel(gray, mask_esp, mask_py, thres_esp, thres_py, n_diff)
        if args.save or n_diff:
            out_dir.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(out_dir / f"parity_{datetime.now():%H%M%S}_{i + 1}.png"), vis)
        if not args.no_window:
            cv2.imshow("Teste de paridade", vis)
            if (cv2.waitKey(0) & 0xFF) == ord("q"):
                break

    print("\nSegmentação: OK, idêntica." if ok else
          f"\nSegmentação: DIFERENÇAS encontradas (painéis salvos em {out_dir}).")

    # compressão 
    try:
        f_gi, f_bits = esp.e2("gi"), esp.e2("bits")
        n_diff_e2 = int(np.count_nonzero(f_gi.mask != f_bits.mask))
        print(f"E2: GI {f_gi.bytes_received} B x sem compressão {f_bits.bytes_received} B "
              f"({f_bits.bytes_received / f_gi.bytes_received:.0f}x menor) | "
              f"pixels diferentes: {n_diff_e2} (cena parada: o esperado é 0 ou quase 0)")
        for bits in (8, 4):
            f = esp.e1(bits)
            print(f"E1 com {bits} bits: {f.bytes_received} B para {f.raw_bytes} B crus "
                  f"({f.compression_ratio:.2f}:1) | compressão na placa {f.t_edge_ms:.1f} ms | "
                  f"descompressão {f.t_decompress_ms:.1f} ms")
        print("Compressão: OK.")
    except RuntimeError as e:
        print(f"\nCompressão: FALHOU.\n{e}")

    if not args.no_window:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
