# synthetic-users-confidence

Servidor MCP que mede quão fiéis são usuários sintéticos a pessoas reais. O desenho completo está no [PRD](docs/specs/2026-11-26-synthetic-users-confidence-prd.md).

> **Status: esqueleto.** Três ferramentas funcionam e o terceiro sinal de confiança ainda não existe. Não use os resultados como evidência.

## Como funciona nesta versão

Você traz as respostas sintéticas já coletadas; o servidor não chama nenhum LLM. Ele compara com as respostas humanas do holdout de qualquer pesquisa em CSV (veja [Importar seus dados](#importar-seus-dados)). O exemplo pronto usa a [Stack Overflow Developer Survey 2025](https://survey.stackoverflow.co/) (ODbL 1.0).

| Ferramenta | O que faz |
| --- | --- |
| `conectar_base` | Conecta o RAG que a equipe já tem para calcular o sinal de suporte na base (veja abaixo) |
| `importar_dados` | Lê o CSV humano com um dicionário do questionário e separa o holdout por respondente, estratificado pelas colunas que você escolher |
| `amostrar` | Contagens, média e variância das respostas sintéticas |
| `pontuar_resposta` | Sinais de confiança separados, com margem de erro (95%); o que não foi calculado vem com `status` e motivo |
| `validar_usuario` | Distância entre o usuário e os humanos do segmento, com intervalo de 95%, piso de ruído humano, razão de variância, margem de erro (média, proporção e variância) e p-value (distribuição e variância) |

Perguntas suportadas: as do dicionário importado. Sem dicionário, valem `AIAcc` (confiança na precisão da IA) e `AISent` (sentimento sobre IA), da Stack Overflow.

## Rodar

```bash
uv venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest
./scripts/download_stackoverflow_2025.sh data/stackoverflow-2025
npx @modelcontextprotocol/inspector .venv/bin/synthetic-users-confidence
```

Instalar no Claude Code:

```bash
claude mcp add synthetic-users-confidence -- "$(pwd)/.venv/bin/synthetic-users-confidence"
```

## Importar seus dados

O CSV precisa ter **uma linha por respondente** e uma coluna por pergunta. Um dicionário (objeto ou arquivo `.json`) diz quais colunas são perguntas e a ordem das opções:

```json
{
  "nome": "pesquisa-ia-2026",
  "id": "respondente",
  "estratos": ["cargo", "faixa_etaria"],
  "separador_multiplo": ";",
  "perguntas": {
    "confia_ia": {
      "texto": "Quanto você confia nas respostas da IA?",
      "rotulo": "Confiança na IA",
      "escala": {"Discordo totalmente": 1, "Discordo": 2, "Neutro": 3, "Concordo": 4, "Concordo totalmente": 5}
    }
  }
}
```

- **Sem dicionário**, `importar_dados` devolve `precisa_dicionario` com as colunas, as opções mais comuns de cada uma e um rascunho (`sugestao`). O agente confirma com você a ordem de cada escala e chama de novo com `dicionario`.
- **Privacidade na detecção:** colunas com mais de 12 opções (texto livre, ids, números) não têm os valores lidos, e uma opção só aparece se pelo menos 5 respondentes a deram. Nomes e valores raros não vão para o agente.
- **Escala de 5 pontos:** a régua de confiabilidade foi definida em pontos de uma escala de 1 a 5, então cada pergunta precisa usar os 5 pontos. Opções fora da escala (como "Não sei") são ignoradas e contadas em `cobertura`.
- **Estratos** definem o sorteio do holdout e podem ser usados como `segmento` em `validar_usuario`. Em colunas de múltipla escolha, as opções são separadas por `separador_multiplo`.
- A saída avisa quando uma opção da escala não aparece no CSV (nome digitado diferente) e recusa ids repetidos.

## Conectar a base de conhecimento (RAG)

O servidor não indexa documentos: chama o RAG que a equipe já tem, por HTTP, e calcula o sinal **suporte na base** (quantos estudos tratam do tema da pergunta). Desenho completo na [spec](docs/specs/2026-11-27-conexao-base-spec.md).

1. Instale com a chave numa variável de ambiente (ela nunca vai como argumento de ferramenta):
   ```bash
   claude mcp add synthetic-users-confidence -e SUC_RAG_TOKEN=SUA_CHAVE -- "$(pwd)/.venv/bin/synthetic-users-confidence"
   ```
   Sem a variável, num cliente que aceite elicitation por URL, `conectar_base` abre uma página local de uso único para colar a chave (com `pip install -e ".[cofre]"`, ela fica no cofre do sistema).
2. Peça ao agente: "conecte a base em `https://.../search`". `conectar_base` faz uma busca de teste, lê só os **nomes** dos campos da resposta e pergunta, por formulário, onde estão o texto, o score, o estudo e a data, e quais estudos são do holdout. Sem formulário, devolve `campos_detectados` e `sugestao` para o agente perguntar no chat e chamar de novo com `campos`.
3. O corte de relevância é calibrado nesta base com 30 consultas placebo (temas que nenhuma pesquisa de produto trata): conta como relevante o trecho mais perto que o percentil 95 delas.

A configuração fica em `~/.config/synthetic-users-confidence/conexao.json` (ou em `SUC_CONEXAO`), sem segredos, e o hash dela sai em todo sinal. Por padrão, a saída traz só id, estudo, data e score dos trechos; `incluir_texto=true` traz o texto. Estudos marcados como holdout não entram na contagem, e a saída avisa se aparecerem.

## Formato da saída

`validar_usuario` devolve por padrão um resumo em markdown que começa pelo rótulo "sintético" e pela **confiabilidade** (baixa, média ou alta), seguido de uma tabela desenhada com bordas (cerca de 100 colunas):

| Coluna | O que mostra |
| --- | --- |
| Pergunta | Nome curto da pergunta (`AIAcc` é "Acurácia da IA"; `AISent` é "Opinião sobre IA"); o texto original vem logo abaixo |
| Confiab. | Confiabilidade: baixa, média ou alta |
| Média sint. / real | Média do usuário sintético contra a das pessoas reais (o baseline, o holdout) |
| Variação sint. / real | Variância das respostas dos dois lados |
| Signif. | p-value com 95% de confiança; abaixo de 0,01 aparece `p<0,01` |
| Insight | Frase curta sobre por que a confiabilidade ficou nesse nível |

Depois da tabela vêm o que **não foi calculado** (suporte na base e acerto histórico, com o motivo) e a regra do nível. Passe `formato="json"` para o JSON completo, que traz o campo `confiabilidade` (nível, insight, sinais, regra e limite).

O nível é **provisório**: os cortes foram escolhidos depois de ver a primeira rodada e não foram calibrados. Sem os três sinais do PRD calculados, ele não passa de média. `pontuar_resposta` continua devolvendo a tabela de dispersão, sem humanos para comparar.

## Insight em linguagem simples

`pontuar_resposta` e `validar_usuario` trazem o campo `insight` no JSON: um parágrafo sem jargão estatístico que diz o que o resultado quer dizer e o que ele não prova. Na tabela de `validar_usuario`, o insight é a versão curta sobre a confiabilidade.

## Experimento às cegas

Para testar o método sem viés, `experiments/run_blind_experiment.py` gera os usuários sintéticos com `claude -p` (uma chamada isolada por resposta, em pasta vazia, sem ferramentas, memória nem configurações) e **sem nunca ver os dados humanos**. A configuração pré-registrada fica em `experiments/stackoverflow-2025-blind.json`; o hash dela é gravado em cada resposta e a análise recusa se ela mudar.

```bash
./scripts/download_stackoverflow_2025.sh data/stackoverflow-2025
python experiments/run_blind_experiment.py generate --config experiments/stackoverflow-2025-blind.json --out runs/blind
python experiments/run_blind_experiment.py analyze  --config experiments/stackoverflow-2025-blind.json --out runs/blind --csv data/stackoverflow-2025/results.csv
```

`--limite N` faz um teste rápido com N respostas por célula. A geração é retomável. A análise compara cada célula com duas referências: respostas sorteadas de qualquer idade ("melhor que perguntar a qualquer um?") e o usuário sintético de outro grupo ("melhor que usar outro grupo?"). Não são o baseline humano (test-retest) nem o placebo descritos no PRD, que ainda não existem aqui. Mostra o primeiro dos três sinais do PRD (dispersão) e um **nível de confiança provisório** (baixa, média, alta) por grupo. Os dois outros sinais (suporte na base e acerto histórico) não são calculados, então o nível não passa de média. Os cortes do nível foram escolhidos depois de ver a primeira rodada e não foram calibrados; o critério de aprovação do experimento é o pré-registrado. O resultado sai em `resultado.md` e `resultado.json` dentro da pasta `--out`; o Holm aparece no JSON. Consome o uso do seu Claude Code.

## Limites conhecidos

- Sem checagem de dados pessoais: use só dados já anonimizados.
- Só escalas de 5 pontos; outras escalas precisam de uma régua calibrada para elas.
- Formato largo (uma linha por respondente); dados em formato longo precisam ser pivotados antes.
- O suporte na base mede se a base trata do tema, não se concorda com a resposta.
- Só o adaptador `http` existe; NotebookLM e RAGs sem API de busca não se conectam.
- As faixas de leitura da dispersão são provisórias, a calibrar na etapa 2 da validação.
- Não há teste de sensibilidade a prompt nem placebo ainda.
