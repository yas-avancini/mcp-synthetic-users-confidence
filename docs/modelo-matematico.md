# Modelo matemático

Este documento descreve as contas que o servidor faz nesta versão. Não há um modelo único: é uma sequência de estatísticas descritivas e testes não paramétricos (bootstrap e permutação) sobre respostas numa escala ordinal de 1 a 5. O servidor não chama nenhum LLM; ele só compara as respostas sintéticas que você traz com as humanas.

> Os cortes de confiabilidade (seção 8) e as faixas de leitura da dispersão (seção 6) são **provisórios**: foram escolhidos depois de ver a primeira rodada e não foram calibrados. O desenho completo está no [PRD](specs/2026-11-26-synthetic-users-confidence-prd.md).

Notação: $s$ é o usuário sintético, $h$ são os humanos do holdout no segmento, $n_s$ e $n_h$ são os tamanhos das amostras e $K = 5$ é o número de pontos da escala.

## 1. Dados e holdout

Código: `src/synthetic_users_confidence/data.py`.

- Cada resposta vira um inteiro de 1 a 5 pela escala do dicionário. Opções fora da escala (como "Não sei") são descartadas e contadas em `cobertura`.
- **Holdout estratificado por respondente.** Para cada estrato $g$, com $n_g$ respondentes, sorteia-se sem reposição

```math
\text{round}(n_g \cdot f) \quad \text{respondentes,} \qquad f = 0{,}3,\ \text{semente } 42
```

- A comparação usa só os humanos do holdout que pertencem ao segmento. Em colunas de múltipla escolha, o respondente entra no segmento se o valor pedido está entre as opções que ele marcou.
- Com menos de **30** humanos no segmento, nada é calculado (`sem_holdout_suficiente`).

## 2. Distribuição

Com $c_k$ respostas no ponto $k$:

```math
p_k = \frac{c_k}{n}, \quad k = 1,\dots,5 \qquad
\bar{x} = \frac{1}{n}\sum_i x_i \qquad
s^2 = \frac{1}{n-1}\sum_i (x_i - \bar{x})^2
```

## 3. Distância entre sintético e humano (EMD)

Código: `metrics.emd`.

