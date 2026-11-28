// app_httpd.h  -  rotas HTTP
//
//   GET /raw                      imagem em cinza sem compressão (dataset)
//   GET /e1?bits=8                E1: imagem em cinza comprimida em GI (RLE + Huffman), 1..8 bits (8 = sem perdas)
//   GET /e1?codec=jpeg&q=50       E1 com JPEG, para comparação (qualidade 1..100, escala do OpenCV)
//   GET /e2                       E2: máscara 0/1 comprimida em GI (bits = 8, sem perdas)
//   GET /e2?fmt=bits|bytes        E2 sem compressão (bits: 8 pixels por byte), para comparação
//   GET /paridade                 cinza + máscara do MESMO quadro (teste com o Python)
//   GET /fundo?action=capturar      média de N_BACKGROUNDS quadros da bandeja vazia
//   GET /fundo?action=limpar        apaga o fundo (segmentação sem subtração)
//   GET /fundo                    baixa o fundo guardado
//   GET /set?var=X&val=Y          exposição, ganho, brilho, contraste
//   GET /status                   ajustes atuais em JSON
#pragma once

#include <Arduino.h>
#include "esp_camera.h"
#include "esp_http_server.h"
#include "esp_timer.h"
#include "img_converters.h"
#include "image_process.h"
#include "rle_huff.h"

// Lê um parâmetro da query string.
static bool get_param(httpd_req_t *req, const char *key, char *val, size_t n) {
  char q[96];
  return httpd_req_get_url_query_str(req, q, sizeof(q)) == ESP_OK && httpd_query_key_value(q, key, val, n) == ESP_OK;
}

// Cabeçalhos comuns. Os textos ficam no struct para ficar ativo até o envio da resposta.
struct Headers {
  char w[8], h[8], cap[24], proc[24], extra[16], raw[16], bits[4];
};

static void set_headers(httpd_req_t *req, Headers &c, int64_t t_cap, int64_t t_proc) {
  snprintf(c.w, sizeof(c.w), "%d", W);
  snprintf(c.h, sizeof(c.h), "%d", H);
  snprintf(c.cap, sizeof(c.cap), "%lld", (long long)t_cap);
  snprintf(c.proc, sizeof(c.proc), "%lld", (long long)t_proc);
  httpd_resp_set_hdr(req, "X-Width", c.w);
  httpd_resp_set_hdr(req, "X-Height", c.h);
  httpd_resp_set_hdr(req, "X-Capture-Time-us", c.cap);  // captura + cópia da ROI
  httpd_resp_set_hdr(req, "X-Proc-Time-us", c.proc);    // processamento na placa
}

// GET /raw
static esp_err_t raw_handler(httpd_req_t *req) {
  int64_t t_cap;
  if (!get_roi(t_cap)) return httpd_resp_send_500(req);
  Headers c;
  set_headers(req, c, t_cap, 0);
  httpd_resp_set_type(req, "application/octet-stream");
  return httpd_resp_send(req, (const char *)gray_buf, N);
}

// GET /e1?bits=8 (GI) | /e1?codec=jpeg&q=50
static esp_err_t e1_handler(httpd_req_t *req) {
  char codec[8] = "gi", v[8];
  get_param(req, "codec", codec, sizeof(codec));
  bool jpeg = !strcmp(codec, "jpeg");

  int64_t t_cap;
  if (!get_roi(t_cap)) return httpd_resp_send_500(req);
  Headers c;

  if (jpeg) {
    int q = get_param(req, "q", v, sizeof(v)) ? atoi(v) : 50;
    q = constrain(q, 1, 100);
    int64_t t0 = esp_timer_get_time();
    uint8_t *jpg = nullptr;
    size_t jpg_len = 0;
    if (!fmt2jpg(gray_buf, N, W, H, PIXFORMAT_GRAYSCALE, q, &jpg, &jpg_len)) return httpd_resp_send_500(req);
    set_headers(req, c, t_cap, esp_timer_get_time() - t0);
    snprintf(c.extra, sizeof(c.extra), "%d", q);
    snprintf(c.raw, sizeof(c.raw), "%u", (unsigned)N);
    httpd_resp_set_hdr(req, "X-Codec", "jpeg");
    httpd_resp_set_hdr(req, "X-Quality", c.extra);
    httpd_resp_set_hdr(req, "X-Raw-Bytes", c.raw);
    httpd_resp_set_type(req, "image/jpeg");
    esp_err_t r = httpd_resp_send(req, (const char *)jpg, jpg_len);
    free(jpg);
    return r;
  }

  int bits = get_param(req, "bits", v, sizeof(v)) ? atoi(v) : 8;
  bits = constrain(bits, 1, 8);
  int64_t t0 = esp_timer_get_time();
  size_t len = gi_encode(gray_buf, (uint16_t)W, (uint16_t)H, (uint8_t)bits, work_buf, work_cap, nullptr);
  if (!len) return httpd_resp_send_500(req);
  set_headers(req, c, t_cap, esp_timer_get_time() - t0);
  snprintf(c.bits, sizeof(c.bits), "%d", bits);
  snprintf(c.raw, sizeof(c.raw), "%u", (unsigned)N);
  httpd_resp_set_hdr(req, "X-Codec", "gi");
  httpd_resp_set_hdr(req, "X-Bits", c.bits);
  httpd_resp_set_hdr(req, "X-Raw-Bytes", c.raw);  // tamanho sem compressão
  httpd_resp_set_type(req, "application/octet-stream");
  return httpd_resp_send(req, (const char *)work_buf, len);
}

