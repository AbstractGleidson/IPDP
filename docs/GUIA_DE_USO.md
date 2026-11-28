# Guia de uso

Passo a passo para colocar o sistema para funcionar, do zero até o experimento final.

## Sumário

1. [Requisitos](#1-requisitos)
2. [Instalação do servidor](#2-instalação-do-servidor)
3. [Gravar a ESP32](#3-gravar-a-esp32)
4. [Conferir a comunicação e a segmentação](#4-conferir-a-comunicação-e-a-segmentação)
5. [Montar o dataset](#5-montar-o-dataset)
6. [Treinar](#6-treinar)
7. [Classificar ao vivo](#7-classificar-ao-vivo)
8. [Rodar o experimento E1 × E2](#8-rodar-o-experimento-e1--e2)
9. [Fundo branco ou retroiluminação](#9-fundo-branco-ou-retroiluminação)
10. [Problemas comuns](#10-problemas-comuns)

---

## 1. Requisitos

**Hardware**

- ESP32-CAM AI Thinker (com PSRAM) e um gravador USB
- Computador na **mesma rede Wi-Fi** da placa
- Esteira ou bandeja com iluminação estável e suporte fixo para a câmera (modelos em `3d_models/`)

**Software**

- Python 3.10 ou mais recente
- Arduino IDE com o pacote **esp32 da Espressif**

## 2. Instalação do servidor

Na raiz do repositório:

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Abra `src/server/config.py` e coloque o IP da placa em `ESP32_URL` (o IP aparece no Serial no passo seguinte).

> **Todos os comandos do servidor rodam a partir da raiz do repositório, no formato `python -m src.server.<módulo>`.**

## 3. Gravar a ESP32

Resumo (detalhes em [FIRMWARE.md](FIRMWARE.md#2-como-gravar)):

1. Crie `src/edger/inspect_objectos/keys.h` com `WIFI_SSID` e `WIFI_PASS`.
2. Abra `inspect_objectos.ino` na Arduino IDE.
3. Placa **AI Thinker ESP32-CAM**, **PSRAM habilitada**.
4. Grave e abra o Monitor Serial em **9600**. Anote o IP que aparece em `Pronto: http://…`.
5. Teste no navegador: `http://IP/status`.

## 4. Conferir a comunicação e a segmentação

1. **Ajuste a exposição.** Com a bandeja vazia, confira se a imagem não está estourada:
   ```bash
   python -c "from src.server.esp32_client import ESP32; import numpy as np; i=ESP32().raw().img; print('mediana:', np.median(i), '| estourados:', round((i>=250).mean()*100, 1), '%')"
   ```
   Se houver muitos pixels estourados, desligue a exposição automática (`http://IP/set?var=aec&val=0`) e ajuste `http://IP/set?var=aec_value&val=200` até melhorar.
2. **Capture o fundo na placa** (bandeja vazia): `http://IP/fundo?acao=capturar`.
3. **Coloque algumas peças e rode o teste de paridade:**
   ```bash
   python -m src.server.parity_test
   ```
   O esperado é `Fundo na ESP32: sim`, **0 pixels diferentes** em todas as repetições e `Compressão: OK`. Os painéis mostram o quadro e as máscaras: confira se as peças aparecem inteiras, com os furos abertos.

## 5. Montar o dataset

Leia antes o protocolo em [DATASET.md](DATASET.md).

```bash
python -m src.server.capture_dataset --session s01
```

1. Com a bandeja vazia, aperte **`b`** de 5 a 10 vezes (fundo do dataset) e **`f`** uma vez (fundo da placa).
2. Escolha a classe com **`1`** a **`5`** e a peça física com **`+`**/**`-`**.
3. Posicione a peça, confira o contorno na tela e aperte **espaço** para salvar.
4. Repita variando posição, rotação e face; depois troque de peça.

As fotos vão para `src/data/raw/` e cada uma ganha uma linha no `src/data/metadata.csv`.

## 6. Treinar

```bash
python -m src.server.training_pipeline
```

Acompanhe as cinco etapas na tela. Depois:

- confira as máscaras em `src/data/processed/` e a lista de fotos descartadas;
- veja as matrizes de confusão e a curva de compromisso em `src/server/results/`;
- o modelo fica em `src/server/models/classifier.joblib`.

Variações úteis para o relatório:

```bash
python -m src.server.training_pipeline --features hu          # só os momentos de Hu
python -m src.server.training_pipeline --model svm            # salva o SVM em vez do k-means
python -m src.server.training_pipeline --train-bits 4         # treina com a degradação da E1 em 4 bits
```

## 7. Classificar ao vivo

```bash
python -m src.server.classification_pipeline --strategy e1    # frame original com as peças identificadas
python -m src.server.classification_pipeline                  # E2: máscara feita na placa
```

Teclas: `1`/`2` troca E1/E2, `+`/`-` muda os bits, `o` mostra o frame original, `f` captura o fundo, `s` salva a tela, `q` sai.

## 8. Rodar o experimento E1 × E2

Monte uma cena fixa na bandeja (algumas peças, sem encostar) e rode:

```bash
python -m src.server.classification_pipeline --experiment --repetitions 30
```

O resultado fica em `src/server/results/experiment_<data>.csv` (um pedido por linha) e `…_summary.csv` (médias por configuração). Junto com o `compression_offline.csv` e a `tradeoff_curve.png` do treinamento, é a base dos resultados do relatório:

| Pergunta | Onde olhar |
| --- | --- |
| Quanto cada estratégia transmite? | `bytes_received`, `compression_ratio` |
| Quanto a placa trabalha? | `t_edge_ms` |
| Quanto custa a rede? | `t_network_ms` |
| Quanto o servidor trabalha? | `t_decompress_ms`, `t_segment_ms`, `t_server_ms` |
| Qual o tempo total? | `t_total_ms` |
| A compressão prejudica a classificação? | `accuracy` no `compression_offline.csv` |

## 9. Fundo branco ou retroiluminação

**Com fundo capturado (recomendado):** nada muda no código. A segmentação usa a diferença entre a foto e o fundo, então a peça se destaca seja ela clara ou escura. Só capture o fundo de novo (`f` ou `/fundo?acao=capturar`) e cuide para o branco não estourar (passo 4.1).

**Sem fundo, só com o limiar:** as peças passam a ser mais escuras que o fundo. Mude nos dois lados e regrave a placa:

- `src/edger/inspect_objectos/image_process.h`: `OBJ_CLARO = false`;
- `src/server/config.py`: `BRIGHT_OBJECT = False`;
- apague o fundo da placa: `http://IP/fundo?acao=limpar`.

No fundo branco, atenção às **sombras** (a subtração de fundo as junta com a peça) e aos **reflexos** do metal (podem abrir buracos na máscara). Para valer de verdade, capture uma sessão nova nesse fundo e treine de novo.

## 10. Problemas comuns

| Sintoma | Causa provável | Solução |
| --- | --- | --- |
| `ModuleNotFoundError: No module named 'src'` | Script rodado de dentro de `src/server` | Rode da raiz: `python -m src.server.<módulo>` |
| `Connection refused` ou tempo esgotado | IP errado ou redes diferentes | Confira `ESP32_URL` e se placa e computador estão na mesma rede |
| `PSRAM não encontrada` no Serial | PSRAM desabilitada | *Ferramentas → PSRAM → Enabled* |
| A IDE não abre o sketch | Pasta com nome diferente do `.ino` | A pasta precisa se chamar `inspect_objectos` |
| `Falha ao alocar buffers` | Resolução ou ROI grandes demais | Use `FRAMESIZE_QVGA` ou uma ROI menor |
| `A rota /e2 não devolveu um pacote GI` | Firmware antigo na placa | Grave o `inspect_objectos` atual, com `rle_huff.h/.cpp` na pasta |
| Paridade com pixels diferentes | Constantes diferentes entre placa e `config.py` | O teste diz quais; iguale `GAUSS_K`, `OPEN_K`, `CLOSE_K` e `OBJ_CLARO`/`BRIGHT_OBJECT` |
| `Fundo na ESP32: não` | Fundo não capturado ou placa reiniciada | `http://IP/fundo?acao=capturar` com a bandeja vazia |
| Nenhuma peça detectada | Sem fundo, peças na borda ou área menor que `MIN_AREA` | Capture o fundo, centralize as peças, revise `MIN_AREA` |
| Muitas peças falsas | Fundo capturado com algo na bandeja, ou a luz mudou | Capture o fundo de novo |
| Furos somem (Euler errado) | Fechamento grande ou câmera longe | Diminua `CLOSE_K` (nos dois lados) ou aproxime a câmera |
| `Modelo não encontrado` | Classificação antes do treino | Rode o `training_pipeline` |
| Treino avisa "divisão por foto" | Menos de 2 peças físicas em alguma classe | Fotografe mais peças diferentes dessa classe |
| E1 com 8 bits lenta no servidor | Descompressão em Python de uma imagem com muitas corridas | Esperado; aparece em `t_decompress_ms` |
| `decod.py` reclama de `PIL` | Pillow não instalado | `pip install pillow` |
