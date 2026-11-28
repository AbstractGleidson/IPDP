// rle_huff.h — Compressão RLE + Huffman canônico de imagens em tons de cinza.
//
// Formato do pacote "GI" (todos os campos em little-endian):
//
//   off  tam   campo
//   0    2     magic 'G' 'I'
//   2    1     versão (GI_VERSION)
//   3    1     bits de quantização (1..8; 8 = sem perdas)
//   4    2     largura  (uint16)
//   6    2     altura   (uint16)
//   8    4     nº de corridas (uint32)
//   12   2     kc = nº de símbolos da tabela de comprimentos (uint16)
//   14   2*kc  pares (comprimento da corrida, tamanho do código), em ordem crescente de símbolo
//   ..   2     kv = nº de símbolos da tabela de valores (uint16)
//   ..   2*kv  pares (valor quantizado, tamanho do código), em ordem crescente de símbolo
//   ..   ...   bitstream (MSB primeiro): para cada corrida, código(comprimento) e depois código(valor)
//
// Os códigos são canônicos: ordenando os símbolos por (tamanho, símbolo), o
// primeiro recebe 0 e cada seguinte recebe o anterior + 1, deslocado à
// esquerda quando o tamanho aumenta. Por isso a tabela só leva os tamanhos.

#pragma once

#include <stddef.h>
#include <stdint.h>

#define GI_VERSION 1
#define GI_MAX_RUN 255      // maior comprimento de corrida representável
#define GI_MAX_CODE_LEN 32  // maior tamanho de código suportado

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint32_t num_runs;    // nº de corridas geradas
    uint16_t kc;          // símbolos distintos na tabela de comprimentos
    uint16_t kv;          // símbolos distintos na tabela de valores
    size_t header_bytes;  // cabeçalho + tabelas
    size_t stream_bytes;  // bitstream
    size_t total_bytes;   // pacote inteiro
} gi_stats_t;

// Maior tamanho possível do pacote para uma imagem w x h. Use para alocar
// o buffer de saída (na ESP: ps_malloc(gi_max_size(w, h))).
size_t gi_max_size(uint16_t w, uint16_t h);

// Comprime 'img' (w*h bytes, 1 byte por pixel, linha após linha) mantendo os
// 'bits' bits mais significativos de cada pixel.
// Retorna o nº de bytes escritos em 'out', ou 0 em caso de erro
// (parâmetros inválidos ou 'out_cap' insuficiente).
// 'stats' é opcional (pode ser NULL).
size_t gi_encode(const uint8_t *img, uint16_t w, uint16_t h, uint8_t bits,
                 uint8_t *out, size_t out_cap, gi_stats_t *stats);

#ifdef __cplusplus
}
#endif
