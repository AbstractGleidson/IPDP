import numpy as np
import cv2

# calcula os momentos da imagem
def moments(img, ordem=3):
    """
    Calcula todos os momentos brutos (m), centrais (mu) e normalizados (nu)
    até a ordem pedida, de uma só vez.

    m_pq = (Vx^T · I^T · Vy)[p, q], onde Vx e Vy são matrizes de
    Vandermonde (colunas = x^0, x^1, ..., x^ordem). 
    """
    
    I = np.asarray(img) # transformação a imagem em um numpy array
    
    # aplica conversão para grayscale  
    if I.ndim == 3:
        I = cv2.cvtColor(I, cv2.COLOR_BGR2GRAY)
        
    I = I.astype(np.float64) 

    h, w = I.shape # recupera as dimensões da imagem
    
    k = np.arange(ordem + 1)
    x = np.arange(w, dtype=np.float64)
    y = np.arange(h, dtype=np.float64)

    # Momentos brutos: matriz (ordem+1) x (ordem+1), m[p, q]
    Vx = x[:, None] ** k
    Vy = y[:, None] ** k
    m = Vx.T @ I.T @ Vy

    m00 = m[0, 0]
    if m00 == 0:
        raise ValueError("Imagem vazia (m00 = 0): não há objeto para medir.")

    # calcula centroide
    cx, cy = m[1, 0] / m00, m[0, 1] / m00

    # Momentos centrais: mesmo truque com coordenadas deslocadas
    Ux = (x - cx)[:, None] ** k
    Uy = (y - cy)[:, None] ** k
    mu = Ux.T @ I.T @ Uy

    # Momentos invariantes à escala: nu_pq = mu_pq / mu00^((p+q)/2 + 1)
    p, q = np.meshgrid(k, k, indexing="ij")
    gamma = (p + q) / 2.0 + 1.0
    nu = mu / (mu[0, 0] ** gamma)

    return m, mu, nu

# momentos invariantes de HU
def hu_invariants_moments(nu):
    """I1..I7 de Hu + I8 de Flusser a partir da matriz nu[p, q]."""
    
    n20, n02, n11 = nu[2, 0], nu[0, 2], nu[1, 1]
    n30, n03, n21, n12 = nu[3, 0], nu[0, 3], nu[2, 1], nu[1, 2]

    a = n30 + n12
    b = n21 + n03
    c = n30 - 3 * n12
    d = 3 * n21 - n03

    I1 = n20 + n02
    I2 = (n20 - n02) ** 2 + 4 * n11 ** 2
    I3 = c ** 2 + d ** 2
    I4 = a ** 2 + b ** 2
    I5 = c * a * (a ** 2 - 3 * b ** 2) + d * b * (3 * a ** 2 - b ** 2)
    I6 = (n20 - n02) * (a ** 2 - b ** 2) + 4 * n11 * a * b
    I7 = d * a * (a ** 2 - 3 * b ** 2) - c * b * (3 * a ** 2 - b ** 2)
    I8 = n11 * (a ** 2 - b ** 2) - (n20 - n02) * a * b

    return np.array([I1, I2, I3, I4, I5, I6, I7, I8])

# cria um dicionario com o momentos 
def dict_moments(img):
    """Mesmo formato de saída da sua função rot_invariant_moments."""
    m, mu, nu = moments(img, ordem=3)
    
    out = {}
    
    # cria as labels para os momentos
    for p in range(4):
        for q in range(4 - p):
            out[f"m{p}{q}"] = m[p, q]
            
            if p + q >= 2:
                out[f"mu{p}{q}"] = mu[p, q]
                out[f"nu{p}{q}"] = nu[p, q]
    
    for i, v in enumerate(hu_invariants_moments(nu), start=1):
        out[f"I{i}"] = v
    
    return out

# vetor de caracteristicas da imagem com base nos momentos
def feature_vector(img, usar_log=True):
    """
    Vetor de 8 características (I1..I8).
    Os invariantes variam por várias ordens de grandeza (1e-1 até 1e-20),
    normaliza com transformação log com sinal
    """
    _, _, nu = moments(img, ordem=3)
    hu = hu_invariants_moments(nu)
    
    if usar_log:
        hu = -np.sign(hu) * np.log10(np.abs(hu) + 1e-30) # transformação log para linearizar
    
    return hu