// Implementação do pacote "GI" (RLE + Huffman canônico).

#include "rle_huff.h"
#include <string.h>

// Iterador de runs 
//
// Percorre a imagem devolvendo uma corrida por vez: 'len' pixels 
// seguidos com o mesmo valor quantizado 'val'. Corridas maiores
// que GI_MAX_RUN são divididas em várias corridas com o mesmo valor.

typedef struct {
    const uint8_t *img;
    size_t n;       // total de pixels
    size_t i;       // posição atual
    uint8_t shift;  // 8 - bits de quantização
} run_iter_t;

static int next_run(run_iter_t *it, uint8_t *len, uint8_t *val) {
    if (it->i >= it->n) return 0;

    const uint8_t v = it->img[it->i] >> it->shift;
    size_t j = it->i + 1;
    while (j < it->n && (j - it->i) < GI_MAX_RUN && (it->img[j] >> it->shift) == v) j++;

    *len = (uint8_t)(j - it->i);
    *val = v;
    it->i = j;
    return 1;
}

// Huffman
static uint32_t h_freq[511];
static int16_t h_parent[511];
static uint8_t h_alive[511];
static int16_t h_leaf[256];  // símbolo -> índice da folha (-1 se não usado)

// Retorna 1 se deu certo, 0 se algum código passaria de GI_MAX_CODE_LEN bits.
static int huff_lengths(const uint32_t freq[256], uint8_t len[256]) {
    int n = 0;
    for (int s = 0; s < 256; s++) {
        len[s] = 0;
        h_leaf[s] = -1;
        if (freq[s]) {
            h_freq[n] = freq[s];
            h_parent[n] = -1;
            h_alive[n] = 1;
            h_leaf[s] = (int16_t)n++;
        }
    }

    if (n == 0) return 1;
    if (n == 1) {
        // Caso especial: um único símbolo daria código vazio (profundidade 0).
        for (int s = 0; s < 256; s++)
            if (freq[s]) len[s] = 1;
        return 1;
    }

    int total = n;
    for (int m = 0; m < n - 1; m++) {
        int a = -1, b = -1;  // a = menor, b = segundo menor
        for (int i = 0; i < total; i++) {
            if (!h_alive[i]) continue;
            if (a < 0 || h_freq[i] < h_freq[a]) {
                b = a;
                a = i;
            } else if (b < 0 || h_freq[i] < h_freq[b]) {
                b = i;
            }
        }
        h_alive[a] = h_alive[b] = 0;
        h_freq[total] = h_freq[a] + h_freq[b];
        h_parent[total] = -1;
        h_alive[total] = 1;
        h_parent[a] = h_parent[b] = (int16_t)total;
        total++;
    }

    for (int s = 0; s < 256; s++) {
        if (h_leaf[s] < 0) continue;
        int d = 0;
        for (int i = h_leaf[s]; h_parent[i] >= 0; i = h_parent[i]) d++;
        if (d > GI_MAX_CODE_LEN) return 0;
        len[s] = (uint8_t)d;
    }
    return 1;
}

// Huffman canônico: códigos a partir dos comprimentos
//
// Percorrendo os símbolos por (tamanho, símbolo), o primeiro 
// recebe 0 e cada um seguinte recebe o anterior + 1, 
// deslocado à esquerda quando o tamanho aumenta. 
static void canonical_codes(const uint8_t len[256], uint32_t code[256]) {
    uint16_t count[GI_MAX_CODE_LEN + 1];
    uint32_t next[GI_MAX_CODE_LEN + 1];
    memset(count, 0, sizeof(count));

    for (int s = 0; s < 256; s++)
        if (len[s]) count[len[s]]++;

    uint32_t c = 0;
    next[0] = 0;
    for (int b = 1; b <= GI_MAX_CODE_LEN; b++) {
        c = (c + count[b - 1]) << 1;
        next[b] = c;
    }

    for (int s = 0; s < 256; s++) {
        code[s] = 0;
        if (len[s]) code[s] = next[len[s]]++;
    }
}

// Escrita de bytes e bits no buffer de saída
typedef struct {
    uint8_t *buf;
    size_t cap;
    size_t pos;
    uint8_t cur;  // byte sendo montado
    uint8_t nb;   // quantos bits já há em 'cur'
} writer_t;

static void w_u8(writer_t *w, uint8_t b) {
    if (w->pos < w->cap) w->buf[w->pos] = b;
    w->pos++;
}

