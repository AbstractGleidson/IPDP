"""
Cliente da ESP32 (firmware edger/inspect_objectos).

Faz os pedidos HTTP mantendo a conexão TCP aberta, descomprime as respostas
e devolve, para cada quadro, a imagem (E1) ou a máscara (E2) com os tempos:

    t_request_ms     ida e volta do pedido (inclui captura, processamento na placa e rede)
    t_capture_ms     captura + recorte da ROI na placa
    t_edge_ms        processamento na placa (compressão; na E2, também a segmentação)
    t_decompress_ms  descompressão no servidor
"""
import time
from dataclasses import dataclass, field
import cv2
import numpy as np
import requests
import src.server.config as config
import src.server.gi_decoder as gi_decoder

# classe para representar um frame da esp32
@dataclass
class Frame:
    strategy: str # tipo de estragegoa usado na aquisição
    img: np.ndarray = None # imagem em cinza (E1 e /raw)
    mask: np.ndarray = None # máscara 0/255 (E2)
    bytes_received: int = 0 # quantidade de bytes recebidos 
    raw_bytes: int = 0  # tamanho sem compressão (E1: 1 byte/pixel; E2: 1 bit/pixel)
    t_request_ms: float = 0.0 
    t_capture_ms: float = 0.0
    t_edge_ms: float = 0.0
    t_decompress_ms: float = 0.0
    threshold: int = None 
    bits: int = None
    headers: dict = field(default_factory=dict)

    # calcula a taxa de compressão 
    @property
    def compression_ratio(self):
        return self.raw_bytes / self.bytes_received if self.bytes_received else 0.0

# interface de comunicação com esp32
class ESP32:
    def __init__(self, url=config.ESP32_URL, timeout=config.TIMEOUT_S):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()  # conexão persistente: tira o custo de abrir TCP a cada quadro

    def _get(self, route, **params):
        t0 = time.perf_counter()
        r = self.session.get(self.url + route, params=params, timeout=self.timeout)
        r.raise_for_status()
        
        return r, (time.perf_counter() - t0) * 1000

    # constroi frame 
    @staticmethod
    def _frame(strategy, r, t_request):
        h = r.headers
        
        return Frame(
            strategy=strategy,
            bytes_received=len(r.content),
            raw_bytes=int(h.get("X-Raw-Bytes", len(r.content))),
            t_request_ms=t_request,
            t_capture_ms=int(h.get("X-Capture-Time-us", 0)) / 1000,
            t_edge_ms=int(h.get("X-Proc-Time-us", 0)) / 1000,
            threshold=int(h["X-Threshold"]) if "X-Threshold" in h else None,
            headers=dict(h),
        )

    # solicita com compressão GI
    @staticmethod
    def _require_gi(r, header, route):
        """Avisa com clareza quando a placa está com um firmware sem a compressão GI."""
        
        if r.headers.get(header) != "gi" or not r.content.startswith(b"GI"):
            raise RuntimeError(
                f"A rota {route} não devolveu um pacote GI ({header}={r.headers.get(header)!r}, "
                f"início {r.content[:4]!r}). A ESP32 provavelmente está com o firmware antigo: "
                "grave o edger/inspect_objectos com rle_huff.h/.cpp na pasta.")

    # retorna a configuração da camera
    def status(self):
        return self._get("/status")[0].json()

    # muda configuração da camera
    def set(self, var, val):
        return self._get("/set", var=var, val=val)[0].text

    # solicita o fundo da imagem
    def background(self):
        """Fundo guardado na placa (ou None)."""
        try:
            r, _ = self._get("/fundo")
            
        except requests.HTTPError:
            return None
        
        w, h = int(r.headers["X-Width"]), int(r.headers["X-Height"])
        
        return np.frombuffer(r.content, np.uint8).reshape(h, w)

    def capture_background(self):
        return self._get("/fundo", acao="capturar")[0].text

    def clear_background(self):
        return self._get("/fundo", acao="limpar")[0].text

    #  solicita frames 
    def raw(self):
        r, t = self._get("/raw")
        f = self._frame("raw", r, t)
        w, h = int(r.headers["X-Width"]), int(r.headers["X-Height"])
        f.img = np.frombuffer(r.content, np.uint8).reshape(h, w)
        f.raw_bytes = w * h
        
        return f

    def e1(self, bits=8):
        """E1: imagem inteira em cinza, comprimida em GI com 'bits' bits por pixel."""
        
        r, t = self._get("/e1", bits=bits)
        self._require_gi(r, "X-Codec", "/e1")
        f = self._frame("E1", r, t)
        t0 = time.perf_counter()
        f.img = gi_decoder.decode_image(r.content)
        f.t_decompress_ms = (time.perf_counter() - t0) * 1000
        f.bits = bits
        
        return f

    def e1_jpeg(self, quality=50):
        """E1 com JPEG (comparação)."""
        
        r, t = self._get("/e1", codec="jpeg", q=quality)
        f = self._frame("E1-JPEG", r, t)
        t0 = time.perf_counter()
        f.img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_GRAYSCALE)
        f.t_decompress_ms = (time.perf_counter() - t0) * 1000
        f.bits = quality
        
        return f

    def e2(self, fmt="gi"):
        """E2: máscara segmentada na placa. fmt = 'gi' (comprimida), 'bits' ou 'bytes' (sem compressão)."""
        
        r, t = self._get("/e2", fmt=fmt)
        
        if fmt == "gi":
            self._require_gi(r, "X-Format", "/e2")
            
        f = self._frame("E2" if fmt == "gi" else f"E2-{fmt}", r, t)
        w, h = int(r.headers["X-Width"]), int(r.headers["X-Height"])
        t0 = time.perf_counter()
        
        if fmt == "gi":
            f.mask = gi_decoder.decode_mask(r.content)
            
        elif fmt == "bits":
            f.mask = np.unpackbits(np.frombuffer(r.content, np.uint8))[:w * h].reshape(h, w) * 255
            
        else:
            f.mask = np.frombuffer(r.content, np.uint8).reshape(h, w) * 255
            
        f.t_decompress_ms = (time.perf_counter() - t0) * 1000
        
        return f

    # verifica se o quadro da camera é o mesmo da esp32
    def parity(self):
        """Imagem em cinza e máscara da placa, do mesmo quadro."""
        
        r, _ = self._get("/paridade")
        w, h = int(r.headers["X-Width"]), int(r.headers["X-Height"])
        n = w * h
        d = np.frombuffer(r.content, np.uint8)
        
        return d[:n].reshape(h, w), d[n:2 * n].reshape(h, w), dict(r.headers)
