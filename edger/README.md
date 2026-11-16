# Borda: ESP32-CAM (baseado no exemplo CameraWebServer)

Esta pasta contém o código que roda na **câmera** do projeto de inspeção de peças. Ele parte do exemplo oficial **CameraWebServer**, que vem com o pacote ESP32 da Arduino IDE, e vai sendo adaptado para as estratégias E1, E2 e E3 do trabalho.

Este README explica como o exemplo funciona e quais mudanças fazem sentido para o projeto.

---

## O que tem em cada arquivo

| Arquivo | Para que serve |
| --- | --- |
| `CameraWebServer.ino` | Arquivo principal. Configura a câmera, conecta no Wi-Fi e liga o servidor web. |
| `app_httpd.cpp` | O servidor web em si. Cada endereço (rota) que você acessa no navegador é tratado aqui. |
| `board_config.h` | Onde você escolhe **qual placa** está usando. |
| `camera_pins.h` | Mapa de pinos de cada placa. Não precisa mexer. |
| `camera_index.h` | A página web de controle, já compactada (gzip) em forma de bytes. Não dá para editar diretamente. |
| `partitions.csv` | Como a memória flash é dividida. Reserva bastante espaço para o programa. |
| `ci.yml` | Configuração de testes automáticos do repositório da Espressif. Pode ignorar. |

## Como o exemplo funciona

O fluxo é bem simples:

1. **`setup()`** monta a estrutura `camera_config_t` com os pinos, a resolução e o formato da imagem, e chama `esp_camera_init()`.
2. A placa se conecta ao Wi-Fi e imprime o IP no Monitor Serial.
3. **`startCameraServer()`** liga **dois servidores HTTP**:
   - na porta **80**, a página de controle e as rotas de captura e configuração;
   - na porta **81**, o vídeo ao vivo (`/stream`), separado para não travar o resto.
4. **`loop()`** não faz nada. Todo o trabalho acontece nas tarefas do servidor web.

Ou seja, a ESP32 fica **esperando pedidos**. Quem decide quando tirar a foto é quem acessa o endereço. Isso combina muito bem com o nosso projeto: o computador pede uma imagem, a câmera responde e o computador mede quanto tempo levou.

### Rotas mais úteis

| Rota | O que faz |
| --- | --- |
| `http://IP/` | Página de controle com todos os ajustes da câmera |
| `http://IP/capture` | Tira **uma foto** e devolve em JPEG. É a principal para o projeto. |
| `http://IP:81/stream` | Vídeo ao vivo (bom para posicionar a câmera e ajustar a luz) |
| `http://IP/control?var=X&val=Y` | Muda um ajuste, por exemplo `var=quality&val=20` |
| `http://IP/status` | Devolve todos os ajustes atuais em JSON |
| `http://IP/bmp` | Foto sem compressão (BMP) |

O `/capture` já devolve um cabeçalho `X-Timestamp`, e o tempo de captura aparece no Monitor Serial quando o nível de log está em *Info*.

### Ajustes que já existem via `/control`

`framesize`, `quality`, `brightness`, `contrast`, `saturation`, `awb` (balanço de branco automático), `aec` (exposição automática), `agc` (ganho automático), `aec_value`, `agc_gain`, `hmirror`, `vflip`, `led_intensity`, entre outros.

## Como colocar para rodar

1. Instale o pacote **esp32 da Espressif** no Gerenciador de Placas da Arduino IDE.
2. Escolha a placa **AI Thinker ESP32-CAM** em *Ferramentas → Placa*.
3. Em *Ferramentas*, deixe **PSRAM: Enabled** e escolha um esquema de partição com bastante espaço para o app (por exemplo, *Huge APP*).
4. **Ajuste o `board_config.h`** (veja o aviso abaixo).
5. Coloque o nome e a senha do Wi-Fi no `CameraWebServer.ino`.
6. Grave na placa (lembre de ligar o GPIO0 ao GND durante a gravação, se o seu módulo não tiver placa USB com botão).
7. Abra o Monitor Serial em **115200** e acesse o IP que aparecer.

