// test_rle_huff.cpp — Harness de teste no PC para rle_huff.cpp.
//
// Carrega uma imagem (convertida para tons de cinza), comprime com gi_encode
// e grava o pacote "GI" em <nome>_q<bits>.gi no diretório atual.
//
// Compilar:  g++ -O2 -o test_rle_huff test_rle_huff.cpp rle_huff.cpp
// Usar:      ./test_rle_huff parafuso_0.png 4
// Decodificar e conferir:
//            python decod.py parafuso_0_q4.gi --ref parafuso_0.png

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <string>

#define STB_IMAGE_IMPLEMENTATION
#include "stb_image.h"

#include "rle_huff.h"

// "dir/parafuso_0.png" -> "parafuso_0"
static std::string base_name(const std::string &path) {
    size_t slash = path.find_last_of("/\\");
    std::string name = (slash == std::string::npos) ? path : path.substr(slash + 1);
    size_t dot = name.find_last_of('.');
    return (dot == std::string::npos) ? name : name.substr(0, dot);
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        std::fprintf(stderr, "uso: %s <imagem> [bits=4]\n", argv[0]);
        return 1;
    }
    const int bits = (argc >= 3) ? std::atoi(argv[2]) : 4;
    if (bits < 1 || bits > 8) {
        std::fprintf(stderr, "bits deve estar entre 1 e 8\n");
        return 1;
    }

    int w, h, ch;
    unsigned char *img = stbi_load(argv[1], &w, &h, &ch, 1);  // força 1 canal
    if (!img) {
        std::fprintf(stderr, "erro ao abrir %s: %s\n", argv[1], stbi_failure_reason());
        return 1;
    }
    if (w > 65535 || h > 65535) {
        std::fprintf(stderr, "imagem grande demais para o formato (máx. 65535)\n");
        stbi_image_free(img);
        return 1;
    }

    const size_t cap = gi_max_size((uint16_t)w, (uint16_t)h);
    uint8_t *out = (uint8_t *)std::malloc(cap);
    if (!out) {
        std::fprintf(stderr, "sem memória\n");
        stbi_image_free(img);
        return 1;
    }

    gi_stats_t st;
    auto t0 = std::chrono::steady_clock::now();
    const size_t len = gi_encode(img, (uint16_t)w, (uint16_t)h, (uint8_t)bits, out, cap, &st);
    auto t1 = std::chrono::steady_clock::now();
    stbi_image_free(img);

    if (len == 0) {
        std::fprintf(stderr, "gi_encode falhou\n");
        std::free(out);
        return 1;
    }

    const std::string out_path = base_name(argv[1]) + "_q" + std::to_string(bits) + ".gi";
    FILE *f = std::fopen(out_path.c_str(), "wb");
    if (!f || std::fwrite(out, 1, len, f) != len) {
        std::fprintf(stderr, "erro ao gravar %s\n", out_path.c_str());
        if (f) std::fclose(f);
        std::free(out);
        return 1;
    }
    std::fclose(f);
    std::free(out);

    const size_t raw = (size_t)w * h;
    const double us = std::chrono::duration<double, std::micro>(t1 - t0).count();
    std::printf("imagem      : %s (%dx%d, %zu bytes crus)\n", argv[1], w, h, raw);
    std::printf("quantização : %d bits\n", bits);
    std::printf("corridas    : %u\n", st.num_runs);
    std::printf("tabelas     : kc=%u kv=%u\n", st.kc, st.kv);
    std::printf("cabeçalho   : %zu bytes (inclui tabelas)\n", st.header_bytes);
    std::printf("bitstream   : %zu bytes\n", st.stream_bytes);
    std::printf("total       : %zu bytes (razão %.2f:1)\n", st.total_bytes, (double)raw / st.total_bytes);
    std::printf("tempo       : %.1f us\n", us);
    std::printf("saída       : %s\n", out_path.c_str());
    return 0;
}
