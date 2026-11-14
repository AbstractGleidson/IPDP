# Inspeção de Peças com Câmera Barata

Este projeto simula uma pequena estação de inspeção. As peças (parafusos, porcas, arruelas e pregos) passam por baixo de uma câmera, e o sistema diz automaticamente o que cada uma é.

---

## A ideia

Placas como o **ESP32-CAM** e o **Raspberry Pi 5** são baratas e fáceis de encontrar, mas não têm tanto poder de processamento. Então dividimos o trabalho:

- **A câmera** tira a foto e manda pelo Wi-Fi.
- **O computador** recebe os dados e faz a parte pesada: encontra as peças na imagem, analisa o formato de cada uma e decide o que ela é.

## Como o repositório está organizado

```
IPDP/
├── edger/ # código que roda na câmera 
├── server/ # código que roda no computador
├── data/ # imagens e rótulos das peças
└── report/ # relatório 
```