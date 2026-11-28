# Momentos Invariantes


## Sumário

1. [A imagem como distribuição de massa](#1-a-imagem-como-distribuição-de-massa)
2. [Momentos brutos](#2-momentos-brutos)
3. [Formulação matricial (Vandermonde)](#3-formulação-matricial-vandermonde)
4. [Centroide](#4-centroide)
5. [Momentos centrais: invariância à translação](#5-momentos-centrais-invariância-à-translação)
6. [Momentos normalizados: invariância à escala](#6-momentos-normalizados-invariância-à-escala)
7. [Invariância à rotação: momentos complexos](#7-invariância-à-rotação-momentos-complexos)
8. [Os invariantes de Hu e de Flusser](#8-os-invariantes-de-hu-e-de-flusser)
9. [Reflexão e independência dos invariantes](#9-reflexão-e-independência-dos-invariantes)
10. [Transformação logarítmica](#10-transformação-logarítmica)
11. [Padronização (z-score)](#11-padronização-z-score)
12. [K-means](#12-k-means)
13. [Do agrupamento à classificação](#13-do-agrupamento-à-classificação)
14. [Exemplo numérico completo](#14-exemplo-numérico-completo)
15. [Limitações práticas](#15-limitações-práticas)

---

## 1. A imagem como distribuição de massa

Uma imagem em tons de cinza é uma função $I(x, y) \geq 0$ definida numa grade de pixels, onde $x$ é a coluna (eixo horizontal) e $y$ é a linha (eixo vertical).

A ideia central é interpretar $I(x, y)$ como uma **densidade de massa**: cada pixel é uma partícula de peso $I(x,y)$. Se normalizarmos pela massa total, $I$ vira uma **distribuição de probabilidade** bidimensional. A partir daí, todas as ferramentas de estatística descritiva se aplicam:

| Estatística | Equivalente em momentos | Significado na forma |
|---|---|---|
| Massa total | $m_{00}$ | Área do objeto |
| Média | $m_{10}/m_{00},\ m_{01}/m_{00}$ | Centroide |
| Variância / covariância | $\mu_{20},\ \mu_{02},\ \mu_{11}$ | Espalhamento e orientação |
| Assimetria (*skewness*) | $\mu_{30},\ \mu_{21},\ \mu_{12},\ \mu_{03}$ | Desequilíbrio da forma |

Para que os momentos descrevam **a forma** e não a iluminação, é recomendável usar imagens binárias: $I(x,y) = 1$ no objeto e $0$ no fundo (ou 255 e 0, o que só muda um fator de escala que a normalização elimina).

---

## 2. Momentos brutos

O **momento bruto** (ou geométrico) de ordem $(p + q)$ é

$$
m_{pq} = \sum_{y=0}^{h-1} \sum_{x=0}^{w-1} x^p \, y^q \, I(x, y), \qquad p, q \in \{0, 1, 2, \dots\}
$$

No caso contínuo, a soma vira uma integral:

$$
m_{pq} = \iint x^p \, y^q \, I(x, y) \, dx \, dy
$$

Os momentos de ordem baixa têm interpretação direta:

- $m_{00} = \sum I(x,y)$ é a massa total. Em imagem binária, é a **área** (número de pixels do objeto).
- $m_{10} = \sum x \, I(x,y)$ e $m_{01} = \sum y \, I(x,y)$ são as somas das coordenadas ponderadas pela massa.

Até a ordem 3 existem 10 momentos: $m_{00}$; $m_{10}, m_{01}$; $m_{20}, m_{11}, m_{02}$; $m_{30}, m_{21}, m_{12}, m_{03}$.

**Teorema da unicidade (Hu, 1962).** Se $I$ é contínua por partes e tem suporte limitado, a sequência infinita $\{m_{pq}\}$ determina $I$ de forma única, e vice-versa. Os momentos de ordem baixa capturam a forma "grossa"; os de ordem alta, os detalhes.

---

## 3. Formulação matricial (Vandermonde)

A soma dupla pode ser escrita como um produto de matrizes. Defina as **matrizes de Vandermonde**:

$$
V_x = \begin{bmatrix}
1 & 0 & 0 & 0 \\
1 & 1 & 1 & 1 \\
1 & 2 & 4 & 8 \\
\vdots & \vdots & \vdots & \vdots \\
1 & (w-1) & (w-1)^2 & (w-1)^3
\end{bmatrix}_{w \times 4},
\qquad
V_x[x, p] = x^p
$$

e, analogamente, $V_y[y, q] = y^q$, de dimensão $h \times 4$.

Como o NumPy indexa a imagem como $I[y, x]$ (linha, coluna), a transposta $I^T$ tem $I^T[x, y] = I(x, y)$. Então:

$$
\left(V_x^T \, I^T \, V_y\right)[p, q]
= \sum_{x} \sum_{y} V_x^T[p, x] \; I^T[x, y] \; V_y[y, q]
= \sum_{x} \sum_{y} x^p \, I(x, y) \, y^q
= m_{pq}
$$

Ou seja:

$$
\boxed{M = V_x^T \, I^T \, V_y}
\qquad
\underbrace{(4 \times w)}_{V_x^T} \cdot \underbrace{(w \times h)}_{I^T} \cdot \underbrace{(h \times 4)}_{V_y} = (4 \times 4)
$$

Uma única expressão produz a matriz com **todos** os momentos até a ordem 3. O custo é $O(w \cdot h)$, o mesmo dos laços, mas executado por rotinas de álgebra linear otimizadas (BLAS) em vez de laços interpretados.

---

## 4. Centroide

O **centroide** (centro de massa) é a média das coordenadas ponderada pela massa:

$$
\bar{x} = \frac{m_{10}}{m_{00}}, \qquad \bar{y} = \frac{m_{01}}{m_{00}}
$$

Ele exige $m_{00} \neq 0$. Uma imagem toda preta não tem objeto, e o centroide não está definido.

---

## 5. Momentos centrais: invariância à translação

### 5.1 Definição

Os momentos brutos dependem da posição do objeto. Para eliminar essa dependência, medem-se as coordenadas a partir do centroide:

$$
\mu_{pq} = \sum_{y} \sum_{x} (x - \bar{x})^p \, (y - \bar{y})^q \, I(x, y)
$$

### 5.2 Prova da invariância à translação

Considere o objeto deslocado por $(t_x, t_y)$: $I'(x, y) = I(x - t_x, y - t_y)$. A massa total não muda e o centroide desloca junto: $\bar{x}' = \bar{x} + t_x$, $\bar{y}' = \bar{y} + t_y$. Fazendo a substituição $u = x - t_x$, $v = y - t_y$:

$$
\mu'_{pq}
= \sum (x - \bar{x} - t_x)^p (y - \bar{y} - t_y)^q \, I(x - t_x, y - t_y)
= \sum (u - \bar{x})^p (v - \bar{y})^q \, I(u, v)
= \mu_{pq}
$$

### 5.3 Propriedades

- $\mu_{00} = m_{00}$ (a massa não depende de onde se mede).
- $\mu_{10} = \mu_{01} = 0$ sempre, pois $\sum (x - \bar{x}) I = m_{10} - \bar{x} \, m_{00} = 0$.

### 5.4 Relação com os momentos brutos

Pelo binômio de Newton, os momentos centrais podem ser obtidos dos brutos:

$$
\mu_{pq} = \sum_{r=0}^{p} \sum_{s=0}^{q} \binom{p}{r} \binom{q}{s} (-\bar{x})^{p-r} (-\bar{y})^{q-s} \, m_{rs}
$$

Exemplos:

$$
\mu_{20} = m_{20} - \bar{x}\, m_{10}, \qquad
\mu_{11} = m_{11} - \bar{x}\, m_{01}, \qquad
\mu_{02} = m_{02} - \bar{y}\, m_{01}
$$

$$
\mu_{30} = m_{30} - 3\bar{x}\, m_{20} + 2\bar{x}^2\, m_{10}
$$

O código não usa essas fórmulas: aplica o mesmo truque de Vandermonde às coordenadas deslocadas $(x - \bar{x})$ e $(y - \bar{y})$, que é numericamente mais estável (evita subtrair números grandes e parecidos).

### 5.5 Momentos de segunda ordem: a matriz de covariância

Os momentos de ordem 2 formam a **matriz de covariância** (ou tensor de inércia) do objeto:

$$
C = \frac{1}{\mu_{00}}
\begin{bmatrix}
\mu_{20} & \mu_{11} \\
\mu_{11} & \mu_{02}
\end{bmatrix}
$$

Seus autovalores $\lambda_1 \geq \lambda_2$ são as variâncias ao longo dos eixos principais:

$$
\lambda_{1,2} = \frac{(\mu_{20} + \mu_{02}) \pm \sqrt{(\mu_{20} - \mu_{02})^2 + 4\mu_{11}^2}}{2\,\mu_{00}}
$$

Daí saem medidas clássicas de forma:

- **Orientação** do eixo maior: $\theta = \frac{1}{2} \operatorname{atan2}\!\left(2\mu_{11},\ \mu_{20} - \mu_{02}\right)$
- **Excentricidade**: $e = \sqrt{1 - \lambda_2 / \lambda_1}$ (0 para círculo, perto de 1 para formas alongadas)
- A forma pode ser aproximada por uma **elipse equivalente** com semieixos proporcionais a $\sqrt{\lambda_1}$ e $\sqrt{\lambda_2}$.

### 5.6 Momentos de terceira ordem

$\mu_{30}, \mu_{21}, \mu_{12}, \mu_{03}$ medem **assimetria**. Para uma forma simétrica em relação ao centroide (círculo, retângulo, elipse), todos os momentos centrais de ordem ímpar são zero: cada ponto $(x, y)$ tem um correspondente $(-x, -y)$ e as contribuições se cancelam.

---

## 6. Momentos normalizados: invariância à escala

### 6.1 Como os momentos centrais mudam com a escala

Amplie o objeto por um fator $s > 0$ em torno do centroide: $I'(x, y) = I(x/s, y/s)$. Com a substituição $u = x/s$, $v = y/s$ (logo $dx\,dy = s^2\, du\,dv$):

$$
\mu'_{pq}
= \iint x^p y^q \, I\!\left(\tfrac{x}{s}, \tfrac{y}{s}\right) dx\, dy
= \iint (su)^p (sv)^q \, I(u, v) \, s^2 \, du\, dv
= s^{p+q+2} \, \mu_{pq}
$$

Dois fatores aparecem: $s^{p+q}$ vem das coordenadas, e $s^2$ vem do aumento da área. Em particular:

$$
\mu'_{00} = s^2 \, \mu_{00}
$$

### 6.2 Escolha do expoente

Queremos dividir $\mu_{pq}$ por uma potência de $\mu_{00}$ que tenha exatamente o mesmo fator $s^{p+q+2}$:

$$
\left(\mu'_{00}\right)^{\gamma} = s^{2\gamma} \, \mu_{00}^{\gamma}
\quad \Rightarrow \quad
2\gamma = p + q + 2
\quad \Rightarrow \quad
\boxed{\gamma = \frac{p + q}{2} + 1}
$$

### 6.3 Definição

$$
\nu_{pq} = \frac{\mu_{pq}}{\mu_{00}^{\gamma}}, \qquad \gamma = \frac{p+q}{2} + 1
$$

Verificação:

$$
\nu'_{pq} = \frac{s^{p+q+2}\, \mu_{pq}}{s^{p+q+2}\, \mu_{00}^{\gamma}} = \nu_{pq}
$$

Os $\nu_{pq}$ são invariantes à **translação e à escala**. Para $p + q < 2$ são triviais: $\nu_{00} = 1$ e $\nu_{10} = \nu_{01} = 0$. Por isso apenas os de ordem $\geq 2$ carregam informação.

**Bônus:** a mesma normalização elimina um fator de intensidade. Se $I' = \alpha I$, então $\mu'_{pq} = \alpha\,\mu_{pq}$ e $\mu'_{00} = \alpha\,\mu_{00}$; como $\gamma > 1$ para $p+q \geq 2$, sobra $\alpha^{1-\gamma}$. Logo, a invariância a intensidade **não** é total; por isso imagens binárias com valor fixo são o caso ideal.

### 6.4 Matriz de expoentes

Para $p, q \in \{0, 1, 2, 3\}$:

$$
\Gamma = \begin{bmatrix}
1.0 & 1.5 & 2.0 & 2.5 \\
1.5 & 2.0 & 2.5 & 3.0 \\
2.0 & 2.5 & 3.0 & 3.5 \\
2.5 & 3.0 & 3.5 & 4.0
\end{bmatrix}
\qquad
\Gamma[p, q] = \frac{p+q}{2} + 1
$$

e a normalização inteira é a divisão elemento a elemento $N = \mathcal{M} \oslash \mu_{00}^{\,\Gamma}$.

---

## 7. Invariância à rotação: momentos complexos

### 7.1 O problema

Uma rotação por $\theta$ em torno do centroide mistura as coordenadas:

$$
\begin{bmatrix} x' \\ y' \end{bmatrix} =
\begin{bmatrix} \cos\theta & -\sin\theta \\ \sin\theta & \cos\theta \end{bmatrix}
\begin{bmatrix} x \\ y \end{bmatrix}
$$

e, portanto, mistura os momentos de mesma ordem entre si. Os $\nu_{pq}$ individuais **não** são invariantes à rotação. É preciso encontrar combinações deles que sejam.

### 7.2 Caso de ordem 2: traço e determinante

A matriz de covariância transforma-se como $C' = R\, C\, R^T$. Matrizes semelhantes têm os mesmos autovalores, portanto o **traço** e o **determinante** não mudam:

$$
\operatorname{tr}(C) = \lambda_1 + \lambda_2 \propto \nu_{20} + \nu_{02}
$$

$$
\operatorname{tr}(C)^2 - 4 \det(C) = (\lambda_1 - \lambda_2)^2 \propto (\nu_{20} - \nu_{02})^2 + 4\nu_{11}^2
$$

Estes são exatamente $I_1$ e $I_2$. Para a ordem 3, porém, essa abordagem matricial fica complicada. A ferramenta certa são os números complexos.

### 7.3 Momentos complexos

Identifique cada ponto do plano com um número complexo $z = x + iy$. Defina os **momentos complexos** (usando coordenadas centradas e normalizadas):

$$
c_{pq} = \sum (x + iy)^p \, (x - iy)^q \, I(x, y) = \sum z^p \, \bar{z}^{\,q} \, I(z)
$$

### 7.4 Propriedade fundamental

Uma rotação por $\theta$ é simplesmente a multiplicação $z' = z\, e^{i\theta}$, e $\bar{z}' = \bar{z}\, e^{-i\theta}$. Para o objeto rotacionado, $I'(z') = I(z)$, logo:

$$
c'_{pq} = \sum (z\,e^{i\theta})^p \, (\bar{z}\,e^{-i\theta})^q \, I(z)
= e^{i(p-q)\theta} \sum z^p \bar{z}^{\,q} I(z)
$$

$$
\boxed{c'_{pq} = e^{i(p-q)\theta} \, c_{pq}}
$$

A rotação **só altera a fase** de $c_{pq}$, nunca o módulo. Isso dá duas receitas para construir invariantes:

1. **Módulo:** $|c_{pq}|$ é invariante, porque $|e^{i\phi}| = 1$.
2. **Produtos com fases que se cancelam:** um produto $\prod_j c_{p_j q_j}^{k_j}$ é invariante se $\sum_j k_j (p_j - q_j) = 0$. Conjugar um momento inverte o sinal de $(p - q)$, já que $\bar{c}_{pq} = c_{qp}$ para $I$ real.

### 7.5 Expansão em partes real e imaginária

Expandindo as potências de $z = x + iy$ e trocando somas de monômios por momentos $\nu$:

**$c_{11}$** (fase $e^{0}$):

$$
z\bar{z} = x^2 + y^2 \quad\Rightarrow\quad c_{11} = \nu_{20} + \nu_{02}
$$

**$c_{20}$** (fase $e^{2i\theta}$):

$$
z^2 = (x^2 - y^2) + i\,2xy \quad\Rightarrow\quad c_{20} = (\nu_{20} - \nu_{02}) + i\,2\nu_{11}
$$

**$c_{21}$** (fase $e^{i\theta}$):

$$
z^2\bar{z} = z\,(x^2+y^2) = (x^3 + xy^2) + i\,(x^2 y + y^3)
\quad\Rightarrow\quad c_{21} = \underbrace{(\nu_{30} + \nu_{12})}_{a} + i\,\underbrace{(\nu_{21} + \nu_{03})}_{b}
$$

**$c_{30}$** (fase $e^{3i\theta}$):

$$
z^3 = (x^3 - 3xy^2) + i\,(3x^2 y - y^3)
\quad\Rightarrow\quad c_{30} = \underbrace{(\nu_{30} - 3\nu_{12})}_{c} + i\,\underbrace{(3\nu_{21} - \nu_{03})}_{d}
$$

Resumo, com as variáveis auxiliares usadas no código:

| Momento complexo | Parte real | Parte imaginária | Fase sob rotação |
|---|---|---|---|
| $c_{11}$ | $\nu_{20} + \nu_{02}$ | $0$ | $1$ |
| $c_{20}$ | $e = \nu_{20} - \nu_{02}$ | $2\nu_{11}$ | $e^{2i\theta}$ |
| $c_{21}$ | $a = \nu_{30} + \nu_{12}$ | $b = \nu_{21} + \nu_{03}$ | $e^{i\theta}$ |
| $c_{30}$ | $c = \nu_{30} - 3\nu_{12}$ | $d = 3\nu_{21} - \nu_{03}$ | $e^{3i\theta}$ |

---

## 8. Os invariantes de Hu e de Flusser

Com a tabela acima, cada invariante é um módulo ou um produto com fase total zero.

### $I_1$: módulo de $c_{11}$

$$
I_1 = c_{11} = \nu_{20} + \nu_{02}
$$

Momento de inércia polar em torno do centroide; proporcional a $\lambda_1 + \lambda_2$. Mede o quanto a massa está espalhada, sem levar em conta a direção.

### $I_2$: módulo ao quadrado de $c_{20}$

$$
I_2 = |c_{20}|^2 = (\nu_{20} - \nu_{02})^2 + 4\nu_{11}^2
$$

Proporcional a $(\lambda_1 - \lambda_2)^2$. Mede **alongamento**: é zero para formas com simetria rotacional (círculo, quadrado) e cresce para formas alongadas.

### $I_3$: módulo ao quadrado de $c_{30}$

$$
I_3 = |c_{30}|^2 = c^2 + d^2 = (\nu_{30} - 3\nu_{12})^2 + (3\nu_{21} - \nu_{03})^2
$$

### $I_4$: módulo ao quadrado de $c_{21}$

$$
I_4 = |c_{21}|^2 = a^2 + b^2 = (\nu_{30} + \nu_{12})^2 + (\nu_{21} + \nu_{03})^2
$$

### $I_5$ e $I_7$: produto $c_{30}\,\bar{c}_{21}^{\,3}$

Fase total: $3\theta + 3 \cdot (-\theta) = 0$. Logo o produto é invariante, e suas partes real e imaginária também. Expandindo:

$$
\bar{c}_{21}^{\,3} = (a - ib)^3 = (a^3 - 3ab^2) - i\,(3a^2 b - b^3)
$$

$$
c_{30}\,\bar{c}_{21}^{\,3} = (c + id)\left[(a^3 - 3ab^2) - i\,(3a^2 b - b^3)\right]
$$

Parte real:

$$
I_5 = \operatorname{Re}\!\left(c_{30}\,\bar{c}_{21}^{\,3}\right)
= c\,a\,(a^2 - 3b^2) + d\,b\,(3a^2 - b^2)
$$

Parte imaginária:

$$
I_7 = \operatorname{Im}\!\left(c_{30}\,\bar{c}_{21}^{\,3}\right)
= d\,a\,(a^2 - 3b^2) - c\,b\,(3a^2 - b^2)
$$

### $I_6$ e $I_8$: produto $c_{20}\,\bar{c}_{21}^{\,2}$

Fase total: $2\theta + 2 \cdot (-\theta) = 0$. Expandindo, com $e = \nu_{20} - \nu_{02}$:

$$
\bar{c}_{21}^{\,2} = (a - ib)^2 = (a^2 - b^2) - i\,2ab
$$

$$
c_{20}\,\bar{c}_{21}^{\,2} = (e + i\,2\nu_{11})\left[(a^2 - b^2) - i\,2ab\right]
$$

Parte real:

$$
I_6 = \operatorname{Re}\!\left(c_{20}\,\bar{c}_{21}^{\,2}\right)
= (\nu_{20} - \nu_{02})(a^2 - b^2) + 4\nu_{11}\,a\,b
$$

Parte imaginária (dividida por 2, o que não afeta a invariância):

$$
I_8 = \tfrac{1}{2}\operatorname{Im}\!\left(c_{20}\,\bar{c}_{21}^{\,2}\right)
= \nu_{11}(a^2 - b^2) - (\nu_{20} - \nu_{02})\,a\,b
$$

### Resumo

| Invariante | Construção complexa | Fórmula em $\nu$ |
|---|---|---|
| $I_1$ | $c_{11}$ | $\nu_{20} + \nu_{02}$ |
| $I_2$ | $\lvert c_{20}\rvert^2$ | $(\nu_{20} - \nu_{02})^2 + 4\nu_{11}^2$ |
| $I_3$ | $\lvert c_{30}\rvert^2$ | $c^2 + d^2$ |
| $I_4$ | $\lvert c_{21}\rvert^2$ | $a^2 + b^2$ |
| $I_5$ | $\operatorname{Re}(c_{30}\bar{c}_{21}^3)$ | $ca(a^2 - 3b^2) + db(3a^2 - b^2)$ |
| $I_6$ | $\operatorname{Re}(c_{20}\bar{c}_{21}^2)$ | $(\nu_{20}-\nu_{02})(a^2 - b^2) + 4\nu_{11}ab$ |
| $I_7$ | $\operatorname{Im}(c_{30}\bar{c}_{21}^3)$ | $da(a^2 - 3b^2) - cb(3a^2 - b^2)$ |
| $I_8$ | $\tfrac12\operatorname{Im}(c_{20}\bar{c}_{21}^2)$ | $\nu_{11}(a^2 - b^2) - (\nu_{20}-\nu_{02})ab$ |

$I_1$ a $I_7$ são os invariantes propostos por Hu (1962). $I_8$ foi acrescentado por Flusser (2000).

---

## 9. Reflexão e independência dos invariantes

### 9.1 Comportamento sob reflexão

Uma reflexão no eixo $x$ é $y \to -y$, ou seja, $z \to \bar{z}$. Para $I$ real, isso leva $c_{pq} \to c_{qp} = \overline{c_{pq}}$: **todo momento complexo vira seu conjugado**.

Consequências:

- Módulos e partes reais não mudam: $I_1, \dots, I_6$ são invariantes também à reflexão.
- Partes imaginárias trocam de sinal: **$I_7$ e $I_8$ mudam de sinal** quando a imagem é espelhada.

Por isso $I_7$ e $I_8$ são chamados *pseudo-invariantes* (ou *skew invariants*). Isso é útil: o módulo deles é invariante a reflexão, e o sinal distingue um objeto da sua imagem espelhada (por exemplo, "b" de "d"). Se o espelhamento não deve importar na sua aplicação, use $|I_7|$ e $|I_8|$.

### 9.2 Independência

Flusser (2000) mostrou que o conjunto de Hu tem um problema duplo:

- **$I_3$ é dependente** dos outros. Ele pode ser escrito como

$$
I_3 = \frac{I_5^2 + I_7^2}{I_4^3}
$$

  o que se verifica direto pelos módulos: $|c_{30}\bar{c}_{21}^3|^2 = |c_{30}|^2 |c_{21}|^6$, ou seja, $I_5^2 + I_7^2 = I_3 \, I_4^3$.

- **Falta um invariante** de ordem 3 para completar a base: $I_8$.

O conjunto $\{I_1, I_2, I_4, I_5, I_6, I_7, I_8\}$ é **independente e completo** até a ordem 3: qualquer outro invariante à rotação construído com momentos de ordem $\leq 3$ pode ser expresso em função deles.

---

## 10. Transformação logarítmica

### 10.1 O problema da escala

Os invariantes têm ordens de grandeza muito diferentes, porque envolvem produtos de vários $\nu$, que são números pequenos:

| Invariante | Grau em $\nu$ | Ordem típica |
|---|---|---|
| $I_1$ | 1 | $10^{-1}$ |
| $I_2$ | 2 | $10^{-2}$ a $10^{-4}$ |
| $I_3, I_4$ | 2 | $10^{-3}$ a $10^{-8}$ |
| $I_6, I_8$ | 3 | $10^{-6}$ a $10^{-12}$ |
| $I_5, I_7$ | 4 | $10^{-8}$ a $10^{-20}$ |

Numa distância euclidiana, só $I_1$ teria peso; os demais seriam invisíveis.

### 10.2 A transformação

$$
h' = -\operatorname{sign}(h) \cdot \log_{10}\!\left(|h| + \varepsilon\right), \qquad \varepsilon = 10^{-30}
$$

- $\log_{10}|h|$ **comprime** as ordens de grandeza: $10^{-2} \mapsto -2$, $10^{-20} \mapsto -20$. Agora todos os valores estão numa escala comparável.
- $\operatorname{sign}(h)$ **preserva o sinal**, que carrega informação (especialmente em $I_7$ e $I_8$).
- O sinal negativo da frente apenas torna os valores positivos na maioria dos casos.
- $\varepsilon$ evita $\log(0)$.

### 10.3 O efeito colateral: amplificação de ruído perto de zero

A derivada de $\log|h|$ é $1/h$, que explode quando $h \to 0$. Para formas simétricas, os invariantes de ordem 3 deveriam ser exatamente zero, mas a discretização em pixels produz valores minúsculos e aleatórios (ex.: $10^{-18}$ numa imagem, $10^{-22}$ em outra). O log transforma essa diferença irrelevante em uma diferença de 4 unidades, do mesmo tamanho das diferenças reais entre formas.

**Regra prática:** se as classes têm formas simétricas, os invariantes de ordem 3 tendem a virar ruído após o log. Teste subconjuntos ($I_1, I_2$ ou $I_1$ a $I_4$) e escolha pela acurácia de validação.

---

## 11. Padronização (z-score)

Mesmo após o log, cada característica tem média e dispersão próprias. O k-means usa distância euclidiana, que dá mais peso às características com maior variância. A padronização coloca todas em pé de igualdade:

$$
z_j = \frac{x_j - \bar{x}_j}{\sigma_j}
$$

onde $\bar{x}_j$ e $\sigma_j$ são a média e o desvio padrão da característica $j$, **calculados apenas no conjunto de treino** e reaplicados no teste (para não vazar informação do teste para o modelo).

Após a padronização, cada característica tem média 0 e variância 1 no treino.