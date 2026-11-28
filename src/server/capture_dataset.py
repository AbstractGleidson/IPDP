"""
Captura do dataset a partir da ESP32 (rota /raw do firmware inspect_objectos).

Mostra a imagem ao vivo com a segmentação por cima, para conferir se a peça
está sendo bem separada do fundo ANTES de salvar.

Teclas
    1..5     escolhe a classe (ordem de config.CLASSES)
    + / -    muda o número da peça física (parafuso 1, parafuso 2, ...)
    espaço   salva a foto
    b        salva uma foto do fundo (bandeja VAZIA); tire de 5 a 10 no início da sessão
    f        captura o fundo também na ESP32 (usado pela E2); bandeja VAZIA
    m        alterna modo: "individual" (1 peça por foto) ou "multi" (várias peças, para teste)
    a        liga/desliga exposição automática
    [ / ]    diminui/aumenta a exposição manual
    q        sai

Uso
    python capture_dataset.py
    python capture_dataset.py --session s01 --url http://192.168.0.50
    python capture_dataset.py --webcam 0      # testa o fluxo com a webcam do notebook
"""

import argparse
import csv
import json
import time
from datetime import datetime
from pathlib import Path
import cv2
import numpy as np
import requests
import config as config
from esp32_client import ESP32
from image_process import load_background, process_image, draw

# campos de meta dados
METADATA_FIELDS = ["file", "label", "piece_id", "session", "mode", "timestamp", "width", "height", "n_pieces", "threshold"]

# Classe para comunicação com a esp32 
class ESP32Source:
    def __init__(self, url):
        self.esp = ESP32(url)

    # solicita frame para a esp32
    def read(self):
        return self.esp.raw().img

    # ajusta parametro da camera
    def set(self, var, val):
        try:
            self.esp.set(var, val)
        except requests.RequestException as e:
            print("Falha ao ajustar", var, e)

    # verifica o set de configurações
    def status(self):
        try:
            return self.esp.status()
        except (requests.RequestException, ValueError):
            return {}

    # recupera o fundo da imagem
    def capture_background(self):
        try:
            print("ESP32:", self.esp.capture_background())
            
        except requests.RequestException as e:
            print("Falha ao capturar o fundo na ESP32:", e)

# Classe para trabalhar com a webcam
class WebcamSource:
    """Só para testar o fluxo sem a ESP32."""
    
    def __init__(self, index):
        self.cap = cv2.VideoCapture(index)

    def read(self):
        ok, frame = self.cap.read()
        if not ok:
            raise IOError("webcam sem imagem")
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    def set(self, var, val):
        pass

    def status(self):
        return {}

    def capture_background(self):
        pass

# verifica a quantidade de fotos .png em uma pasta qualquer 
def next_index(folder: Path) -> int:
    return len(list(folder.glob("*.png"))) + 1

# escreve os dados usados na aquisição de frames
def append_metadata(metadata_csv: Path, row: dict):
    new = not metadata_csv.exists()
    
    with open(metadata_csv, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=METADATA_FIELDS)
        
        if new:
            w.writeheader()
            
        w.writerow(row)

