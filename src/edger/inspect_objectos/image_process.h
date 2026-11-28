// Aquisição da ROI e segmentação
#pragma once

#include <Arduino.h>
#include "esp_camera.h"
#include "esp_timer.h"
#include "rle_huff.h"

// Configuração do processamento
static const bool OBJ_CLARO = true; // sem fundo: peça mais clara que o fundo 
static const int  GAUSS_K = 3; // kernel do gaussiano: 1 (desliga), 3, 5, 7 ou 9
static const int  OPEN_K = 3;  // kernel da abertura (remove ruído): 0 ou 1 desliga
static const int  CLOSE_K = 3; // kernel do fechamento (fecha falhas): 0 ou 1 desliga
static const int  N_BACKGROUNDS = 8; // quadros na média do fundo

// wargs de erro
static_assert(GAUSS_K >= 1 && GAUSS_K <= 9 && GAUSS_K % 2 == 1, "GAUSS_K deve ser 1, 3, 5, 7 ou 9");
static_assert(OPEN_K <= 1 || OPEN_K % 2 == 1, "OPEN_K deve ser ímpar");
static_assert(CLOSE_K <= 1 || CLOSE_K % 2 == 1, "CLOSE_K deve ser ímpar");

// Estado e buffers (PSRAM, alocados uma vez)
static int W = 0, H = 0, OX = 0, OY = 0; // tamanho e origem da ROI
static size_t N = 0; // pixels da ROI
static uint8_t  *gray_buf = nullptr; // ROI em cinza
static uint8_t  *tmp_buf = nullptr; // imagem suavizada
static uint8_t  *aux_buf = nullptr; // diferença com o fundo / passo da morfologia
static uint8_t  *mask_buf = nullptr; // máscara 0/1
static uint8_t  *background_buff = nullptr; // fundo
static uint8_t  *bits_buf = nullptr; // máscara empacotada
static uint16_t *blur_buf = nullptr; // passada horizontal do gaussiano (somas sem dividir)

// Área de trabalho compartilhada: o gaussiano usa como blur_buf (2N bytes) e, depois da
// segmentação, a compressão GI escreve o pacote nela (gi_max_size = 2N + ~1 KB).
// As duas coisas nunca acontecem ao mesmo tempo, e isso economiza ~600 KB de PSRAM em VGA.
static uint8_t *work_buf = nullptr;
static size_t work_cap = 0;
static bool has_background = false;

// aloca memoria para os buffes
static bool alloc_buffers() {
    gray_buf = (uint8_t *)ps_malloc(N);
    tmp_buf = (uint8_t *)ps_malloc(N);
    aux_buf = (uint8_t *)ps_malloc(N);
    mask_buf = (uint8_t *)ps_malloc(N);
    background_buff = (uint8_t *)ps_malloc(N);
    bits_buf = (uint8_t *)ps_malloc((N + 7) / 8);
    work_cap = gi_max_size((uint16_t)W, (uint16_t)H);
    work_buf = (uint8_t *)ps_malloc(work_cap);
    blur_buf = (uint16_t *)work_buf;

    return gray_buf && tmp_buf && aux_buf && mask_buf && background_buff && bits_buf && work_buf;
}


// Copia a ROI do quadro da câmera para gray_buf.
static bool get_roi(int64_t &t_capture) {
    int64_t t0 = esp_timer_get_time(); // t do frame
    camera_fb_t *fb = esp_camera_fb_get(); // pega frame da camera

    // se a aquisição falhou
    if (!fb) 
    return false;

    // confere formato e se a ROI cabe no quadro
    if (fb->format != PIXFORMAT_GRAYSCALE || (int)fb->width < OX + W || (int)fb->height < OY + H) 
    {
    esp_camera_fb_return(fb); // libera buffer
    return false;
    }

    // cópia a região de interesse para o buffer
    for (int y = 0; y < H; y++)
    memcpy(gray_buf + (size_t)y * W, fb->buf + (size_t)(OY + y) * fb->width + OX, W);

    esp_camera_fb_return(fb); 
    t_capture = esp_timer_get_time() - t0; // tempo de processamento do roi

    return true;
}


// Índice refletido na borda sem repetir o pixel da borda 
static inline int reflex(int i, int n) 
{
    if (i < 0) return -i;
    if (i >= n) return 2 * n - 2 - i;
    return i;
}

// Coeficientes binomiais (linha k-1 do triângulo de Pascal): a aproximação inteira
// clássica da gaussiana. k=3: 1 2 1 | k=5: 1 4 6 4 1 | k=7: 1 6 15 20 15 6 1
// Amostragem da gaussiana
static void binomial_kernel(int k, uint16_t *c) {
    c[0] = 1;

    for (int i = 1; i < k; i++) 
    {
    c[i] = 0;
    for (int j = i; j > 0; j--) c[j] += c[j - 1];
    }
}