> **Atenção:** o `board_config.h` atual está com `CAMERA_MODEL_ESP_EYE` ativado. Para o ESP32-CAM comum, comente essa linha e ative a do AI Thinker:
>
> ```cpp
> //#define CAMERA_MODEL_ESP_EYE  // Has PSRAM
> #define CAMERA_MODEL_AI_THINKER // Has PSRAM
> ```
>
> Com a placa errada, a câmera falha ao iniciar (erro `0x105` ou parecido no Serial).

---

## Modificações pensando no projeto

As sugestões estão em ordem: as primeiras são simples e já resolvem a estratégia **E1**; as últimas preparam **E2** e **E3**.

### 1. Tirar a senha do Wi-Fi do código

Como o código vai para o GitHub, é melhor guardar a senha em um arquivo separado que não é enviado.

```cpp
// secrets.h  (adicione "secrets.h" no .gitignore)
#define WIFI_SSID "nome_da_rede"
#define WIFI_PASS "senha"
```

```cpp
// CameraWebServer.ino
#include "secrets.h"
const char *ssid = WIFI_SSID;
const char *password = WIFI_PASS;
```

### 2. Deixar as fotos sempre iguais (luz, cor e exposição fixas)

Os ajustes automáticos da câmera mudam a exposição e a cor de uma foto para outra. Isso atrapalha a segmentação e deixa a comparação entre estratégias injusta. Depois de achar uma boa configuração pela página de controle, fixe os valores no final do `setup()`:

```cpp
sensor_t *s = esp_camera_sensor_get();
s->set_whitebal(s, 0);       // desliga balanço de branco automático
s->set_awb_gain(s, 0);
s->set_exposure_ctrl(s, 0);  // desliga exposição automática
s->set_aec_value(s, 300);    // valor achado na página de controle
s->set_gain_ctrl(s, 0);      // desliga ganho automático
s->set_agc_gain(s, 0);
```

Também vale **desligar o LED de flash** (ou deixá-lo sempre com a mesma intensidade), já que a iluminação vai vir dos LEDs da caixa. No `capture_handler`, o flash liga e espera 150 ms antes de cada foto, o que soma tempo à latência medida.

### 3. Resolução e formato pensados para o projeto

O exemplo começa em UXGA (1600×1200), que é grande demais para o que precisamos. Duas opções:

**Opção A: só JPEG (mais simples, serve para E1).** Use uma resolução menor, como VGA ou QVGA:

```cpp
config.frame_size = FRAMESIZE_VGA;   // 640x480
config.pixel_format = PIXFORMAT_JPEG;
```

**Opção B: tons de cinza (serve para E1, E2 e E3).** A câmera entrega os pixels "crus", um byte por pixel. Isso é o que precisamos para fazer Otsu e RLE na própria placa:

```cpp
config.frame_size = FRAMESIZE_QVGA;       // 320x240 = 76.800 bytes por quadro
config.pixel_format = PIXFORMAT_GRAYSCALE;
config.fb_location = CAMERA_FB_IN_PSRAM;
config.fb_count = 2;
config.grab_mode = CAMERA_GRAB_LATEST;
```

> Se usar a opção B, apague a linha `s->set_framesize(s, FRAMESIZE_QVGA);` que fica dentro do `if (config.pixel_format == PIXFORMAT_JPEG)` e confira se o restante do `setup()` não depende do formato JPEG.

Para a E1 continuar funcionando na opção B, a ESP32 converte a imagem para JPEG por software (próximo item).

### 4. Escolher a qualidade do JPEG em cada pedido (E1)

Para o experimento da E1 precisamos variar a qualidade (10, 30, 50, 70, 90). Há um detalhe importante: **no sensor OV2640, a escala de `quality` é invertida e vai de 0 a 63** (quanto menor, melhor). Ela não corresponde à escala 0 a 100 usada no relatório e no OpenCV.

