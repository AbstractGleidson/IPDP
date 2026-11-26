// app_httpd.h  -  rotas HTTP
//
//   GET /raw                      imagem em cinza sem compressão (dataset)
//   GET /e1?q=50                  E1: imagem em cinza comprimida em JPEG, qualidade 1..100 (escala do OpenCV)
//   GET /e2?fmt=bits|bytes        E2: máscara binária (bits: 8 pixels por byte)
//   GET /paridade                 cinza + máscara do MESMO quadro (teste com o Python)
//   GET /fundo?acao=capturar      média de N_BACKGROUNDS quadros da bandeja vazia
//   GET /fundo?acao=limpar        apaga o fundo (segmentação sem subtração)
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

// Lê um parâmetro da query string.
static bool param(httpd_req_t *req, const char *chave, char *val, size_t n) {
  char q[96];
  return httpd_req_get_url_query_str(req, q, sizeof(q)) == ESP_OK && httpd_query_key_value(q, chave, val, n) == ESP_OK;
}

// Cabeçalhos comuns. Os textos ficam no struct para viver até o envio da resposta.
struct Cabecalhos {
  char w[8], h[8], cap[24], proc[24], extra[16];
};

static void cabecalhos(httpd_req_t *req, Cabecalhos &c, int64_t t_cap, int64_t t_proc) {
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
  Cabecalhos c;
  cabecalhos(req, c, t_cap, 0);
  httpd_resp_set_type(req, "application/octet-stream");
  return httpd_resp_send(req, (const char *)gray_buf, N);
}

// GET /e1?q=50
static esp_err_t e1_handler(httpd_req_t *req) {
  char v[8];
  int q = param(req, "q", v, sizeof(v)) ? atoi(v) : 50;
  q = constrain(q, 1, 100);

  int64_t t_cap;
  if (!get_roi(t_cap)) return httpd_resp_send_500(req);
  int64_t t0 = esp_timer_get_time();
  uint8_t *jpg = nullptr;
  size_t jpg_len = 0;
  if (!fmt2jpg(gray_buf, N, W, H, PIXFORMAT_GRAYSCALE, q, &jpg, &jpg_len)) return httpd_resp_send_500(req);
  int64_t t_proc = esp_timer_get_time() - t0;

  Cabecalhos c;
  cabecalhos(req, c, t_cap, t_proc);
  snprintf(c.extra, sizeof(c.extra), "%d", q);
  httpd_resp_set_hdr(req, "X-Quality", c.extra);
  httpd_resp_set_type(req, "image/jpeg");
  esp_err_t r = httpd_resp_send(req, (const char *)jpg, jpg_len);
  free(jpg);
  return r;
}

// GET /e2?fmt=bits|bytes
static esp_err_t e2_handler(httpd_req_t *req) {
  char fmt[8] = "bits";
  param(req, "fmt", fmt, sizeof(fmt));
  bool bytes = !strcmp(fmt, "bytes");

  int64_t t_cap;
  if (!get_roi(t_cap)) return httpd_resp_send_500(req);
  int64_t t0 = esp_timer_get_time();
  uint8_t thres = threshold_otsu();
  size_t n = bytes ? N : empacotar_bits();
  int64_t t_proc = esp_timer_get_time() - t0;

  Cabecalhos c;
  cabecalhos(req, c, t_cap, t_proc);
  snprintf(c.extra, sizeof(c.extra), "%u", thres);
  httpd_resp_set_hdr(req, "X-Threshold", c.extra);
  httpd_resp_set_hdr(req, "X-Format", bytes ? "bytes" : "bits");
  httpd_resp_set_type(req, "application/octet-stream");
  return httpd_resp_send(req, (const char *)(bytes ? mask_buf : bits_buf), n);
}

// GET /paridade : N bytes de cinza seguidos de N bytes de máscara, do mesmo quadro
static esp_err_t paridade_handler(httpd_req_t *req) {
  int64_t t_cap;
  if (!get_roi(t_cap)) return httpd_resp_send_500(req);
  int64_t t0 = esp_timer_get_time();
  uint8_t thres = threshold_otsu();
  Cabecalhos c;
  cabecalhos(req, c, t_cap, esp_timer_get_time() - t0);
  snprintf(c.extra, sizeof(c.extra), "%u", thres);
  httpd_resp_set_hdr(req, "X-Threshold", c.extra);
  httpd_resp_set_hdr(req, "X-Fundo", has_background ? "1" : "0");
  httpd_resp_set_type(req, "application/octet-stream");
  if (httpd_resp_send_chunk(req, (const char *)gray_buf, N) != ESP_OK) return ESP_FAIL;
  if (httpd_resp_send_chunk(req, (const char *)mask_buf, N) != ESP_OK) return ESP_FAIL;
  return httpd_resp_send_chunk(req, nullptr, 0);
}

// GET /fundo?acao=capturar|limpar  (sem ação: baixa o fundo)
static esp_err_t fundo_handler(httpd_req_t *req) {
  char acao[12] = "";
  param(req, "acao", acao, sizeof(acao));

  if (!strcmp(acao, "capturar")) {
    uint16_t *soma = (uint16_t *)ps_malloc(N * sizeof(uint16_t));
    if (!soma) return httpd_resp_send_500(req);
    memset(soma, 0, N * sizeof(uint16_t));
    int64_t t;
    for (int k = 0; k < N_BACKGROUNDS; k++) {
      if (!get_roi(t)) {
        free(soma);
        return httpd_resp_send_500(req);
      }
      for (size_t i = 0; i < N; i++) soma[i] += gray_buf[i];
      delay(60);  // garante quadros diferentes
    }
    for (size_t i = 0; i < N; i++) background_buff[i] = (soma[i] + N_BACKGROUNDS / 2) / N_BACKGROUNDS;
    free(soma);
    has_background = true;
    return httpd_resp_sendstr(req, "fundo capturado");
  }
  if (!strcmp(acao, "limpar")) {
    has_background = false;
    return httpd_resp_sendstr(req, "fundo apagado");
  }
  if (!has_background) {
    httpd_resp_send_err(req, HTTPD_404_NOT_FOUND, "sem fundo");
    return ESP_FAIL;
  }
  Cabecalhos c;
  cabecalhos(req, c, 0, 0);
  httpd_resp_set_type(req, "application/octet-stream");
  return httpd_resp_send(req, (const char *)background_buff, N);
}

// GET /set?var=X&val=Y
static esp_err_t set_handler(httpd_req_t *req) {
  char var[20], val[12];
  if (!param(req, "var", var, sizeof(var)) || !param(req, "val", val, sizeof(val))) {
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
static void registrar_rota(httpd_handle_t srv, const char *uri, esp_err_t (*handler)(httpd_req_t *)) {
  httpd_uri_t r = {};
  r.uri = uri;
  r.method = HTTP_GET;
  r.handler = handler;
  r.user_ctx = nullptr;
  httpd_register_uri_handler(srv, &r);
}

static void iniciar_servidor() {
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.stack_size = 8192;
  httpd_handle_t srv = nullptr;
  if (httpd_start(&srv, &cfg) != ESP_OK) {
    Serial.println("Falha ao iniciar o servidor HTTP");
    return;
  }
  registrar_rota(srv, "/raw", raw_handler);
  registrar_rota(srv, "/e1", e1_handler);
  registrar_rota(srv, "/e2", e2_handler);
  registrar_rota(srv, "/paridade", paridade_handler);
  registrar_rota(srv, "/fundo", fundo_handler);
  registrar_rota(srv, "/set", set_handler);
  registrar_rota(srv, "/status", status_handler);
}
