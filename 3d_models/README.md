# Suporte da ESP32-CAM para a Modular Conveyor (3Core)

Suporte **independente** para a câmera ficar a 300 mm da correia, centralizada sobre a esteira. Não altera nenhum arquivo da esteira original, que tem licença de uso pessoal e não pode ser redistribuída. Imprimam a esteira pelo MakerWorld ou Printables e este suporte à parte.

![Montagem](montagem_suporte.png)

## Peças

| Arquivo | Quantidade | Observação |
| --- | --- | --- |
| `base_suporte.stl` | 1 | Fica ao lado da esteira; a língua fina (3 mm) entra por baixo dela |
| `segmento_coluna.stl` | 4 | Encaixam um no outro; travar com parafuso M3 × 30 e porca |
| `braco_camera.stl` | 1 | Colar deslizante + berço da ESP32-CAM, lente para baixo |

Ferragens: 4 parafusos M3 × 30 com porca (pinos da coluna), 1 M3 × 16 (aperto do colar), abraçadeiras de nylon e, opcionalmente, 4 parafusos para madeira para fixar a base numa tábua.

## Antes de imprimir

Meça na esteira já impressa e ajuste no topo do `.scad`:

- `ESTEIRA_TOPO`: altura da superfície da correia acima da mesa;
- `VAO_SOB`: vão livre por baixo da esteira (a língua tem 3 mm e precisa passar ali);
- `ESTEIRA_L`, se usar o gerador paramétrico com outra largura.

Também confiram as medidas da ESP32-CAM (`PLACA_W`, `PLACA_L`, `CAM_OFF`).

## Montagem

1. Encaixe a língua da base por baixo da esteira, no meio de um módulo. O peso da esteira já segura a base; para mais firmeza, parafuse as duas numa tábua.
2. Encaixe os 4 segmentos da coluna e trave cada junta com um parafuso M3 × 30.
3. Deslize o braço até a lente ficar a 300 mm da correia e aperte o parafuso do colar.
4. Prenda a ESP32-CAM no berço com abraçadeiras, lente para baixo.