// GET /e2 (GI) | /e2?fmt=bits|bytes (sem compressão)
static esp_err_t e2_handler(httpd_req_t *req) {
  char fmt[8] = "gi";
  get_param(req, "fmt", fmt, sizeof(fmt));
  bool bytes = !strcmp(fmt, "bytes");
  bool packed = !strcmp(fmt, "bits");

  int64_t t_cap;
  if (!get_roi(t_cap)) return httpd_resp_send_500(req);
  int64_t t0 = esp_timer_get_time();
  uint8_t thres = threshold_otsu();

  const uint8_t *payload;
  size_t n;
  if (bytes) {
    payload = mask_buf;
    n = N;
  } else if (packed) {
    n = pack_bits();
    payload = bits_buf;
  } else {
    // máscara com valores 0/1: bits = 8 preserva os valores (com bits = 1 tudo viraria 0)
    n = gi_encode(mask_buf, (uint16_t)W, (uint16_t)H, 8, work_buf, work_cap, nullptr);
    if (!n) return httpd_resp_send_500(req);
    payload = work_buf;
  }
  int64_t t_proc = esp_timer_get_time() - t0;

  Headers c;
  set_headers(req, c, t_cap, t_proc);
  snprintf(c.extra, sizeof(c.extra), "%u", thres);
  snprintf(c.raw, sizeof(c.raw), "%u", (unsigned)((N + 7) / 8));
  httpd_resp_set_hdr(req, "X-Threshold", c.extra);
  httpd_resp_set_hdr(req, "X-Format", bytes ? "bytes" : packed ? "bits" : "gi");
  httpd_resp_set_hdr(req, "X-Raw-Bytes", c.raw);  // máscara empacotada, 1 bit por pixel
  httpd_resp_set_type(req, "application/octet-stream");
  return httpd_resp_send(req, (const char *)payload, n);
}

// GET /paridade : N bytes de cinza seguidos de N bytes de máscara, do mesmo quadro
static esp_err_t parity_handler(httpd_req_t *req) {
  int64_t t_cap;
  if (!get_roi(t_cap)) return httpd_resp_send_500(req);
  int64_t t0 = esp_timer_get_time();
  uint8_t thres = threshold_otsu();
  Headers c;
  set_headers(req, c, t_cap, esp_timer_get_time() - t0);
  snprintf(c.extra, sizeof(c.extra), "%u", thres);
  httpd_resp_set_hdr(req, "X-Threshold", c.extra);
  httpd_resp_set_hdr(req, "X-Fundo", has_background ? "1" : "0");
  httpd_resp_set_type(req, "application/octet-stream");
  if (httpd_resp_send_chunk(req, (const char *)gray_buf, N) != ESP_OK) return ESP_FAIL;
  if (httpd_resp_send_chunk(req, (const char *)mask_buf, N) != ESP_OK) return ESP_FAIL;
  return httpd_resp_send_chunk(req, nullptr, 0);
}

