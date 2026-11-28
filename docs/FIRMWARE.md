# Firmware da ESP32-CAM (`src/edger/inspect_objectos`)

Firmware enxuto que transforma a ESP32-CAM num servidor HTTP de imagens. Ele captura em **tons de cinza, sem compressão**, e faz na própria placa só o que cada estratégia exige: comprimir (E1) ou segmentar e comprimir (E2).

## Sumário

1. [Arquivos](#1-arquivos)
2. [Como gravar](#2-como-gravar)
3. [Configuração](#3-configuração)
4. [Módulos](#4-módulos)
5. [Referência das rotas HTTP](#5-referência-das-rotas-http)
6. [Memória](#6-memória)
7. [O exemplo CameraWebServer](#7-o-exemplo-camerawebserver)

---

## 1. Arquivos

| Arquivo | Conteúdo |
| --- | --- |
| `inspect_objectos.ino` | Arquivo principal: inicializa a câmera, define a ROI, conecta no Wi-Fi e liga o servidor |
| `camera_pins.h` | Pinos do módulo de câmera da AI Thinker ESP32-CAM |
| `image_process.h` | Constantes da segmentação, buffers, ROI, gaussiano, Otsu, erosão, dilatação e segmentação |
| `app_httpd.h` | Todas as rotas HTTP |
| `rle_huff.h` / `rle_huff.cpp` | Compressão GI (cópia de `src/Enconding/`) |
| `keys.h` | Nome e senha do Wi-Fi (`WIFI_SSID`, `WIFI_PASS`); **não deve ir para o Git** |
| `partitions.csv` | Divisão da memória flash (cerca de 3,75 MB para o programa) |

> Se alterarem `src/Enconding/rle_huff.cpp` ou `rle_huff.h`, copiem a nova versão para esta pasta: o firmware compila a cópia local.

## 2. Como gravar

1. Instale o pacote **esp32 da Espressif** no Gerenciador de Placas da Arduino IDE.
2. Crie o `keys.h` na pasta do sketch:
   ```cpp
   #pragma once
   #define WIFI_SSID "nome_da_rede"
   #define WIFI_PASS "senha_da_rede"
   ```
3. Abra o `inspect_objectos.ino`. A pasta precisa se chamar `inspect_objectos`, igual ao `.ino`, senão a IDE não abre o sketch.
4. Em *Ferramentas*: placa **AI Thinker ESP32-CAM** e **PSRAM habilitada**.
5. Grave (se o módulo não tiver placa USB com botão, ligue o GPIO0 ao GND durante a gravação).
6. Abra o Monitor Serial em **9600** baud. A placa mostra o tamanho do quadro, a ROI e, depois de conectar, o IP:
   ```
   Quadro 640x480 | ROI 640x480 em (0,0)
   Conectando ao Wi-Fi.....
   Pronto: http://10.13.31.16
   ```
7. Teste no navegador: `http://IP/status` deve devolver um JSON.

## 3. Configuração

### Captura (`inspect_objectos.ino`)

| Constante | Padrão | Função |
| --- | --- | --- |
| `FRAME_SIZE` | `FRAMESIZE_VGA` | Resolução (VGA = 640×480). `FRAMESIZE_QVGA` (320×240) deixa a segmentação cerca de 4× mais rápida |
| `ROI_X`, `ROI_Y` | 0 | Canto superior esquerdo da região de interesse |
| `ROI_W`, `ROI_H` | 0 | Largura e altura da ROI (0 = até o fim do quadro) |

A **ROI** recorta só a área útil (a esteira) antes de qualquer processamento. Vale para todas as rotas: imagem, máscara e fundo têm o tamanho da ROI.

Os ajustes fixos do sensor ficam em `init_camera()`. Depois de achar bons valores de exposição e ganho (pela rota `/set` ou pelas teclas do `capture_dataset.py`), descomentem e gravem:

```cpp
s->set_exposure_ctrl(s, 0);   // desliga a exposição automática
s->set_aec_value(s, 300);     // exposição manual
s->set_gain_ctrl(s, 0);       // desliga o ganho automático
s->set_agc_gain(s, 0);        // ganho manual
```

### Segmentação (`image_process.h`)

| Constante | Padrão | Valores | Função |
| --- | --- | --- | --- |
| `OBJ_CLARO` | `true` | `true` / `false` | Sem fundo capturado: a peça é mais clara que o fundo? (retroiluminação ou fundo branco: `false`) |
| `GAUSS_K` | 3 | 1, 3, 5, 7, 9 | Tamanho do gaussiano (1 desliga) |
| `OPEN_K` | 3 | 0/1 ou ímpar | Abertura: remove pontos soltos |
| `CLOSE_K` | 3 | 0/1 ou ímpar | Fechamento: fecha falhas pequenas (valores grandes fecham os furos das peças) |
| `N_BACKGROUNDS` | 8 | inteiro | Quadros na média do fundo |

**`OBJ_CLARO`, `GAUSS_K`, `OPEN_K` e `CLOSE_K` precisam ser iguais a `BRIGHT_OBJECT`, `GAUSS_K`, `OPEN_K` e `CLOSE_K` do `src/server/config.py`.** Valores inválidos (gaussiano par ou maior que 9, morfologia par) são barrados na compilação por `static_assert`.

## 4. Módulos

### `inspect_objectos.ino`

Junta tudo. O `loop()` não faz nada: todo o trabalho acontece nas tarefas do servidor HTTP.

| Função | O que faz |
| --- | --- |
| `init_camera()` | Configura o sensor em tons de cinza, com 2 buffers na PSRAM e modo "sempre o quadro mais recente"; desliga o balanço de branco |
| `setup_roi()` | Lê o tamanho real do primeiro quadro, calcula a ROI e valida se ela cabe no quadro e é maior que os kernels |
| `setup()` | Verifica a PSRAM, inicia a câmera, define a ROI, aloca os buffers, conecta no Wi-Fi e liga o servidor |

### `image_process.h`

Toda a parte de imagem da placa. Os buffers são alocados **uma única vez** na PSRAM.

| Função | O que faz |
| --- | --- |
| `alloc_buffers()` | Aloca `gray_buf`, `tmp_buf`, `aux_buf`, `mask_buf`, `background_buff`, `bits_buf` e a área de trabalho `work_buf` |
| `get_roi(t_capture)` | Pega um quadro da câmera, copia a ROI para `gray_buf` e devolve o tempo gasto |
| `reflex(i, n)` | Índice refletido na borda (sem repetir o pixel da borda) |
| `binomial_kernel(k, c)` | Coeficientes binomiais: a aproximação inteira da gaussiana |
| `gaussian_blur(src, dst)` | Gaussiano `GAUSS_K`×`GAUSS_K` separável, inteiro, com uma divisão arredondada no fim |
| `otsu(img, n)` | Limiar que maximiza a variância entre classes do histograma |
| `morph_1d(...)` | Uma passada 1D (horizontal ou vertical) de mínimo ou máximo |
| `erode(src, dst, tmp, k)` | Erosão com elemento quadrado k×k (duas passadas 1D) |
| `dilate(src, dst, tmp, k)` | Dilatação com elemento quadrado k×k |
| `threshold_otsu()` | Segmentação completa: fundo → gaussiano → Otsu → abertura → fechamento. Lê `gray_buf`, escreve `mask_buf` (0/1) e devolve o limiar |
| `pack_bits()` | Empacota a máscara em 8 pixels por byte (bit mais significativo primeiro) |

Variáveis de estado: `W`, `H` (tamanho da ROI), `OX`, `OY` (origem da ROI), `N` (pixels), `has_background` (há fundo capturado).

### `app_httpd.h`

| Função | O que faz |
| --- | --- |
| `get_param(req, key, val, n)` | Lê um parâmetro da query string |
| `set_headers(req, h, t_cap, t_proc)` | Cabeçalhos comuns: tamanho e tempos |
| `raw_handler`, `e1_handler`, `e2_handler`, `parity_handler`, `background_handler`, `set_handler`, `status_handler` | Uma função por rota (ver a referência abaixo) |
| `register_route(srv, uri, handler)` | Registra uma rota GET |
| `start_server()` | Liga o servidor HTTP na porta 80 e registra todas as rotas |

### `rle_huff.h` / `rle_huff.cpp`

Compressão GI. Ver [COMPRESSAO.md](COMPRESSAO.md).

## 5. Referência das rotas HTTP

Todas as rotas são `GET` na porta 80. Toda resposta com imagem traz:

| Cabeçalho | Conteúdo |
| --- | --- |
| `X-Width`, `X-Height` | Tamanho da ROI |
| `X-Capture-Time-us` | Captura do quadro + recorte da ROI, em µs |
| `X-Proc-Time-us` | Processamento na placa (compressão; na E2, também a segmentação), em µs |

### `/raw`

Imagem em cinza **sem compressão**, para montar o dataset.

- **Resposta:** `largura × altura` bytes, linha após linha.

### `/e1`: estratégia E1

| Parâmetro | Padrão | Valores |
| --- | --- | --- |
| `bits` | 8 | 1 a 8 (8 = sem perdas) |
| `codec` | `gi` | `gi` ou `jpeg` |
| `q` | 50 | 1 a 100 (só com `codec=jpeg`, escala do OpenCV) |

- **Resposta:** pacote GI (`application/octet-stream`) ou JPEG (`image/jpeg`).
- **Cabeçalhos extras:** `X-Codec` (`gi` ou `jpeg`), `X-Bits` ou `X-Quality`, `X-Raw-Bytes` (tamanho sem compressão = largura × altura).
- **Exemplos:** `/e1?bits=4`, `/e1?codec=jpeg&q=70`.

### `/e2`: estratégia E2

| Parâmetro | Padrão | Valores |
| --- | --- | --- |
| `fmt` | `gi` | `gi` (comprimida), `bits` (8 pixels por byte) ou `bytes` (1 byte por pixel, 0/1) |

- **Resposta:** a máscara no formato pedido. No formato `gi`, a máscara 0/1 é comprimida com `bits = 8`.
- **Cabeçalhos extras:** `X-Threshold` (limiar de Otsu), `X-Format`, `X-Raw-Bytes` (máscara empacotada = ⌈largura × altura / 8⌉).

### `/paridade`

Imagem em cinza **e** máscara do **mesmo quadro**, para o `parity_test.py`.

- **Resposta:** `N` bytes de cinza seguidos de `N` bytes de máscara (0/1), com `N = largura × altura`.
- **Cabeçalhos extras:** `X-Threshold`, `X-Fundo` (`1` se há fundo capturado).

### `/fundo`

| Chamada | Efeito | Resposta |
| --- | --- | --- |
| `/fundo?acao=capturar` | Tira a média de `N_BACKGROUNDS` quadros (bandeja **vazia**) e guarda como fundo | `fundo capturado` |
| `/fundo?acao=limpar` | Apaga o fundo; a segmentação passa a usar só o limiar e `OBJ_CLARO` | `fundo apagado` |
| `/fundo` | Baixa o fundo guardado | `N` bytes, ou erro 404 `sem fundo` |

O fundo fica só na RAM: **some quando a placa reinicia**.

### `/set`

Ajusta o sensor: `/set?var=X&val=Y`. Responde `ok` ou erro 400.

| `var` | Valores | Efeito |
| --- | --- | --- |
| `aec` | 0 / 1 | Exposição automática |
| `aec_value` | 0 a 1200 | Exposição manual (com `aec=0`) |
| `agc` | 0 / 1 | Ganho automático |
| `agc_gain` | 0 a 30 | Ganho manual (com `agc=0`) |
| `brightness` | −2 a 2 | Brilho |
| `contrast` | −2 a 2 | Contraste |

### `/status`

JSON com o estado da placa:

```json
{"largura": 640, "altura": 480, "roi": [0, 0, 640, 480], "fundo": true,
 "obj_claro": true, "gauss_k": 3, "open_k": 3, "close_k": 3,
 "aec": 0, "aec_value": 300, "agc": 0, "agc_gain": 0, "brightness": 0, "contrast": 0}
```

O servidor usa `obj_claro`, `gauss_k`, `open_k` e `close_k` para avisar quando a segmentação da placa difere do `config.py`.

## 6. Memória

Todos os buffers ficam na PSRAM e são alocados uma vez, no `setup()`. Em VGA (N = 307.200 pixels):

| Buffer | Tamanho | Uso |
| --- | --- | --- |
| `gray_buf` | N | ROI em cinza |
| `tmp_buf` | N | imagem suavizada |
| `aux_buf` | N | diferença com o fundo e passo da morfologia |
| `mask_buf` | N | máscara 0/1 |
| `background_buff` | N | fundo |
| `bits_buf` | N/8 | máscara empacotada |
| `work_buf` | `gi_max_size(W, H)` ≈ 2N | área compartilhada: passada do gaussiano **e** saída da compressão GI |

O `work_buf` é compartilhado porque o gaussiano e a compressão nunca acontecem ao mesmo tempo: na E2, a segmentação termina antes da compressão começar. Isso economiza cerca de 600 KB em VGA. Se a alocação falhar, a placa avisa no Serial: reduzam a resolução para QVGA ou a ROI.

## 7. O exemplo CameraWebServer

A pasta `src/edger/CameraWebServer/` guarda o exemplo original da Espressif, com página de controle e vídeo ao vivo. Ele **não** tem as rotas do projeto, mas é útil para posicionar a câmera e ajustar a luz. Já está configurado para a AI Thinker (`CAMERA_MODEL_AI_THINKER` em `board_config.h`). O guia do exemplo está em `src/edger/README.md`.