static void w_u16(writer_t *w, uint16_t v) {
    w_u8(w, (uint8_t)(v & 0xFF));
    w_u8(w, (uint8_t)(v >> 8));
}

static void w_u32(writer_t *w, uint32_t v) {
    w_u16(w, (uint16_t)(v & 0xFFFF));
    w_u16(w, (uint16_t)(v >> 16));
}

// Escreve os 'len' bits menos significativos de 'code', do mais significativo
// para o menos significativo (MSB primeiro).
static void w_bits(writer_t *w, uint32_t code, uint8_t len) {
    for (int i = len - 1; i >= 0; i--) {
        w->cur = (uint8_t)((w->cur << 1) | ((code >> i) & 1u));
        if (++w->nb == 8) {
            w_u8(w, w->cur);
            w->cur = 0;
            w->nb = 0;
        }
    }
}

// Completa o último byte com zeros (padding).
static void w_flush(writer_t *w) {
    if (w->nb > 0) {
        w_u8(w, (uint8_t)(w->cur << (8 - w->nb)));
        w->cur = 0;
        w->nb = 0;
    }
}

// Grava k e os pares (símbolo, tamanho) dos símbolos usados, em ordem crescente.
static uint16_t write_table(writer_t *w, const uint8_t len[256]) {
    uint16_t k = 0;
    for (int s = 0; s < 256; s++)
        if (len[s]) k++;

    w_u16(w, k);
    for (int s = 0; s < 256; s++) {
        if (!len[s]) continue;
        w_u8(w, (uint8_t)s);
        w_u8(w, len[s]);
    }
    return k;
}

// API pública
size_t gi_max_size(uint16_t w, uint16_t h) {
    // Cabeçalho (12) + duas tabelas no pior caso (2 + 2*256 cada) + bitstream.
    return 12 + 2 * (2 + 2 * 256) + 2 * (size_t)w * h + 1;
}

// Buffers de trabalho estáticos
static uint32_t s_freq_c[256], s_freq_v[256];
static uint8_t s_len_c[256], s_len_v[256];
static uint32_t s_code_c[256], s_code_v[256];

size_t gi_encode(const uint8_t *img, uint16_t w, uint16_t h, uint8_t bits,
                 uint8_t *out, size_t out_cap, gi_stats_t *stats) {
    if (!img || !out || w == 0 || h == 0 || bits < 1 || bits > 8) return 0;

    const size_t n = (size_t)w * h;
    const uint8_t shift = (uint8_t)(8 - bits);

    // 1ª passada: RLE só para contar as frequências
    memset(s_freq_c, 0, sizeof(s_freq_c));
    memset(s_freq_v, 0, sizeof(s_freq_v));

    run_iter_t it = {img, n, 0, shift};
    uint8_t rl, rv;
    uint32_t num_runs = 0;
    while (next_run(&it, &rl, &rv)) {
        s_freq_c[rl]++;
        s_freq_v[rv]++;
        num_runs++;
    }

    // Huffman: comprimentos e códigos canônicos
    if (!huff_lengths(s_freq_c, s_len_c)) return 0;
    if (!huff_lengths(s_freq_v, s_len_v)) return 0;
    canonical_codes(s_len_c, s_code_c);
    canonical_codes(s_len_v, s_code_v);

    // Cabeçalho e tabelas
    writer_t wr = {out, out_cap, 0, 0, 0};
    w_u8(&wr, 'G');
    w_u8(&wr, 'I');
    w_u8(&wr, GI_VERSION);
    w_u8(&wr, bits);
    w_u16(&wr, w);
    w_u16(&wr, h);
    w_u32(&wr, num_runs);
    const uint16_t kc = write_table(&wr, s_len_c);
    const uint16_t kv = write_table(&wr, s_len_v);
    const size_t header_bytes = wr.pos;

    // 2ª passada: RLE de novo, agora escrevendo os códigos
    it.i = 0;
    while (next_run(&it, &rl, &rv)) {
        w_bits(&wr, s_code_c[rl], s_len_c[rl]);
        w_bits(&wr, s_code_v[rv], s_len_v[rv]);
    }
    w_flush(&wr);

    if (wr.pos > out_cap) return 0;  // não coube

    if (stats) {
        stats->num_runs = num_runs;
        stats->kc = kc;
        stats->kv = kv;
        stats->header_bytes = header_bytes;
        stats->stream_bytes = wr.pos - header_bytes;
        stats->total_bytes = wr.pos;
    }
    return wr.pos;
}