// GET /fundo?action=capturar|limpar  (sem ação: baixa o fundo)
static esp_err_t background_handler(httpd_req_t *req) {
  char action[12] = "";
  get_param(req, "action", action, sizeof(action));

  if (!strcmp(action, "capturar")) {
    uint16_t *sum = (uint16_t *)ps_malloc(N * sizeof(uint16_t));
    if (!sum) return httpd_resp_send_500(req);
    memset(sum, 0, N * sizeof(uint16_t));
    int64_t t;
    for (int k = 0; k < N_BACKGROUNDS; k++) {
      if (!get_roi(t)) {
        free(sum);
        return httpd_resp_send_500(req);
      }
      for (size_t i = 0; i < N; i++) sum[i] += gray_buf[i];
      delay(60);  // garante quadros diferentes
    }
    for (size_t i = 0; i < N; i++) background_buff[i] = (sum[i] + N_BACKGROUNDS / 2) / N_BACKGROUNDS;
    free(sum);
    has_background = true;
    return httpd_resp_sendstr(req, "fundo capturado");
  }
  if (!strcmp(action, "limpar")) {
    has_background = false;
    return httpd_resp_sendstr(req, "fundo apagado");
  }
  if (!has_background) {
    httpd_resp_send_err(req, HTTPD_404_NOT_FOUND, "sem fundo");
    return ESP_FAIL;
  }
  Headers c;
  set_headers(req, c, 0, 0);
  httpd_resp_set_type(req, "application/octet-stream");
  return httpd_resp_send(req, (const char *)background_buff, N);
}

// GET /set?var=X&val=Y
static esp_err_t set_handler(httpd_req_t *req) {
  char var[20], val[12];
  if (!get_param(req, "var", var, sizeof(var)) || !get_param(req, "val", val, sizeof(val))) {
    httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "use /set?var=X&val=Y");
    return ESP_FAIL;
  }
  int v = atoi(val);
  sensor_t *s = esp_camera_sensor_get();
  int r = -1;
  if (!strcmp(var, "aec"))             r = s->set_exposure_ctrl(s, v);  // exposição automática 0/1
  else if (!strcmp(var, "aec_value"))  r = s->set_aec_value(s, v);      // exposição manual 0..1200
  else if (!strcmp(var, "agc"))        r = s->set_gain_ctrl(s, v);      // ganho automático 0/1
  else if (!strcmp(var, "agc_gain"))   r = s->set_agc_gain(s, v);       // ganho manual 0..30
  else if (!strcmp(var, "brightness")) r = s->set_brightness(s, v);     // -2..2
  else if (!strcmp(var, "contrast"))   r = s->set_contrast(s, v);       // -2..2
  if (r != 0) {
    httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "variavel ou valor invalido");
    return ESP_FAIL;
  }
  return httpd_resp_sendstr(req, "ok");
}

// GET /status
static esp_err_t status_handler(httpd_req_t *req) {
  sensor_t *s = esp_camera_sensor_get();
  char out[320];
  snprintf(out, sizeof(out),
           "{\"largura\":%d,\"altura\":%d,\"roi\":[%d,%d,%d,%d],\"fundo\":%s,"
           "\"obj_claro\":%s,\"gauss_k\":%d,\"open_k\":%d,\"close_k\":%d,"
           "\"aec\":%u,\"aec_value\":%u,\"agc\":%u,\"agc_gain\":%u,\"brightness\":%d,\"contrast\":%d}",
           W, H, OX, OY, W, H, has_background ? "true" : "false",
           OBJ_CLARO ? "true" : "false", GAUSS_K, OPEN_K, CLOSE_K,
           s->status.aec, s->status.aec_value, s->status.agc, s->status.agc_gain,
           s->status.brightness, s->status.contrast);
  httpd_resp_set_type(req, "application/json");
  return httpd_resp_sendstr(req, out);
}

// Registra uma rota GET. A struct começa zerada, então os campos opcionais
// (websocket etc.) ficam com valores padrão e não geram avisos.
static void register_route(httpd_handle_t srv, const char *uri, esp_err_t (*handler)(httpd_req_t *)) {
  httpd_uri_t r = {};
  r.uri = uri;
  r.method = HTTP_GET;
  r.handler = handler;
  r.user_ctx = nullptr;
  httpd_register_uri_handler(srv, &r);
}

static void start_server() {
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.stack_size = 8192;
  httpd_handle_t srv = nullptr;
  if (httpd_start(&srv, &cfg) != ESP_OK) {
    Serial.println("Falha ao iniciar o servidor HTTP");
    return;
  }
  register_route(srv, "/raw", raw_handler);
  register_route(srv, "/e1", e1_handler);
  register_route(srv, "/e2", e2_handler);
  register_route(srv, "/paridade", parity_handler);
  register_route(srv, "/fundo", background_handler);
  register_route(srv, "/set", set_handler);
  register_route(srv, "/status", status_handler);
}