# execução principal
def main():
    ap = argparse.ArgumentParser()
    
    # argumentos de linha de comando nomeados
    ap.add_argument("--url", default=config.ESP32_URL)
    ap.add_argument("--webcam", type=int, default=None)
    ap.add_argument("--session", default=datetime.now().strftime("%Y%m%d"),help="identificador da sessão (mude se mexer na luz ou na altura da câmera)")
    ap.add_argument("--data", default=str(config.DATA_DIR))
    
    args = ap.parse_args()

    paths = config.paths(args.data)
    
    # cria pastas 
    for k in ("raw", "background"):
        paths[k].mkdir(parents=True, exist_ok=True)

    # verifica qual camera sera usado
    source = WebcamSource(args.webcam) if args.webcam is not None else ESP32Source(args.url)

    # Guarda os ajustes do sensor desta sessão
    status = source.status()
    
    # grava dados usados para a aquisição dos dados
    if status:
        with open(paths["background"] / f"session_{args.session}.json", "w") as f:
            json.dump(status, f, indent=2)

    # carrega fundo
    background = load_background(paths["background"], args.session)
    
    if background is None:
        print("Sem fundo para esta sessão: esvazie a bandeja e aperte 'b' algumas vezes.")

    # dados da classe que tá sendo feito a aquisição
    class_idx, piece, mode = 0, 1, "individual"
    aec_auto, aec_value = bool(status.get("aec", 1)), int(status.get("aec_value", 300))
    fps_t, fps = time.time(), 0.0

    while True:
        try:
            img = source.read()
            
        except Exception as e:
            print("Erro na captura:", e)
            time.sleep(0.5)
            continue
        
        # faz o pré-processamento da imagem
        objects, mask, thres = process_image(img, background, ignore_border=False)
        valid = [o for o in objects if not o["touches_border"]]

        # dados da classe
        label = config.CLASSES[class_idx]
        now = time.time()
        fps = 0.9 * fps + 0.1 / max(now - fps_t, 1e-3)
        fps_t = now

        # desenha entorno da peça 
        vis = draw(img, objects, mask)
        
        n_saved = len(list((paths["raw"] / label).glob("*.png"))) if (paths["raw"] / label).exists() else 0
        
        # labels para frame
        lines = [
            f"classe: {label} [{class_idx + 1}]   peca: {piece:02d}   modo: {mode}",
            f"salvas desta classe: {n_saved}   pecas validas na imagem: {len(valid)}",
            f"fundo: {'ok' if background is not None else 'FALTA (b)'}   "
            f"exposicao: {'auto' if aec_auto else aec_value}   {fps:.1f} fps",
        ]
        
        # aplica labels
        for i, text in enumerate(lines):
            cv2.putText(vis, text, (8, 18 + 18 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
        
        cv2.imshow("Captura do dataset", vis)

        key = cv2.waitKey(1) & 0xFF
        
        # comandos da tela
        if key == ord("q"):
            break
        
        elif ord("1") <= key <= ord(str(len(config.CLASSES))):
            class_idx, piece = key - ord("1"), 1
            
        elif key in (ord("+"), ord("=")):
            piece += 1
            
        elif key == ord("-"):
            piece = max(1, piece - 1)
            
        elif key == ord("m"):
            mode = "multi" if mode == "individual" else "individual"
            
        elif key == ord("a"):
            aec_auto = not aec_auto
            source.set("aec", int(aec_auto))
            
            if not aec_auto:
                source.set("aec_value", aec_value)
                
        elif key in (ord("["), ord("]")) and not aec_auto:
            aec_value = int(np.clip(aec_value + (50 if key == ord("]") else -50), 0, 1200))
            source.set("aec_value", aec_value)
            
        elif key == ord("f"):
            source.capture_background()
            
        elif key == ord("b"):
            dest = paths["background"] / f"background_{args.session}_{next_index(paths['background']):03d}.png"
            cv2.imwrite(str(dest), img)
            background = load_background(paths["background"], args.session)
            print("Fundo salvo:", dest.name)
            
        elif key == ord(" "):
            if mode == "individual" and len(valid) != 1:
                print(f"NÃO salvo: modo individual exige 1 peça válida, há {len(valid)}.")
                continue
            
            folder = paths["raw"] / (label if mode == "individual" else "multi")
            folder.mkdir(parents=True, exist_ok=True)
            name = (f"{label}_p{piece:02d}_{args.session}_{next_index(folder):04d}.png" if mode == "individual" else f"multi_{args.session}_{next_index(folder):04d}.png")
            
            cv2.imwrite(str(folder / name), img)  # PNG: sem perdas, imagem original
            
            append_metadata(paths["metadata"], {
                "file": str((folder / name).relative_to(paths["raw"])),
                "label": label if mode == "individual" else "",
                "piece_id": f"{label}_{piece:02d}" if mode == "individual" else "",
                "session": args.session, "mode": mode,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "width": img.shape[1], "height": img.shape[0],
                "n_pieces": len(valid), "threshold": round(float(thres), 1),
            })
            
            print("Salvo:", name)

    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
