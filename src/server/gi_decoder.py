"""
Descompressão do pacote "GI" (RLE + Huffman canônico) no servidor, em Python.

Mesmo algoritmo do Enconding/decod.py, mas recebendo os bytes direto da resposta
HTTP (sem arquivo). Formato do pacote: ver Enconding/rle_huff.h.

Também calcula o tamanho exato que o gi_encode() da ESP32 produziria para uma
imagem (compressed_size).
"""

import heapq
import struct
import numpy as np

MAGIC = b"GI"
HEADER = struct.Struct("<2sBBHHI")  # magic, versão, bits, largura, altura, nº de corridas
MAX_RUN = 255  # o RLE da ESP32 limita cada corrida a 255 pixels

def read_header(data: bytes):
    """(bits, largura, altura, nº de corridas) do pacote."""
    
    if len(data) < HEADER.size:
        raise ValueError("pacote GI curto demais")
    
    magic, version, bits, w, h, num_runs = HEADER.unpack_from(data, 0)
    
    if magic != MAGIC or version != 1 or not 1 <= bits <= 8:
        raise ValueError("não é um pacote GI válido (versão 1)")
    
    return bits, w, h, num_runs

def _read_table(data, pos):
    """Lê k e os k pares (símbolo, tamanho do código)."""
    
    (k,) = struct.unpack_from("<H", data, pos)
    pos += 2
    pairs = [(data[pos + 2 * i], data[pos + 2 * i + 1]) for i in range(k)]
    
    return pairs, pos + 2 * k

def _canonical_codes(pairs):
    """{(tamanho, código): símbolo}, códigos canônicos ordenados por (tamanho, símbolo)."""
    
    table, code, prev = {}, 0, None
    
    for symbol, length in sorted(pairs, key=lambda p: (p[1], p[0])):
        if prev is not None:
            code = (code + 1) << (length - prev)
        table[(length, code)] = symbol
        prev = length
        
    return table

def decode(data: bytes):
    """Devolve (bits, índices quantizados h x w em uint8). Com bits = 8, os índices são os pixels."""
    
    bits, w, h, num_runs = read_header(data)
    pos = HEADER.size

    pairs_len, pos = _read_table(data, pos)
    pairs_val, pos = _read_table(data, pos)
    table_len, table_val = _canonical_codes(pairs_len), _canonical_codes(pairs_val)
    max_len = max((l for _, l in pairs_len), default=0)
    max_val = max((l for _, l in pairs_val), default=0)

    bitstream = np.unpackbits(np.frombuffer(data, np.uint8, offset=pos)).tolist()
    n_bits = len(bitstream)
    p = 0

    def read_symbol(table, max_size):
        nonlocal p
        code = 0
        
        for size in range(1, max_size + 1):
            if p >= n_bits:
                raise ValueError("GI: bitstream terminou antes de todas as corridas")
            
            code = (code << 1) | bitstream[p]
            p += 1
            symbol = table.get((size, code))
            
            if symbol is not None:
                return symbol
            
        raise ValueError("GI: código de Huffman inválido")

    lengths = np.empty(num_runs, np.int64)
    values = np.empty(num_runs, np.uint8)
    
    for r in range(num_runs):
        lengths[r] = read_symbol(table_len, max_len)
        values[r] = read_symbol(table_val, max_val)

    if int(lengths.sum()) != w * h:
        raise ValueError("GI: soma das corridas diferente de largura x altura")
    
    return bits, np.repeat(values, lengths).reshape(h, w)

def reconstruct(indices: np.ndarray, bits: int) -> np.ndarray:
    """Índice quantizado -> tom de cinza, no centro do intervalo de cada nível (igual ao decod.py)."""
    
    shift = 8 - bits
    half = (1 << shift) >> 1  # 0 quando bits = 8 (sem perdas)
    
    return ((indices.astype(np.uint16) << shift) + half).astype(np.uint8)


def decode_image(data: bytes) -> np.ndarray:
    """Pacote GI de uma imagem em cinza (E1) -> imagem reconstruída."""
    
    bits, indices = decode(data)
    
    return reconstruct(indices, bits)


def decode_mask(data: bytes) -> np.ndarray:
    """Pacote GI de uma máscara 0/1 (E2, codificada com bits = 8) -> máscara 0/255."""
    bits, indices = decode(data)
    
    if bits != 8:
        raise ValueError("a máscara da E2 deve ser codificada com bits = 8 (valores 0/1)")
    
    return (indices > 0).astype(np.uint8) * 255


def quantize(img: np.ndarray, bits: int) -> np.ndarray:
    """O que a E1 entrega ao servidor depois de comprimir com 'bits' e descomprimir."""
    
    return reconstruct(img.astype(np.uint8) >> (8 - bits), bits)


# Tamanho exato do pacote (sem montar o bitstream)
def _runs(img: np.ndarray, bits: int):
    """Corridas (comprimento, valor) do RLE da ESP32, com corridas limitadas a 255."""
    
    flat = (img.astype(np.uint8) >> (8 - bits)).ravel()
    edges = np.flatnonzero(np.diff(flat)) + 1
    starts = np.concatenate(([0], edges))
    lengths = np.diff(np.concatenate((starts, [flat.size])))
    values = flat[starts]
    
    # corrida maior que 255 vira várias de 255 + resto, com o mesmo valor
    reps = (lengths + MAX_RUN - 1) // MAX_RUN
    values = np.repeat(values, reps)
    split = np.full(int(reps.sum()), MAX_RUN, np.int64)
    last = np.cumsum(reps) - 1
    split[last] = lengths - (reps - 1) * MAX_RUN
    
    return split, values


def _huffman_bits(freqs):
    """(nº de símbolos, total de bits) de um código de Huffman ótimo para as frequências."""
    
    freqs = [f for f in freqs if f > 0]
    
    if len(freqs) == 1:  # um símbolo só: o codificador usa código de 1 bit
        return 1, freqs[0]
    
    heap = list(freqs)
    heapq.heapify(heap)
    total = 0
    
    while len(heap) > 1:  # o custo total é a soma das fusões, qualquer que seja o desempate
        a, b = heapq.heappop(heap), heapq.heappop(heap)
        total += a + b
        heapq.heappush(heap, a + b)
        
    return len(freqs), total

def compressed_size(img: np.ndarray, bits: int) -> int:
    """Bytes que o gi_encode() da ESP32 geraria para 'img' com 'bits' bits por pixel."""
    
    lengths, values = _runs(img, bits)
    k_len, bits_len = _huffman_bits(np.bincount(lengths, minlength=256).tolist())
    k_val, bits_val = _huffman_bits(np.bincount(values, minlength=256).tolist())
    
    return HEADER.size + (2 + 2 * k_len) + (2 + 2 * k_val) + (bits_len + bits_val + 7) // 8