// Gaussiano KxK separável em aritmética inteira: passada horizontal (somas inteiras em blur_buf),
// passada vertical e uma única divisão arredondada por 4^(K-1).
static void gaussian_blur(const uint8_t *src, uint8_t *dst) {

    if (GAUSS_K <= 1) {
        if (dst != src) memcpy(dst, src, N); // copia os dados para o destino e retorna 
        return;
    }

    uint16_t c[9];
    binomial_kernel(GAUSS_K, c); // gera os coeficiente em c

    const int r = GAUSS_K / 2; // calcula o tamanho da mascara
    const int shift = 2 * (GAUSS_K - 1); // sum do kernel 

    // passada orizontal 
    for (int y = 0; y < H; y++) 
    {  
        const uint8_t *linha = src + (size_t) y * W;
        uint16_t *out = blur_buf + (size_t)y * W;

        for (int x = 0; x < W; x++) 
        {
            uint32_t s = 0;
            for (int i = -r; i <= r; i++) s += c[i + r] * linha[reflex(x + i, W)];
            out[x] = (uint16_t)s;
        }
    }

    // passada vertical 
    for (int y = 0; y < H; y++) {  // vertical + normalização
        uint8_t *out = dst + (size_t) y * W;
        for (int x = 0; x < W; x++) 
        {
            uint32_t s = 0;
            for (int i = -r; i <= r; i++) s += c[i + r] * blur_buf[(size_t) reflex(y + i, H) * W + x];
            out[x] = (s + (1u << (shift - 1))) >> shift; // normaliza
        }
    }
}


// Limiar que maximiza a variância entre classes.
static uint8_t otsu(const uint8_t *img, size_t n) 
{
    uint32_t hist[256] = {0};

    // calcula o histograma da imagem
    for (size_t i = 0; i < n; i++) 
        hist[img[i]]++;

    uint64_t sum = 0;  // sum de t * hist[t]

    // acumulada das intensidades pelo peso
    for (int t = 0; t < 256; t++) 
        sum += (uint64_t) t * hist[t];

    uint64_t sumB = 0;
    uint32_t wB = 0;
    double best = 0;
    uint8_t thres = 0;

    for (int t = 0; t < 256; t++) {
        wB += hist[t];// pixels com intensidade <= t (classe do fundo)

        if (wB == 0) 
            continue; // ainda não há pixels abaixo de t

        uint32_t wF = n - wB; // pixels acima de t

        if (wF == 0) 
            break; // todos os pixels já estão abaixo de t

        sumB += (uint64_t)t * hist[t];

        double mB = (double)sumB / wB;
        double mF = (double)(sum - sumB) / wF;
        double between = (double)wB * (double)wF * (mB - mF) * (mB - mF);  // variância entre classes 

        // atualiza com o melhor limiar
        if (between > best) 
        {
            best = between;
            thres = t;
        }
    }

    return thres;
}


// Uma passada 1D (horizontal ou vertical) numa janela de k pixels: mínimo (erosão) ou
// máximo (dilatação). Vizinhos fora da imagem são ignorados.
static void morph_1d(const uint8_t *src, uint8_t *dst, int k, bool is_erode, bool horizontal) 
{
  const int r = k / 2;

    for (int y = 0; y < H; y++) {
        for (int x = 0; x < W; x++) {

            uint8_t v = is_erode ? 1 : 0;

            // kernel vetorizado na simetria de r
            for (int i = -r; i <= r; i++) {
                int xx = horizontal ? x + i : x;
                int yy = horizontal ? y : y + i;

                // dentro da imagem
                if (xx < 0 || yy < 0 || xx >= W || yy >= H) 
                    continue;

                uint8_t p = src[(size_t)yy * W + xx];

                v = is_erode ? (v & p) : (v | p);
            }
            dst[(size_t)y * W + x] = v; // salva na posição adequada
        }
    }
}

// Erosão com elemento quadrado KxK (separável). 
static void erode(uint8_t *src, uint8_t *dst, uint8_t *tmp, int k) {
    if (k <= 1) 
    {
        if (dst != src) 
            memcpy(dst, src, N);
        return;

    }
    morph_1d(src, tmp, k, true, true);
    morph_1d(tmp, dst, k, true, false);
}

// Dilatação com elemento quadrado KxK (separável). 
static void dilate(uint8_t *src, uint8_t *dst, uint8_t *tmp, int k) {
    if (k <= 1) 
    {
        if (dst != src) 
            memcpy(dst, src, N);
        return;
    }
    morph_1d(src, tmp, k, false, true);
    morph_1d(tmp, dst, k, false, false);
}

// Segmenta gray_buf -> mask_buf (0/1). Devolve o limiar de Otsu usado.
static uint8_t threshold_otsu() {
    const uint8_t *src = gray_buf;
    bool bright = OBJ_CLARO;

    if (has_background) 
    {  
        for (size_t i = 0; i < N; i++) // diferença absoluta: fica clara qualquer que seja sua cor
            aux_buf[i] = abs((int)gray_buf[i] - (int)background_buff[i]);
        src = aux_buf;
        bright = true;
    }

    // blur na imagem 
    gaussian_blur(src, tmp_buf);
    uint8_t thres = otsu(tmp_buf, N); // calcula o limiar de otsu

    // aplica a limiarização
    for (size_t i = 0; i < N; i++) 
    {
        bool above = tmp_buf[i] > thres;
        mask_buf[i] = (bright ? above : !above) ? 1 : 0;
    }

    // operações morfologicas de pós-processamento
    if (OPEN_K > 1) 
    {   
        erode(mask_buf, mask_buf, aux_buf, OPEN_K);
        dilate(mask_buf, mask_buf, aux_buf, OPEN_K);
    }

    if (CLOSE_K > 1) 
    {  
        dilate(mask_buf, mask_buf, aux_buf, CLOSE_K);
        erode(mask_buf, mask_buf, aux_buf, CLOSE_K);
    }

    return thres;
}

// Empacota a máscara: 8 pixels por byte, bit mais significativo primeiro.
static size_t pack_bits() 
{
    size_t nb = (N + 7) / 8;
    memset(bits_buf, 0, nb);
    
    for (size_t i = 0; i < N; i++)
        if (mask_buf[i]) bits_buf[i >> 3] |= 0x80 >> (i & 7);
    return nb;
}
