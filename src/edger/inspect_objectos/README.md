# inspect_objectos (firmware da ESP32-CAM)

| Arquivo | Conteúdo |
| --- | --- |
| `inspect_objectos.ino` | Câmera, ROI, Wi-Fi, `setup()` e `loop()` |
| `camera_pins.h` | Pinos da AI Thinker ESP32-CAM |
| `image_process.h` | ROI, gaussiano, Otsu, erosão, dilatação e segmentação |
| `app_httpd.h` | Rotas HTTP |
| `rle_huff.h` / `rle_huff.cpp` | Compressão GI (cópia de `Enconding/`) |
| `keys.h` | Wi-Fi (fora do Git; modelo em `keys_exemplo.h`) |

## Rotas

| Rota | Envia |
| --- | --- |
| `/e1?bits=8` | E1: imagem em cinza comprimida em GI (1 a 8 bits; 8 = sem perdas) |
| `/e1?codec=jpeg&q=50` | E1 em JPEG, para comparação |
| `/e2` | E2: máscara 0/1 comprimida em GI |
| `/e2?fmt=bits` ou `fmt=bytes` | E2 sem compressão, para comparação |
| `/raw` | Imagem sem compressão (dataset) |
| `/paridade` | Imagem e máscara do mesmo quadro |
| `/fundo?acao=capturar` / `limpar` | Fundo da segmentação (sem ação: baixa o fundo) |
| `/set?var=X&val=Y`, `/status` | Ajustes do sensor e da segmentação |

Cabeçalhos de cada resposta:

- `X-Capture-Time-us`: tempo de captura;
- `X-Proc-Time-us`: processamento na placa (compressão e, na E2, a segmentação);
- `X-Raw-Bytes`: tamanho sem compressão;
- `X-Threshold`: limiar de Otsu (só nas rotas que segmentam).
