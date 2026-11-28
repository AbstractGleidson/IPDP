from pathlib import Path

import cv2
import numpy as np
import config as config
from moments import moments, feature_vector

# constantes
HU_NAMES = [f"hu{i}" for i in range(1, 9)]
SHAPE_NAMES = ["euler", "compactness", "eccentricity", "elongation", "solidity"]
SIZE_NAMES = ["area", "perimeter"]
FEATURE_NAMES = HU_NAMES + SHAPE_NAMES + SIZE_NAMES

# Fundo
def load_background(background_dir: Path, session: str):
    """Média arredondada das fotos da bandeja vazia de uma sessão (mesma conta da ESP32)."""

    files = sorted(Path(background_dir).glob(f"background_{session}_*.png"))
    stack = [cv2.imread(str(f), cv2.IMREAD_GRAYSCALE) for f in files]
    stack = [s for s in stack if s is not None]

    if not stack:
        return None

    n = len(stack)
    total = np.sum(np.stack(stack).astype(np.uint32), axis=0)

    return ((total + n // 2) // n).astype(np.uint8)

# transforma para escala de cinza
def grayscale(img):
    
    if img.ndim == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    return img

# gera amostragem para o kernel da gaussiana 
def binomial_kernel(k):
    """Linha k-1 do triângulo de Pascal: aproximação inteira da gaussiana (igual à ESP32)."""
    
    c = [1]
    
    for _ in range(k - 1):
        c = [x + y for x, y in zip(c + [0], [0] + c)]
        
    return c

# filtro gaussiano
def gaussian_blur(img, k):
    """Gaussiano KxK separável, inteiro, borda refletida e uma divisão arredondada por 4^(K-1)."""

    if k <= 1:
        return img.copy()

    c = binomial_kernel(k)
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
    total = sum(t * hist[t] for t in range(256))
    sum_b, w_b, best, thres = 0, 0, 0.0, 0

    for t in range(256):
        w_b += hist[t]

        if w_b == 0:
            continue
        w_f = n - w_b

        if w_f == 0:
            break

        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (total - sum_b) / w_f
        between = float(w_b) * float(w_f) * (m_b - m_f) * (m_b - m_f)

        if between > best:
            best, thres = between, t

    return thres

# suporte para operação morfologica
def _morph_pass(mask, k, is_erode, axis):
    """Mínimo (erosão) ou máximo (dilatação) numa janela 1D de k pixels; fora da imagem é ignorado."""

    r = k // 2
    neutral = 1 if is_erode else 0
    op = np.minimum if is_erode else np.maximum

    length = mask.shape[axis]
    pad = [(0, 0), (0, 0)]
    pad[axis] = (r, r)
    p = np.pad(mask, pad, constant_values=neutral)

    window = lambda i: p[:, i:i + length] if axis == 1 else p[i:i + length, :]

    out = window(0)

    for i in range(1, k):
        out = op(out, window(i))

    return out

# erosão 
def erode(mask, k):
    """Erosão binária com elemento quadrado KxK (separável), igual à erode() da ESP32."""

    if k <= 1:
        return mask
    return _morph_pass(_morph_pass(mask, k, True, 1), k, True, 0)

# dilatação
def dilate(mask, k):
    """Dilatação binária com elemento quadrado KxK (separável), igual à dilate() da ESP32."""

    if k <= 1:
        return mask

    return _morph_pass(_morph_pass(mask, k, False, 1), k, False, 0)


# segmentação
def segment(img, background=None):
    """Devolve (máscara 0/255, limiar de Otsu). Espelho exato da threshold_otsu() da ESP32."""
    
    g = grayscale(img)

    if background is not None and config.USE_BACKGROUND and background.shape == g.shape:
        base = np.abs(g.astype(np.int16) - background.astype(np.int16)).astype(np.uint8)
        bright = True

    else:
        base = g
        bright = config.BRIGHT_OBJECT

    smooth = gaussian_blur(base, config.GAUSS_K)
    thres = otsu(smooth)
    mask = (smooth > thres) if bright else (smooth <= thres)
    mask = mask.astype(np.uint8)

    if config.OPEN_K > 1:    # abertura = erosão + dilatação
        mask = dilate(erode(mask, config.OPEN_K), config.OPEN_K)

    if config.CLOSE_K > 1:   # fechamento = dilatação + erosão
        mask = erode(dilate(mask, config.CLOSE_K), config.CLOSE_K)

    return mask * 255, thres

def components(mask):
    """Separa as peças da máscara. Cada item traz a máscara recortada da peça."""

    n, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    H, W = mask.shape
    m = config.BORDER_MARGIN
    pad = config.CROP_PAD
    objects = []

    for i in range(1, n):
        x, y, w, h, area = stats[i]

        if area < config.MIN_AREA:
            continue

        touches_border = x <= m or y <= m or x + w >= W - m or y + h >= H - m
        crop = (labels[y:y + h, x:x + w] == i).astype(np.uint8) * 255
        crop = np.pad(crop, pad, mode="constant")

        objects.append({
            "bbox": (int(x), int(y), int(w), int(h)),
            "area_px": int(area),
            "centroid": (float(centroids[i][0]), float(centroids[i][1])),
            "touches_border": bool(touches_border),
            "mask": crop,
        })

    return objects

# Descritores
def descriptors(piece_mask):
    """Vetor de descritores de uma peça (máscara binária recortada)."""
    
    m = (piece_mask > 0).astype(np.uint8)

    contours, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    hier = hier[0]
    outer = [i for i in range(len(contours)) if hier[i][3] == -1]
    ext = max(outer, key=lambda i: cv2.contourArea(contours[i]))
    contour = contours[ext]

    area = float(m.sum())
    perimeter = float(cv2.arcLength(contour, True))

    # Número de Euler = 1 - furos (furos = contornos filhos do contorno externo)
    holes = sum(
        1 for i in range(len(contours))
        if hier[i][3] == ext and cv2.contourArea(contours[i]) >= config.MIN_HOLE_AREA
    )
    euler = 1 - holes

    # Compacidade: 1 para o círculo, cresce para formas alongadas ou recortadas
    compactness = perimeter ** 2 / (4 * np.pi * area) if area > 0 else 0.0

    # Excentricidade pelos autovalores da matriz de covariância (momentos centrais)
    _, mu, _ = moments(m, ordem=3)
    cov = np.array([[mu[2, 0], mu[1, 1]], [mu[1, 1], mu[0, 2]]]) / mu[0, 0]
    l1, l2 = sorted(np.linalg.eigvalsh(cov), reverse=True)
    eccentricity = float(np.sqrt(1 - l2 / l1)) if l1 > 0 else 0.0

    # Alongamento do retângulo de área mínima (invariante à rotação)
    (_, _), (rw, rh), _ = cv2.minAreaRect(contour)
    elongation = max(rw, rh) / max(min(rw, rh), 1e-6)

    # Solidez: área / área do fecho convexo
    hull_area = cv2.contourArea(cv2.convexHull(contour))
    solidity = cv2.contourArea(contour) / hull_area if hull_area > 0 else 0.0

    hu = feature_vector(m, usar_log=True)

    values = list(hu) + [euler, compactness, eccentricity, elongation, solidity, area, perimeter]

    return dict(zip(FEATURE_NAMES, map(float, values)))

# Pipeline completo
def process_mask(mask, ignore_border=True):
    """Componentes + descritores a partir de uma máscara pronta (é o que o servidor faz na E2)."""

    objects = components(mask)

    if ignore_border:
        objects = [o for o in objects if not o["touches_border"]]

    for o in objects:
        o["features"] = descriptors(o["mask"])

    return [o for o in objects if o["features"] is not None]

def process_image(img, background=None, ignore_border=True):
    """Segmentação + componentes + descritores (é o que o servidor faz na E1 e no treino)."""
    
    mask, thres = segment(img, background)

    return process_mask(mask, ignore_border), mask, thres

def draw(img, objects, mask=None, labels=None):
    """Sobreposição para conferência: contorno da máscara e caixa de cada peça."""
    
    vis = cv2.cvtColor(grayscale(img), cv2.COLOR_GRAY2BGR)

    if mask is not None:
        contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(vis, contours, -1, (0, 200, 255), 1)

    for i, o in enumerate(objects):
        x, y, w, h = o["bbox"]
        color = (0, 0, 255) if o.get("touches_border") else (0, 220, 0)
        cv2.rectangle(vis, (x, y), (x + w, y + h), color, 1)
        text = labels[i] if labels else f"E={int(o['features']['euler'])}" if o.get("features") else ""
        cv2.putText(vis, text, (x, max(y - 4, 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

    return vis
