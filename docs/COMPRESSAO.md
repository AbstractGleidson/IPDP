# Compressão GI (RLE + Huffman canônico)

O formato **GI** foi implementado pelo grupo para reduzir o que a ESP32 envia pela rede. A compressão roda na placa, em C; a descompressão roda no servidor, em Python.

## Sumário

1. [Arquivos](#1-arquivos)
2. [Como o algoritmo funciona](#2-como-o-algoritmo-funciona)
3. [Formato do pacote](#3-formato-do-pacote)
4. [Codificador em C (`rle_huff`)](#4-codificador-em-c-rle_huff)
5. [Decodificadores em Python](#5-decodificadores-em-python)
6. [Testar a compressão no PC](#6-testar-a-compressão-no-pc)
7. [Cuidados](#7-cuidados)

---

## 1. Arquivos

| Arquivo | Onde roda | Função |
| --- | --- | --- |
| `src/Enconding/rle_huff.h` | ESP32 e PC | Formato do pacote e interface do codificador |
| `src/Enconding/rle_huff.cpp` | ESP32 e PC | Codificador (`gi_encode`) |
| `src/Enconding/decod.py` | PC | Decodificador de referência, por linha de comando (lê `.gi` e salva PNG) |
| `src/Enconding/test_rle_huff.cpp` | PC | Comprime uma imagem e mostra as estatísticas |
| `src/Enconding/stb_image.h` | PC | Leitura de PNG/JPEG para o teste (biblioteca de terceiros) |
| `src/server/gi_decoder.py` | servidor | Decodificador usado pelo sistema (mesmo algoritmo do `decod.py`, a partir dos bytes da resposta HTTP) |
| `src/edger/inspect_objectos/rle_huff.*` | ESP32 | Cópia do codificador compilada no firmware |

## 2. Como o algoritmo funciona

**1. Quantização.** Cada pixel mantém só os `bits` bits mais significativos (`valor >> (8 − bits)`). Com `bits = 8` não há perda; com menos bits, tons vizinhos viram o mesmo nível e surgem corridas mais longas.

**2. RLE.** A imagem, lida linha após linha, vira uma sequência de corridas `(comprimento, valor)`. Uma corrida tem no máximo 255 pixels (`GI_MAX_RUN`); corridas maiores são divididas.

**3. Huffman canônico.** Comprimentos e valores ganham **tabelas de Huffman separadas**, porque têm distribuições muito diferentes. Símbolos frequentes recebem códigos curtos.

**4. Códigos canônicos.** Ordenando os símbolos por (tamanho do código, símbolo), o primeiro recebe o código 0 e cada seguinte recebe o anterior + 1, deslocado à esquerda quando o tamanho aumenta. Assim o pacote só precisa levar o **tamanho** do código de cada símbolo, e não o código inteiro.

**5. Duas passadas.** O codificador percorre a imagem duas vezes: a primeira só conta as frequências para montar as tabelas; a segunda escreve os códigos.

Na reconstrução, cada índice quantizado volta para o **centro do seu intervalo**: com 4 bits, o índice 3 representa os tons 48 a 63 e vira 56.

## 3. Formato do pacote

Todos os campos são *little-endian*.

| Deslocamento | Tamanho | Campo |
| --- | --- | --- |
| 0 | 2 | magic `'G' 'I'` |
| 2 | 1 | versão (`GI_VERSION` = 1) |
| 3 | 1 | bits de quantização (1 a 8) |
| 4 | 2 | largura (uint16) |
| 6 | 2 | altura (uint16) |
| 8 | 4 | número de corridas (uint32) |
| 12 | 2 | `kc` = nº de símbolos da tabela de comprimentos |
| 14 | 2·`kc` | pares (comprimento da corrida, tamanho do código), em ordem crescente de símbolo |
| … | 2 | `kv` = nº de símbolos da tabela de valores |
| … | 2·`kv` | pares (valor quantizado, tamanho do código) |
| … | … | bitstream (bit mais significativo primeiro): para cada corrida, código do comprimento e depois código do valor |

Tamanho total = 12 + (2 + 2·`kc`) + (2 + 2·`kv`) + ⌈bits do fluxo / 8⌉.

## 4. Codificador em C (`rle_huff`)

```c
size_t gi_max_size(uint16_t w, uint16_t h);
size_t gi_encode(const uint8_t *img, uint16_t w, uint16_t h, uint8_t bits,
                 uint8_t *out, size_t out_cap, gi_stats_t *stats);
```

| Função | Descrição |
| --- | --- |
| `gi_max_size(w, h)` | Maior tamanho possível do pacote; use para alocar o buffer de saída (na ESP: `ps_malloc(gi_max_size(w, h))`) |
| `gi_encode(...)` | Comprime `img` (w×h bytes, 1 byte por pixel) mantendo `bits` bits. Devolve o número de bytes escritos em `out`, ou 0 em caso de erro (parâmetros inválidos ou `out_cap` insuficiente) |

`stats` é opcional (pode ser `NULL`) e devolve o número de corridas, de símbolos de cada tabela e o tamanho do cabeçalho, do fluxo e do total.

O codificador **não usa `malloc` nem a STL**: a memória de trabalho é estática (cerca de 9 KB), o que o torna seguro para a ESP32. Por isso também não é seguro chamá-lo de duas tarefas ao mesmo tempo; no firmware, o servidor HTTP atende um pedido por vez.

## 5. Decodificadores em Python

### `src/server/gi_decoder.py` (usado pelo sistema)

| Função | Descrição |
| --- | --- |
| `read_header(data)` | Devolve `(bits, largura, altura, nº de corridas)`; erro se não for um pacote GI versão 1 |
| `decode(data)` | Devolve `(bits, índices)`, com os índices quantizados numa matriz altura × largura |
| `reconstruct(indices, bits)` | Índice → tom de cinza, no centro do intervalo |
| `decode_image(data)` | Pacote da E1 → imagem em cinza reconstruída |
| `decode_mask(data)` | Pacote da E2 → máscara 0/255 (exige `bits = 8`) |
| `quantize(img, bits)` | O que a E1 entrega ao servidor depois de comprimir e descomprimir, sem precisar comprimir de verdade |
| `compressed_size(img, bits)` | Número **exato** de bytes que o `gi_encode()` geraria, sem montar o fluxo de bits |

O `compressed_size()` é exato porque o custo total de um código de Huffman ótimo não depende de como os empates são resolvidos: basta somar as fusões da construção da árvore. Ele é usado pela avaliação offline do `training_pipeline.py`, que mede bytes e acurácia sem a placa.

A descompressão é Python puro. Na E2, a máscara volta em poucos milissegundos; na E1 sem perdas, uma imagem VGA leva da ordem de centenas de milissegundos, porque quase todo pixel vira uma corrida. Esse tempo aparece separado como `t_decompress_ms`.

### `src/Enconding/decod.py` (ferramenta de linha de comando)

```bash
python src/Enconding/decod.py arquivo.gi                 # salva arquivo_decoded.png
python src/Enconding/decod.py arquivo.gi -o saida.png
```

Precisa do **Pillow** (`pip install pillow`), que não está no `requirements.txt`.

## 6. Testar a compressão no PC

```bash
cd src/Enconding
g++ -O2 -o test_rle_huff test_rle_huff.cpp rle_huff.cpp
./test_rle_huff parafuso_0.png 4            # comprime com 4 bits -> parafuso_0_q4.gi
python decod.py parafuso_0_q4.gi            # descomprime -> parafuso_0_q4_decoded.png
```

O teste mostra o número de corridas, os símbolos de cada tabela, o tamanho do cabeçalho e do fluxo e a razão de compressão.

## 7. Cuidados

- **A máscara da E2 deve ser comprimida com `bits = 8`.** A máscara da ESP32 tem valores 0 e 1. Com `bits = 1`, o codificador guarda só o bit mais significativo, que é sempre 0: a máscara inteira viraria zero, sem erro. O firmware já faz isso certo, e o `decode_mask()` recusa pacotes com outro valor.
- **O RLE não ajuda em imagem ruidosa sem perdas.** Na E1 com 8 bits, pixels vizinhos raramente são iguais, então quase todo pixel vira uma corrida e a razão de compressão fica perto de 1. Com menos bits, as corridas crescem e a compressão melhora muito.
- **Mantenham as duas cópias iguais.** O firmware compila a cópia em `src/edger/inspect_objectos/`. Se mudarem o codificador em `src/Enconding/`, copiem para lá.