Com a opção B do item anterior, dá para usar a escala padrão: captura em cinza e comprime com `frame2jpg`, que recebe qualidade de 0 a 100. Uma nova rota `/jpeg?q=50` ficaria assim (no `app_httpd.cpp`):

```cpp
static esp_err_t jpeg_handler(httpd_req_t *req) {
  int q = 50;
  char *buf = NULL;
  char val[8];
  if (parse_get(req, &buf) == ESP_OK) {
    if (httpd_query_key_value(buf, "q", val, sizeof(val)) == ESP_OK) q = atoi(val);
    free(buf);
  }

  int64_t t0 = esp_timer_get_time();
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) { httpd_resp_send_500(req); return ESP_FAIL; }

  uint8_t *jpg = NULL;
  size_t jpg_len = 0;
  bool ok = frame2jpg(fb, q, &jpg, &jpg_len);   // escala 0-100, como no OpenCV
  esp_camera_fb_return(fb);
  if (!ok) { httpd_resp_send_500(req); return ESP_FAIL; }

  char t_borda[24];
  snprintf(t_borda, sizeof(t_borda), "%lld", esp_timer_get_time() - t0);
  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "X-Edge-Time-us", t_borda);   // tempo gasto na borda
  esp_err_t res = httpd_resp_send(req, (const char *)jpg, jpg_len);
  free(jpg);
  return res;
}
```

O cabeçalho `X-Edge-Time-us` informa ao computador quanto tempo a placa gastou. Assim dá para separar o tempo da borda do tempo de rede na análise.

> Se preferir manter a opção A (JPEG direto do sensor, mais rápido), use `s->set_quality(s, q)` com a escala 0 a 63 e descarte uma foto depois de mudar a qualidade (`esp_camera_fb_return(esp_camera_fb_get());`), porque o buffer pode ainda conter um quadro antigo.

### 5. Segmentação e RLE na própria placa (E2/E3)

Com a imagem em tons de cinza, a ESP32 consegue calcular o limiar de Otsu e mandar só a **máscara binária comprimida em RLE**. É o principal teste da ideia de "processar na borda para economizar rede".

**Limiar de Otsu:**

```cpp
static uint8_t otsu_threshold(const uint8_t *img, size_t n) {
  uint32_t hist[256] = {0};
  for (size_t i = 0; i < n; i++) hist[img[i]]++;

  uint64_t sum = 0;
  for (int t = 0; t < 256; t++) sum += (uint64_t)t * hist[t];

  uint64_t sumB = 0;
  uint32_t wB = 0;
  double best = 0;
  uint8_t thr = 0;
  for (int t = 0; t < 256; t++) {
    wB += hist[t];
    if (wB == 0) continue;
    uint32_t wF = n - wB;
    if (wF == 0) break;
    sumB += (uint64_t)t * hist[t];
    double mB = (double)sumB / wB;
    double mF = (double)(sum - sumB) / wF;
    double between = (double)wB * wF * (mB - mF) * (mB - mF);
    if (between > best) { best = between; thr = t; }
  }
  return thr;
}
```

**RLE da máscara** (as corridas alternam fundo e peça, sempre começando pelo fundo; com fundo escuro, a peça é o que fica acima do limiar):

```cpp
// Devolve o número de corridas gravadas em "out".
static size_t rle_encode(const uint8_t *img, size_t n, uint8_t thr, uint16_t *out) {
  size_t k = 0;
  uint8_t atual = 0;      // começa contando fundo
  uint32_t run = 0;
  for (size_t i = 0; i < n; i++) {
    uint8_t px = img[i] > thr ? 1 : 0;
    if (px == atual) {
      run++;
      if (run == 65535) { out[k++] = 65535; out[k++] = 0; run = 0; }  // evita estouro do uint16
    } else {
      out[k++] = run;
      atual = px;
      run = 1;
    }
  }
  out[k++] = run;
  return k;
}
```

**Rota `/mask`:**

