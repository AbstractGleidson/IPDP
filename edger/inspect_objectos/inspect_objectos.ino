/*
 * inspect_objectos.ino 
 *
 * Estratégias:
 *   E1: a placa envia a imagem inteira em tons de cinza, comprimida (JPEG).
 *   E2: a placa segmenta as peças e envia só a imagem binária (1 bit por pixel).
 *
 * Arquivos:
 *   camera_pins.h          pinos da AI Thinker ESP32-CAM
 *   image_process.h        ROI, gaussiano, Otsu, erosão, dilatação e segmentação
 *   app_httpd.h            rotas HTTP
 *   inspect_objectos.ino   câmera, ROI, Wi-Fi, setup e loop
 */

#include <Arduino.h>
#include <WiFi.h>
#include "esp_camera.h"
#include "keys.h"  // WIFI_SSID e WIFI_PASS
#include "camera_pins.h"
#include "image_process.h"
#include "app_httpd.h"

#define FRAME_SIZE FRAMESIZE_VGA  // VGA 640x480

// Região de interesse recortada (0 = quadro inteiro)
#define ROI_X 0
#define ROI_Y 0
#define ROI_W 0
#define ROI_H 0

static bool iniciar_camera() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_GRAYSCALE;
  config.frame_size = FRAME_SIZE;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.fb_count = 2;
  config.grab_mode = CAMERA_GRAB_LATEST;
  if (esp_camera_init(&config) != ESP_OK) return false;

  sensor_t *s = esp_camera_sensor_get();
  s->set_whitebal(s, 0);
  // s->set_exposure_ctrl(s, 0);
  // s->set_aec_value(s, 300);
  // s->set_gain_ctrl(s, 0);
  // s->set_agc_gain(s, 0);
  return true;
}

// Define a ROI a partir do tamanho real do quadro.
static bool configurar_roi() {
  camera_fb_t *fb = esp_camera_fb_get(); // buffer com imagem

  // verfica se conseguiu ler 
  if (!fb) {
    Serial.println("Falha no primeiro quadro");
    return false;
  }

  int fw = fb->width, fh = fb->height; // recupera dimenssoes da imagem

  // libera buffer
  esp_camera_fb_return(fb);

  // configura as constantes da região de interesse
  OX = ROI_X;
  OY = ROI_Y;
  W = (ROI_W > 0) ? ROI_W : fw - OX;
  H = (ROI_H > 0) ? ROI_H : fh - OY;

  // define o tamanho dos kernels usados
  int r_max = max(max(GAUSS_K, OPEN_K), CLOSE_K) / 2;

  // verifica se a região de interesse é possivel
  if (OX < 0 || OY < 0 || W <= 2 * r_max || H <= 2 * r_max || OX + W > fw || OY + H > fh) 
  {
    Serial.println("ROI inválida: confira ROI_X, ROI_Y, ROI_W e ROI_H");
    return false;
  }

  // tamanho da imagem vetorizado
  N = (size_t) W * H;
  Serial.printf("Quadro %dx%d | ROI %dx%d em (%d,%d)\n", fw, fh, W, H, OX, OY);
  return true;
}

void setup() {
  Serial.begin(9600);
  Serial.println();

  if (!psramFound()) 
  { 
    Serial.println("PSRAM não encontrada (Ferramentas > PSRAM)"); 
    return; 
  }

  if (!iniciar_camera()) 
  { 
    Serial.println("Falha ao iniciar a câmera");
    return; 
  }

  if (!configurar_roi()) 
    return;

  if (!alloc_buffers()) 
  { 
    Serial.println("Falha ao alocar buffers (tente QVGA ou uma ROI menor)"); 
    return; 
  }

  WiFi.begin(WIFI_SSID, WIFI_PASS); // inicia conexão
  WiFi.setSleep(false);
  Serial.print("Conectando ao Wi-Fi");

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();

  iniciar_servidor();
  Serial.print("Pronto: http://");
  
  Serial.println(WiFi.localIP());
}

void loop() {
  delay(10000);  // tudo acontece nas tarefas do servidor HTTP
}
