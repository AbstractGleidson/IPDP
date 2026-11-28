"""Decodificador do pacote "GI" (RLE + Huffman canônico).

Reconstrói a imagem em tons de cinza e salva em PNG.

Uso:
    python decod.py arquivo.gi                 # salva arquivo_decoded.png
    python decod.py arquivo.gi -o saida.png

Formato do pacote: ver rle_huff.h.
"""

import argparse
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

MAGIC = b"GI"
VERSOES_SUPORTADAS = {1}
CABECALHO = struct.Struct("<2sBBHHI")  # magic, versão, bits, largura, altura, nº de corridas (12 bytes)

def ler_tabela(dados: bytes, pos: int):
    """Lê k (uint16) e os k pares (símbolo, tamanho do código). Devolve (pares, nova posição)."""
    (k,) = struct.unpack_from("<H", dados, pos)
    pos += 2
    pares = [(dados[pos + 2 * i], dados[pos + 2 * i + 1]) for i in range(k)]
    return pares, pos + 2 * k


def codigos_canonicos(pares):
    """Refaz os códigos canônicos a partir dos tamanhos.

    Ordena por (tamanho, símbolo); o primeiro recebe 0 e
    cada seguinte recebe o anterior + 1, deslocado à esquerda quando o tamanho aumenta.

    Devolve um dicionário {(tamanho, código): símbolo}.
    """
    tabela = {}
    codigo = 0
    tam_anterior = None
    for simbolo, tam in sorted(pares, key=lambda p: (p[1], p[0])):
        if tam_anterior is not None:
            codigo = (codigo + 1) << (tam - tam_anterior)
        tabela[(tam, codigo)] = simbolo
        tam_anterior = tam
    return tabela


def decodificar(caminho: Path):
    """Lê o pacote e devolve (bits de quantização, imagem com os índices quantizados)."""
    dados = caminho.read_bytes()
    if len(dados) < CABECALHO.size:
        raise ValueError("arquivo curto demais para ser um pacote GI")

    magic, versao, bits, largura, altura, num_corridas = CABECALHO.unpack_from(dados, 0)
    if magic != MAGIC:
        raise ValueError(f"magic inválido {magic!r}: não é um pacote GI")
    if versao not in VERSOES_SUPORTADAS:
        raise ValueError(f"versão {versao} não suportada")
    if not 1 <= bits <= 8:
        raise ValueError(f"bits de quantização inválido: {bits}")

    pos = CABECALHO.size
    pares_c, pos = ler_tabela(dados, pos)
    pares_v, pos = ler_tabela(dados, pos)
    tab_c = codigos_canonicos(pares_c)
    tab_v = codigos_canonicos(pares_v)
    max_c = max((t for _, t in pares_c), default=0)
    max_v = max((t for _, t in pares_v), default=0)

    bitstream = np.unpackbits(np.frombuffer(dados, dtype=np.uint8, offset=pos)).tolist()
    total_bits = len(bitstream)

    comprimentos = np.empty(num_corridas, dtype=np.int64)
    valores = np.empty(num_corridas, dtype=np.uint8)
    p = 0  # posição no bitstream

    def ler_simbolo(tabela, max_tam):
        nonlocal p
        codigo = 0
        for tam in range(1, max_tam + 1):
            if p >= total_bits:
                raise ValueError("bitstream terminou antes de todas as corridas")
            codigo = (codigo << 1) | bitstream[p]
            p += 1
            simbolo = tabela.get((tam, codigo))
            if simbolo is not None:
                return simbolo
        raise ValueError(f"código inválido no bit {p}")

    for r in range(num_corridas):
        comprimentos[r] = ler_simbolo(tab_c, max_c)
        valores[r] = ler_simbolo(tab_v, max_v)

    if int(comprimentos.sum()) != largura * altura:
        raise ValueError(
            f"soma das corridas ({int(comprimentos.sum())}) != largura x altura ({largura * altura})"
        )

    indices = np.repeat(valores, comprimentos).reshape(altura, largura)
    return bits, indices


def reconstruir(indices: np.ndarray, bits: int) -> np.ndarray:
    """Índice quantizado -> tom de cinza, usando o centro do intervalo de cada nível."""
    shift = 8 - bits
    meio = (1 << shift) >> 1  # 0 quando bits = 8 (sem perdas)
    return ((indices.astype(np.uint16) << shift) + meio).astype(np.uint8)


def main() -> int:
    ap = argparse.ArgumentParser(description="Decodifica um pacote GI (RLE + Huffman canônico) e salva em PNG.")
    ap.add_argument("arquivo", type=Path, help="pacote .gi")
    ap.add_argument("-o", "--saida", type=Path, help="PNG de saída (padrão: <arquivo>_decoded.png)")
    args = ap.parse_args()

    try:
        bits, indices = decodificar(args.arquivo)
    except ValueError as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1

    saida = args.saida or args.arquivo.with_name(args.arquivo.stem + "_decoded.png")
    Image.fromarray(reconstruir(indices, bits), mode="L").save(saida)
    print(f"salvo em {saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
