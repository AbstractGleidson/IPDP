from pathlib import Path

ESP32_URL = "http://192.168.3.111" # ip da camera
TIMEOUT_S = 5

# A ordem define as teclas 1, 2, 3, 4, 5 no script de captura.
CLASSES = ["parafuso", "porca", "sensor_ultrassonico", "servo", "motor_dc"]

# Pastas
ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "server" / "models"
RESULTS_DIR = ROOT / "server" / "results"
ENCODING_DIR = ROOT / "Enconding"

def paths(data_dir: Path) -> dict:
    """Todos os caminhos derivados da pasta de dados (permite usar outra pasta, ex.: dados sintéticos)."""
    data_dir = Path(data_dir)
    return {
        "raw": data_dir / "raw", # imagens originais, sem compressão (PNG)
        "background": data_dir / "background", # imagens da bandeja vazia, por sessão
        "processed": data_dir / "processed", # máscaras recortadas para conferência visual
        "metadata": data_dir / "metadata.csv", # uma linha por foto
        "features": data_dir / "features.csv", # uma linha por peça segmentada
    }

# Pré-processamento: os quatro primeiros PRECISAM ser iguais aos do firmware (image_process.h)
USE_BACKGROUND = True # subtrai a imagem da bandeja vazia antes de limiarizar
BRIGHT_OBJECT = True # OBJ_CLARO: sem fundo, peça mais clara que o fundo (retroiluminação: False)
GAUSS_K = 3 # GAUSS_K: kernel do gaussiano (1 desliga, 3, 5, 7 ou 9)
OPEN_K = 3 # OPEN_K: kernel da abertura (0 ou 1 desliga)
CLOSE_K = 3 # CLOSE_K: kernel do fechamento (cuidado: kernels grandes fecham os furos)
MIN_AREA = 80 # área mínima de uma peça, em pixels
MIN_HOLE_AREA = 8 # furos menores que isso são ruído (os furos do servo e do sensor são pequenos)
BORDER_MARGIN = 3 # peças a menos disso da borda da imagem são descartadas
CROP_PAD = 4 # borda extra ao recortar cada peça

# Modelo
MODEL_PATH = MODELS_DIR / "classifier.joblib"

# Experimentos de compressão
E1_BITS = [1, 2, 3, 4, 5, 6, 7, 8] # bits por pixel testados na E1 (8 = sem perdas)
E1_JPEG_Q = [10, 30, 50, 70, 90] # qualidades JPEG testadas na E1 (comparação)