É a distância de Wasserstein-1 (Earth Mover's Distance) numa escala ordinal, normalizada para ficar entre 0 e 1. Com $F$ a distribuição acumulada:

```math
\text{EMD}(p, q) = \frac{1}{K-1} \sum_{k=1}^{K-1} \left| F_p(k) - F_q(k) \right|, \qquad F_p(k) = \sum_{j \le k} p_j
```

- 0: distribuições idênticas. 1: toda a massa em extremos opostos (tudo em 1 contra tudo em 5).
- Vale $4 \cdot \text{EMD} \ge |\bar{x}_s - \bar{x}_h|$, com igualdade quando uma distribuição domina a outra. Ou seja, a EMD capta a diferença de média e também a de formato.

### Intervalo de 95%

Código: `metrics.bootstrap_emd_ci`.

Bootstrap com $B = 1000$: reamostra com reposição os dois lados (sintético e humano), calcula a EMD e pega os percentis 2,5 e 97,5.

### Piso de ruído humano

Código: `metrics.human_noise_floor`.

É a EMD que um usuário sintético **perfeito** teria só por acaso, dado o tamanho da amostra. Com $B = 500$ sorteios, $a$ com $n_s$ respostas e $b$ com $n_h$ respostas, ambos tirados com reposição dos humanos:

```math
\text{piso} = \text{mediana}_{i=1..B}\ \text{EMD}\big(p_{a^{(i)}},\ p_{b^{(i)}}\big)
```

Uma EMD perto do piso é o melhor resultado possível com aquele número de respostas sintéticas.

## 4. Testes de significância

Código: `metrics.permutation_pvalue` e `metrics.variance_ratio_pvalue`.

Os dois testes são de permutação, com $N = 2000$ sorteios. Juntam-se as duas amostras, embaralha-se e corta-se em grupos de $n_s$ e $n_h$. Com $T$ a estatística:

```math
p = \frac{\#\{\,T_{\text{perm}} \ge T_{\text{obs}}\,\} + 1}{N + 1}
```

| Teste | Estatística $T$ | Hipótese nula |
| --- | --- | --- |
| Distribuição | $\text{EMD}(p_s, p_h)$ | sintético e humano vêm da mesma distribuição |
| Variância | $\lvert \log(s^2_s / s^2_h) \rvert$ | as duas variâncias são iguais |

No teste de variância, se um dos lados tem variância zero, a estatística vale $+\infty$.

Um p alto com poucas respostas sintéticas indica falta de poder, não fidelidade.

## 5. Variância e margens de erro

Código: `metrics.margin_of_error_mean`, `metrics.margin_of_error_proportion` e `metrics.variance_ci`.

```math
r = \frac{s^2_s}{s^2_h} \qquad
\text{ME}_{\bar{x}} = 1{,}96\,\frac{s}{\sqrt{n}} \qquad
\text{ME}_{\text{prop}} = 100 \cdot 1{,}96 \sqrt{\frac{0{,}25}{n}}\ \text{p.p.}
```

- $r$ é a razão de variância. Abaixo de 0,7, a saída avisa que pode haver **achatamento**: o usuário sintético varia bem menos que as pessoas.
- A margem da proporção é conservadora: usa o pior caso, $p = 0{,}5$.
- O intervalo de 95% da variância é um bootstrap com $B = 2000$ (percentis 2,5 e 97,5).

## 6. Sinal 1: dispersão

Código: `metrics.dispersion`. Aparece em `pontuar_resposta` e em `validar_usuario`.

```math
D = \frac{s}{(K-1)/2} = \frac{s}{2}
```

| $D$ | Leitura |
| --- | --- |
| < 0,25 | consistente |
| 0,25 a < 0,40 | moderada |
| ≥ 0,40 | dividida |

A dispersão mede a consistência do modelo, não se ele acerta. Como $s$ usa $n-1$ no denominador, $D$ pode passar de 1 em amostras muito pequenas.

## 7. Sinal 2: suporte na base

Código: `base.calibrar` e `base.sinal`.

O servidor chama o RAG da equipe e conta quantos estudos tratam do tema da pergunta. Para que "maior" sempre signifique "mais perto", scores de distância viram $-\text{score}$.

**Calibração.** Rodam-se 30 consultas placebo (temas que nenhuma pesquisa de produto trata). Para cada uma, guarda-se a proximidade do trecho mais perto, $m_j$. O corte é:

```math
c = P_{95}(m_1, \dots, m_{30})
```

**Sinal.** A busca traz até 10 trechos (top-k). Contam como relevantes os que ficam mais perto que $c$. Desses, saem os estudos marcados como holdout (se aparecerem, a saída avisa que houve vazamento). O sinal é o número de **estudos distintos** que sobram.

O sinal mede se a base trata do tema, não se ela concorda com a resposta.

## 8. Confiabilidade

Código: `confiabilidade.nivel`.

Com $\Delta = \bar{x}_s - \bar{x}_h$:

| Nível | Regra |
| --- | --- |
| Baixa | $\lvert\Delta\rvert > 0{,}5$ ou $r < 0{,}30$ |
| Alta | $\lvert\Delta\rvert < 0{,}1$ e $r \ge 0{,}70$ e "melhor que perguntar a qualquer um" e os três sinais calculados |
| Média | o resto |

O terceiro sinal do PRD (acerto histórico) ainda não existe, então o nível **nunca passa de média** nesta versão. A ausência de um sinal não conta como sinal bom.

**"Melhor que perguntar a qualquer um".** Sorteia-se, uma vez (semente 0), uma amostra de $n_s$ respostas de humanos fora do holdout, de qualquer segmento. O critério é se o usuário sintético fica mais perto do segmento do que essa amostra aleatória:

```math
\text{EMD}(p_s, p_h) < \text{EMD}(p_{\text{sorteio}}, p_h)
```

> **Limitação conhecida.** Em `validar_usuario` (`tools.py`), a comparação está sendo feita contra o próprio sintético, $\text{EMD}(p_{\text{sorteio}}, p_s)$, e não contra os humanos do segmento, como faz o experimento às cegas (`experiments/run_blind_experiment.py`). Como o critério só pesa no nível alto, que está bloqueado, os níveis atuais não mudam. O campo `melhor_que_perguntar_a_qualquer_um` do JSON, porém, pode estar errado até a correção.

### Insight em uma frase

A frase curta da tabela considera a média "parecida" quando $\lvert\Delta\rvert \le \max(\text{ME}_{\bar{x},s},\ \text{ME}_{\bar{x},h})$. Quanto à variação, lê $r < 0{,}30$ como "quase sem variação", $r < 0{,}70$ como "menos variação" e o resto como "variação parecida". A diferença é chamada de "real" quando $p < 0{,}05$ no teste de distribuição.

## Parâmetros

| Parâmetro | Valor | Onde |
| --- | --- | --- |
| Fração do holdout | 0,3 (semente 42) | `importar_dados` |
| Mínimo de humanos no segmento | 30 | `tools.MIN_HUMANS` |
| Bootstrap da EMD | 1000 | `metrics.bootstrap_emd_ci` |
| Bootstrap do piso | 500 | `metrics.human_noise_floor` |
| Permutações (cada teste) | 2000 | `metrics.permutation_pvalue`, `metrics.variance_ratio_pvalue` |
| Bootstrap da variância | 2000 | `metrics.variance_ci` |
| $z$ para 95% | 1,96 | `metrics.Z95` |
| Consultas placebo / percentil / top-k | 30 / 95 / 10 | `base.PLACEBO`, `base.PERCENTIL`, `base.TOP_K` |
| Cortes de confiabilidade | 0,5 · 0,1 · 0,30 · 0,70 | `confiabilidade.py` |
