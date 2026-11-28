# Dataset: como montar e como é guardado

Como tirar as fotos, onde elas ficam e qual o formato de cada arquivo.

> **Resumo:** fotos em tons de cinza, sem compressão, com câmera e luz fixas, uma peça por foto, várias peças físicas diferentes por classe, e o fundo vazio fotografado no começo de cada sessão.

## Sumário

1. [Montagem](#1-montagem)
2. [Ajuste da câmera](#2-ajuste-da-câmera)
3. [Sessões e fundo](#3-sessões-e-fundo)
4. [Peças físicas](#4-peças-físicas)
5. [Como tirar as fotos](#5-como-tirar-as-fotos)
6. [Estrutura das pastas](#6-estrutura-das-pastas)
7. [Formato dos arquivos](#7-formato-dos-arquivos)

---

## 1. Montagem

Faça uma vez e não mexa mais. Os modelos 3D do suporte da câmera estão em `3d_models/`.

| Item | Como fazer | Por quê |
| --- | --- | --- |
| Câmera | Fixa, perpendicular à esteira, sempre na mesma altura (anote) | Área e perímetro dependem da altura; inclinar a câmera distorce a forma |
| Luz | Difusa, de preferência vinda de vários lados (ou retroiluminação); sem luz de janela | Sombras e reflexos viram "pedaços de peça" na máscara |
| Fundo | Fosco, liso, de cor uniforme | O Otsu funciona melhor com um histograma bimodal |
| Escala (opcional) | Fotografe uma régua uma vez | Permite converter pixels para milímetros no relatório |

## 2. Ajuste da câmera

1. Rode a captura (`python -m src.server.capture_dataset`) com a peça **mais brilhante** no centro (geralmente uma peça de metal).
2. Desligue a exposição automática com **`a`** e ajuste com **`[`** e **`]`** até a peça ficar nítida **sem estourar** (sem manchas totalmente brancas).
3. Grave o valor no firmware (`init_camera()` no `inspect_objectos.ino`), para não depender de ajustar toda vez.

A exposição automática muda o brilho de uma foto para outra, e com ela o limiar e a máscara.

## 3. Sessões e fundo

Uma **sessão** é um período em que câmera, luz e exposição não mudam. O nome padrão é a data (`20261130`); passe outro com `--session`.

No início de cada sessão, com a bandeja **vazia**:

- aperte **`b`** de 5 a 10 vezes: as fotos viram o fundo do **dataset** (a média delas é usada no treinamento);
- aperte **`f`**: a ESP32 tira a média de 8 quadros e guarda o fundo **dela**, usado pela E2 (e baixado pelo servidor na E1).

Mexeu na luz, na altura ou na exposição? Comece uma **nova sessão** e fotografe o fundo de novo. Lembre também que o fundo da placa some quando ela reinicia.

## 4. Peças físicas

**Use várias peças físicas diferentes de cada classe, e não muitas fotos da mesma peça.**

- Parafusos e porcas: 8 a 10 peças diferentes (comprimentos e diâmetros variados).
- Sensor, servo e motor: todas as unidades disponíveis, idealmente 3 ou mais de cada.
- Separe as peças em potinhos numerados: o número é o **número da peça** (teclas `+`/`-`).

Esse número vai para o `metadata.csv` como `piece_id`, e o treinamento garante que **fotos da mesma peça nunca ficam no treino e no teste ao mesmo tempo**. Sem isso, o modelo "decora" a peça e a acurácia sai inflada.

## 5. Como tirar as fotos

**Meta:** 6 a 10 fotos por peça, 60 a 80 por classe, com as classes equilibradas.

Para cada peça, varie a **posição** (centro e quadrantes), a **rotação** (de 45° em 45°) e a **face** (vire a peça).

Regras:

- **Uma peça por foto** no modo individual (o script não salva se houver mais de uma).
- A peça deve ficar **inteira na imagem**, longe da borda: contorno vermelho significa peça encostada na borda.
- **Sempre na posição estável:** parafuso deitado, porca na face plana, sensor com a placa deitada, servo e motor deitados. Uma porca de lado vira um retângulo; um parafuso em pé vira um círculo.
- **Fios** do servo e do motor sempre na mesma posição (enrolados por baixo ou presos para fora do campo de visão).
- **Furos:** confira o número de Euler na tela (`E=1` sem furos, `E=0` um furo como a porca, negativo vários furos, como o sensor). Se os furos sumirem, aproxime a câmera ou diminua o `CLOSE_K`.
- Limpe poeira e fiapos do fundo.

**Fotos com várias peças:** aperte **`m`** e tire de 30 a 50 fotos com 2 a 5 peças, algumas encostadas. Elas não entram no treino; servem para testar o sistema completo.

## 6. Estrutura das pastas

Por padrão, o dataset fica em `src/data/` (ver `config.DATA_DIR`):

```
src/data/
├── raw/
│   ├── parafuso/parafuso_p03_20261130_0012.png
│   ├── porca/ ...
│   └── multi/multi_20261130_0001.png
├── background/
│   ├── background_20261130_001.png
│   └── session_20261130.json
├── processed/                  (gerado pelo treinamento)
├── metadata.csv                (gerado pela captura)
└── features.csv                (gerado pelo treinamento)
```

As fotos são salvas em **PNG, sem perdas, sem nenhuma sobreposição**. Elas são as **originais** dos experimentos de compressão: a avaliação offline gera a E1 em cada nível de bits a partir delas, então todas as estratégias são comparadas sobre as mesmas imagens.

## 7. Formato dos arquivos

### Nome das fotos

- Individual: `<classe>_p<peça>_<sessão>_<nº>.png`, por exemplo `servo_p02_20261130_0007.png`.
- Multi: `multi_<sessão>_<nº>.png`.
- Fundo: `background_<sessão>_<nº>.png`.

### `metadata.csv` (uma linha por foto)

| Coluna | Conteúdo |
| --- | --- |
| `file` | caminho da foto relativo a `raw/` |
| `label` | classe (vazio no modo multi) |
| `piece_id` | `<classe>_<nº da peça>` (vazio no modo multi) |
| `session` | sessão |
| `mode` | `individual` ou `multi` |
| `timestamp` | data e hora |
| `width`, `height` | tamanho da imagem |
| `n_pieces` | peças válidas detectadas no momento da captura |
| `threshold` | limiar de Otsu no momento da captura |

### `session_<sessão>.json`

Os ajustes do sensor naquela sessão (resposta de `/status`), útil para o relatório.

### `features.csv` (uma linha por peça, gerado pelo treinamento)

`file`, `label`, `piece_id`, `session` e os 15 descritores: `hu1` … `hu8`, `euler`, `compactness`, `eccentricity`, `elongation`, `solidity`, `area`, `perimeter`.