```cpp
static esp_err_t mask_handler(httpd_req_t *req) {
  int64_t t0 = esp_timer_get_time();
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb || fb->format != PIXFORMAT_GRAYSCALE) {
    if (fb) esp_camera_fb_return(fb);
    httpd_resp_send_500(req);
    return ESP_FAIL;
  }

  size_t n = fb->len;
  uint16_t *runs = (uint16_t *)ps_malloc((n + 2) * sizeof(uint16_t));  // pior caso
  if (!runs) { esp_camera_fb_return(fb); httpd_resp_send_500(req); return ESP_FAIL; }

  uint8_t thr = otsu_threshold(fb->buf, n);
  size_t k = rle_encode(fb->buf, n, thr, runs);
  int w = fb->width, h = fb->height;
  esp_camera_fb_return(fb);

  char sw[8], sh[8], st[8], stime[24];
  snprintf(sw, sizeof(sw), "%d", w);
  snprintf(sh, sizeof(sh), "%d", h);
  snprintf(st, sizeof(st), "%u", thr);
  snprintf(stime, sizeof(stime), "%lld", esp_timer_get_time() - t0);

  httpd_resp_set_type(req, "application/octet-stream");
  httpd_resp_set_hdr(req, "X-Width", sw);
  httpd_resp_set_hdr(req, "X-Height", sh);
  httpd_resp_set_hdr(req, "X-Threshold", st);
  httpd_resp_set_hdr(req, "X-Edge-Time-us", stime);
  esp_err_t res = httpd_resp_send(req, (const char *)runs, k * sizeof(uint16_t));
  free(runs);
  return res;
}
```

No computador, basta ler a lista de `uint16` (little-endian), reconstruir a máscara alternando 0 e 1 e conferir que ela é idêntica à máscara gerada pelo Otsu do servidor. Esse é o teste de "compressão sem perdas" pedido no relatório.

> Daqui para a **E3** é um passo: em vez de mandar a máscara, a placa pode rotular as regiões e mandar apenas área, perímetro e número de Euler de cada peça. Se a memória ou o tempo apertarem, a E3 pode ficar só no envio da máscara em RLE, como previsto no plano de riscos.

### 6. Registrar as novas rotas

No `startCameraServer()`, crie as estruturas e registre no **primeiro servidor** (porta 80). O limite atual é de 16 rotas e o exemplo usa 10, então ainda tem espaço.

```cpp
httpd_uri_t jpeg_uri = { .uri = "/jpeg", .method = HTTP_GET, .handler = jpeg_handler, .user_ctx = NULL };
httpd_uri_t mask_uri = { .uri = "/mask", .method = HTTP_GET, .handler = mask_handler, .user_ctx = NULL };

// dentro do if (httpd_start(&camera_httpd, &config) == ESP_OK) { ... }
httpd_register_uri_handler(camera_httpd, &jpeg_uri);
httpd_register_uri_handler(camera_httpd, &mask_uri);
```

> Coloque as funções `otsu_threshold`, `rle_encode`, `jpeg_handler` e `mask_handler` **antes** de `startCameraServer()` no arquivo.

### 7. Limpar o que não vamos usar (opcional)

Para medir o desempenho com menos interferência, dá para remover do registro as rotas de depuração (`/xclk`, `/reg`, `/greg`, `/pll`, `/resolution`, `/bmp`). Recomendamos **manter** a página `/` e o `/stream` enquanto a caixa de captura é ajustada, e só tirá-los na hora dos experimentos.

---

## Como o computador conversa com a câmera

Um exemplo mínimo em Python para a E1:

```python
import time, requests, numpy as np, cv2

IP = "192.168.0.50"

t0 = time.perf_counter()
r = requests.get(f"http://{IP}/jpeg", params={"q": 50}, timeout=5)
latencia_ms = (time.perf_counter() - t0) * 1000

img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_GRAYSCALE)
print(f"{len(r.content)} bytes | {latencia_ms:.1f} ms | borda: {int(r.headers['X-Edge-Time-us'])/1000:.1f} ms")
```

Como o computador faz o pedido e recebe a resposta, ele mesmo mede a latência de ida e volta, sem precisar sincronizar o relógio das duas máquinas.