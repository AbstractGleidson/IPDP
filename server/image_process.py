from pathlib import Path

import cv2
import numpy as np
import config 
from moments import moments, feature_vector

# constantes 
NOMES_HU = [f"hu{i}" for i in range(1, 9)]
NOMES_FORMA = ["euler", "compacidade", "excentricidade", "alongamento", "solidez"]
NOMES_TAMANHO = ["area", "perimetro"]
NOMES_FEATURES = NOMES_HU + NOMES_FORMA + NOMES_TAMANHO

# Fundo
def load_background(pasta_fundo: Path, sessao: str):
    
    arquivos = sorted(Path(pasta_fundo).glob(f"fundo_{sessao}_*.png"))
    pilha = [cv2.imread(str(a), cv2.IMREAD_GRAYSCALE) for a in arquivos]
    pilha = [p for p in pilha if p is not None]
    
    if not pilha:
        return None
    
    n = len(pilha)
    soma = np.sum(np.stack(pilha).astype(np.uint32), axis=0)
    
    return ((soma + n // 2) // n).astype(np.uint8)

# Segmentação
def grayscale(img):
    if img.ndim == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img

def kernel_binomial(k):
    """Linha k-1 do triângulo de Pascal: aproximação inteira da gaussiana (igual à ESP32)."""
    c = [1]
    for _ in range(k - 1):
        c = [x + y for x, y in zip(c + [0], [0] + c)]
    return c

def gaussian_blur(img, k):
    """Gaussiano KxK separável, inteiro, borda refletida e uma divisão arredondada por 4^(K-1)."""
    
    if k <= 1:
        return img.copy()
    
    c = kernel_binomial(k)
    r = k // 2
    h, w = img.shape
    p = np.pad(img.astype(np.uint32), ((0, 0), (r, r)), mode="reflect")
    horiz = sum(c[i] * p[:, i:i + w] for i in range(k))
    p = np.pad(horiz, ((r, r), (0, 0)), mode="reflect")
    vert = sum(c[i] * p[i:i + h, :] for i in range(k))
    shift = 2 * (k - 1)
    
    return ((vert + (1 << (shift - 1))) >> shift).astype(np.uint8)


def otsu(img):
    """Limiar de Otsu com as mesmas contas e a mesma ordem da ESP32 (mesmo desempate)."""
    
    hist = np.bincount(img.ravel(), minlength=256).tolist()
    n = img.size
    soma = sum(t * hist[t] for t in range(256))
    soma_b, w_b, melhor, limiar = 0, 0, 0.0, 0
    
    for t in range(256):
        w_b += hist[t]
    
        if w_b == 0:
            continue
        w_f = n - w_b
    
        if w_f == 0:
            break
        
        soma_b += t * hist[t]
        m_b = soma_b / w_b
        m_f = (soma - soma_b) / w_f
        entre = float(w_b) * float(w_f) * (m_b - m_f) * (m_b - m_f)
    
        if entre > melhor:
            melhor, limiar = entre, t
    
    return limiar


def _passada(mask, k, erosao, eixo):
    """Mínimo (erosão) ou máximo (dilatação) numa janela 1D de k pixels; fora da imagem é ignorado."""
    
    r = k // 2
    neutro = 1 if erosao else 0
    op = np.minimum if erosao else np.maximum
    
    largura = mask.shape[eixo]
    pad = [(0, 0), (0, 0)]
    pad[eixo] = (r, r)
    p = np.pad(mask, pad, constant_values=neutro)
    
    fatia = lambda i: p[:, i:i + largura] if eixo == 1 else p[i:i + largura, :]
    
    out = fatia(0)
    
    for i in range(1, k):
        out = op(out, fatia(i))
    
    return out


def erode(mask, k):
    """Erosão binária com elemento quadrado KxK (separável), igual à erode() da ESP32."""
    
    if k <= 1:
        return mask
    return _passada(_passada(mask, k, True, 1), k, True, 0)


def dilate(mask, k):
    """Dilatação binária com elemento quadrado KxK (separável), igual à dilate() da ESP32."""
    
    if k <= 1:
        return mask
    
    return _passada(_passada(mask, k, False, 1), k, False, 0)


def segmentar(img, fundo=None):
    """Devolve (máscara 0/255, limiar de Otsu). Espelho exato da segmentar() da ESP32."""
    g = grayscale(img)
    
    if fundo is not None and C.USAR_FUNDO and fundo.shape == g.shape:
        base = np.abs(g.astype(np.int16) - fundo.astype(np.int16)).astype(np.uint8)
        objeto_claro = True
    
    else:
        base = g
        objeto_claro = config.OBJETO_CLARO

    suave = gaussian_blur(base, config.GAUSS_K)
    limiar = otsu(suave)
    mask = (suave > limiar) if objeto_claro else (suave <= limiar)
    mask = mask.astype(np.uint8)

    if config.OPEN_K > 1:    # abertura = erosão + dilatação
        mask = dilate(erode(mask, config.OPEN_K), C.OPEN_K)
    
    if config.CLOSE_K > 1:   # fechamento = dilatação + erosão
        mask = erode(dilate(mask, config.CLOSE_K), config.CLOSE_K)
    
    return mask * 255, limiar

def componentes(mask):
    """Separa as peças da máscara. Cada item traz a máscara recortada da peça."""
    
    n, labels, stats, centroides = cv2.connectedComponentsWithStats(mask, connectivity=8)
    H, W = mask.shape
    m = config.MARGEM_BORDA
    pad = config.PAD_RECORTE
    objetos = []

    for i in range(1, n):
        x, y, w, h, area = stats[i]
        
        if area < config.MIN_AREA:
            continue
        
        toca_borda = x <= m or y <= m or x + w >= W - m or y + h >= H - m
        recorte = (labels[y:y + h, x:x + w] == i).astype(np.uint8) * 255
        recorte = np.pad(recorte, pad, mode="constant")
        
        objetos.append({
            "bbox": (int(x), int(y), int(w), int(h)),
            "area_px": int(area),
            "centroide": (float(centroides[i][0]), float(centroides[i][1])),
            "toca_borda": bool(toca_borda),
            "mask": recorte,
        })
    
    return objetos


# Descritores
def descritores(mask_peca):
    """Vetor de descritores de uma peça (máscara binária recortada)."""
    m = (mask_peca > 0).astype(np.uint8)

    contornos, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if not contornos:
        return None
    hier = hier[0]
    externos = [i for i in range(len(contornos)) if hier[i][3] == -1]
    ext = max(externos, key=lambda i: cv2.contourArea(contornos[i]))
    contorno = contornos[ext]

    area = float(m.sum())
    perimetro = float(cv2.arcLength(contorno, True))

    # Número de Euler = 1 - furos (furos = contornos filhos do contorno externo)
    furos = sum(
        1 for i in range(len(contornos))
        if hier[i][3] == ext and cv2.contourArea(contornos[i]) >= config.MIN_AREA_FURO
    )
    euler = 1 - furos

    # Compacidade: para o círculo, cresce para formas alongadas ou recortadas
    compacidade = perimetro ** 2 / (4 * np.pi * area) if area > 0 else 0.0

    # Excentricidade pelos autovalores da matriz de covariância (momentos centrais)
    _, mu, _ = moments(m, ordem=3)
    cov = np.array([[mu[2, 0], mu[1, 1]], [mu[1, 1], mu[0, 2]]]) / mu[0, 0]
    l1, l2 = sorted(np.linalg.eigvalsh(cov), reverse=True)
    excentricidade = float(np.sqrt(1 - l2 / l1)) if l1 > 0 else 0.0

    # Alongamento do retângulo de área mínima (invariante à rotação)
    (_, _), (rw, rh), _ = cv2.minAreaRect(contorno)
    alongamento = max(rw, rh) / max(min(rw, rh), 1e-6)

    # Solidez: área / área do fecho convexo (cabeça do parafuso e ponta do prego reduzem)
    area_hull = cv2.contourArea(cv2.convexHull(contorno))
    solidez = cv2.contourArea(contorno) / area_hull if area_hull > 0 else 0.0

    hu = feature_vector(m, usar_log=True)

    valores = list(hu) + [euler, compacidade, excentricidade, alongamento, solidez, area, perimetro]
    
    return dict(zip(NOMES_FEATURES, map(float, valores)))


# Pipeline completo
def processar_mascara(mask, ignorar_borda=True):
    """Componentes + descritores a partir de uma máscara pronta (é o que o servidor faz na E2)."""
    
    objetos = componentes(mask)
    
    if ignorar_borda:
        objetos = [o for o in objetos if not o["toca_borda"]]
    
    for o in objetos:
        o["features"] = descritores(o["mask"])
    
    return [o for o in objetos if o["features"] is not None]

def processar_imagem(img, fundo=None, ignorar_borda=True):
    """Segmentação + componentes + descritores (é o que o servidor faz na E1 e no treino)."""
    mask, limiar = segmentar(img, fundo)
    
    return processar_mascara(mask, ignorar_borda), mask, limiar

def desenhar(img, objetos, mask=None, rotulos=None):
    """Sobreposição para conferência: contorno da máscara e caixa de cada peça."""
    vis = cv2.cvtColor(grayscale(img), cv2.COLOR_GRAY2BGR)
    
    if mask is not None:
        contornos, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(vis, contornos, -1, (0, 200, 255), 1)
    
    for i, o in enumerate(objetos):
        x, y, w, h = o["bbox"]
        cor = (0, 0, 255) if o.get("toca_borda") else (0, 220, 0)
        cv2.rectangle(vis, (x, y), (x + w, y + h), cor, 1)
        texto = rotulos[i] if rotulos else f"E={int(o['features']['euler'])}" if o.get("features") else ""
        cv2.putText(vis, texto, (x, max(y - 4, 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, cor, 1)
    
    return vis