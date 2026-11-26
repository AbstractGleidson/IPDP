## K-means

### 1 - Objetivo

Dados $n$ vetores $\mathbf{x}_1, \dots, \mathbf{x}_n \in \mathbb{R}^d$ e um número $k$ de grupos, o k-means procura centros $\mathbf{c}_1, \dots, \mathbf{c}_k$ e uma atribuição $a(i) \in \{1, \dots, k\}$ que minimizem a **inércia** (soma dos quadrados intra-cluster):

$$
J(\mathbf{c}, a) = \sum_{i=1}^{n} \left\lVert \mathbf{x}_i - \mathbf{c}_{a(i)} \right\rVert^2
$$

Encontrar o mínimo global é NP-difícil. O algoritmo de Lloyd encontra um mínimo local.

### 2 - Algoritmo de Lloyd

Alterna entre dois passos, cada um minimizando $J$ em relação a uma variável com a outra fixa.

**Passo de atribuição** (centros fixos): cada ponto vai para o centro mais próximo.

$$
a(i) = \arg\min_{j} \left\lVert \mathbf{x}_i - \mathbf{c}_j \right\rVert^2
$$

Isso minimiza $J$ termo a termo.

**Passo de atualização** (atribuição fixa): seja $S_j = \{i : a(i) = j\}$. A parte de $J$ que depende de $\mathbf{c}_j$ é $\sum_{i \in S_j} \lVert \mathbf{x}_i - \mathbf{c}_j \rVert^2$. Derivando e igualando a zero:

$$
\frac{\partial J}{\partial \mathbf{c}_j} = -2 \sum_{i \in S_j} (\mathbf{x}_i - \mathbf{c}_j) = 0
\quad\Rightarrow\quad
\boxed{\mathbf{c}_j = \frac{1}{|S_j|} \sum_{i \in S_j} \mathbf{x}_i}
$$

O melhor centro é a **média** dos pontos do grupo (daí o nome *k-means*).

### 3 - Convergência

Cada passo nunca aumenta $J$. Como $J \geq 0$ e só existem $k^n$ atribuições possíveis (um número finito), o algoritmo **sempre converge** em número finito de passos, para um mínimo local. Na prática, o código para quando o deslocamento total dos centros fica abaixo de uma tolerância:

$$
\sum_{j} \left\lVert \mathbf{c}_j^{(t+1)} - \mathbf{c}_j^{(t)} \right\rVert^2 \leq \text{tol}
$$

### 4 - Cálculo vetorizado das distâncias

Expandindo o quadrado da norma:

$$
\lVert \mathbf{x} - \mathbf{c} \rVert^2 = \lVert \mathbf{x} \rVert^2 - 2\,\mathbf{x}^T \mathbf{c} + \lVert \mathbf{c} \rVert^2
$$

Para todos os pares ao mesmo tempo, com $X \in \mathbb{R}^{n \times d}$ e $C \in \mathbb{R}^{k \times d}$:

$$
D = \underbrace{\operatorname{diag}(XX^T)\,\mathbf{1}^T}_{n \times k} - 2\,XC^T + \underbrace{\mathbf{1}\,\operatorname{diag}(CC^T)^T}_{n \times k}
$$

Uma multiplicação de matrizes ($XC^T$) substitui o laço sobre pares. Erros de arredondamento podem gerar valores levemente negativos, por isso o código aplica $\max(D, 0)$.

### 5 - Inicialização k-means++

O resultado do Lloyd depende muito dos centros iniciais. O **k-means++** (Arthur & Vassilvitskii, 2007) escolhe centros espalhados:

1. Escolha $\mathbf{c}_1$ uniformemente entre os pontos.
2. Para cada ponto, seja $D(\mathbf{x})$ a distância ao centro mais próximo já escolhido.
3. Escolha o próximo centro com probabilidade

$$
P(\mathbf{x}_i) = \frac{D(\mathbf{x}_i)^2}{\sum_{l} D(\mathbf{x}_l)^2}
$$

4. Repita até ter $k$ centros.

Pontos longe dos centros atuais têm mais chance de serem escolhidos. Garantia teórica: a inércia esperada após a inicialização é no máximo $O(\log k)$ vezes a ótima.

### 6 - Múltiplas execuções e clusters vazios

- Como o resultado ainda é um mínimo local, o código roda `n_init` vezes com inicializações diferentes e fica com a solução de **menor inércia**.
- Se um cluster fica vazio, a média não está definida. O código o reposiciona no ponto mais distante do seu centro atual, o ponto "pior servido", o que reduz $J$.

---

## Do agrupamento à classificação

O k-means é **não supervisionado**: não usa rótulos. Para classificar, o classificador faz três passos.

**1. Agrupa o treino** com k-means, obtendo os centros $\mathbf{c}_1, \dots, \mathbf{c}_k$.

**2. Rotula cada cluster por voto majoritário.** Com rótulos de treino $y_i$:

$$
\ell(j) = \arg\max_{c} \left|\{ i \in S_j : y_i = c \}\right|
$$

**3. Classifica uma amostra nova pelo centro mais próximo:**

$$
\hat{y}(\mathbf{x}) = \ell\!\left(\arg\min_j \lVert \mathbf{x} - \mathbf{c}_j \rVert\right)
$$

### Geometria da decisão

A regra do centro mais próximo divide o espaço em **regiões de Voronoi**. A fronteira entre os centros $\mathbf{c}_i$ e $\mathbf{c}_j$ é o conjunto de pontos equidistantes:

$$
\lVert \mathbf{x} - \mathbf{c}_i \rVert^2 = \lVert \mathbf{x} - \mathbf{c}_j \rVert^2
\;\Longleftrightarrow\;
2(\mathbf{c}_j - \mathbf{c}_i)^T \mathbf{x} = \lVert \mathbf{c}_j \rVert^2 - \lVert \mathbf{c}_i \rVert^2
$$

que é um **hiperplano** (a mediatriz do segmento entre os dois centros). Com um centro por classe, as fronteiras são lineares. Usando $k$ maior que o número de classes (vários clusters por classe), a fronteira de cada classe vira uma união de regiões de Voronoi, que é linear por partes e pode aproximar formas mais complexas.

---
