# Spec — conexão com a base de conhecimento da equipe (RAG)

Nov 27, 2026 · @Yas Avancini · **Rascunho para decisão**

## Problema

O PRD pede três sinais de confiança por resposta, e o segundo é o **suporte na base de conhecimento**: quantos estudos da equipe sustentam a resposta e quão próximos eles estão da pergunta. Esse sinal é P0. O que ficou fora do MVP foi um RAG **próprio**: o projeto não indexa documentos nem constrói busca, só se conecta ao RAG que a equipe já tem, com as pesquisas e os insumos dela.

Hoje o código devolve `"exige RAG, previsto para depois do MVP"` no `suporte_na_base` (`tools.py`, em `pontuar_resposta` e `validar_usuario`) e o README repete isso. A frase está errada e sai nesta mudança.

**Decisão de 27/11/2026:** o servidor MCP chama o RAG da equipe diretamente (opção B). A alternativa, em que o agente da IDE consulta o RAG e repassa os trechos, foi descartada porque deixa o agente escolher o que entra no sinal e porque exige que o RAG esteja ligado na IDE.

## Decisão que o sinal responde

"A base de pesquisas da equipe trata do tema desta pergunta, para este grupo?" O erro mais caro é dizer que há suporte quando não há: a resposta sintética parece ancorada em pesquisa e não está. Na dúvida, o sinal diz "sem suporte encontrado".

**Limite que não sai do campo `limite`:** a busca mede se a base **fala do tema**, não se **concorda** com a resposta sintética. Um estudo que contradiz o usuário sintético conta como trecho relevante. Detectar concordância exige um LLM julgando os trechos e fica para uma próxima spec.

## Arquitetura

```
IDE (Claude Code, Cursor, VS Code)
  └─ servidor synthetic-users-confidence (local, stdio)
       ├─ conexao.json  ← configuração sem segredos, com hash
       ├─ credencial    ← variável de ambiente ou cofre do sistema (keychain)
       └─ adaptador ──HTTPS──► RAG da equipe
```

**Adaptador.** Interface única, para a comunidade contribuir com outros:

```python
class Adaptador(Protocol):
    def buscar(self, consulta: str, top_k: int) -> list[Trecho]: ...

@dataclass
class Trecho:
    id: str
    estudo: str | None
    data: str | None
    fonte: str | None
    score: float
    texto: str
```

O MVP traz só o adaptador `http`, genérico e configurado por arquivo. Adaptadores dedicados (Qdrant, pgvector, Pinecone, Elasticsearch/OpenSearch) e um adaptador `mcp`, em que o nosso servidor age como cliente do MCP do RAG, ficam como contribuições. O PRD já prevê conectores como porta de entrada da comunidade.

## Configuração (`conexao.json`)

```json
{
  "nome": "pesquisas-equipe",
  "adaptador": "http",
  "url": "https://rag.exemplo.com/api/search",
  "metodo": "POST",
  "autenticacao": { "tipo": "bearer", "variavel": "SUC_RAG_TOKEN" },
  "requisicao": { "query": "{consulta}", "top_k": "{top_k}" },
  "resposta": {
    "lista": "results",
    "id": "id",
    "texto": "text",
    "score": "score",
    "estudo": "metadata.study_id",
    "data": "metadata.date",
    "fonte": "metadata.source"
  },
  "score": { "tipo": "similaridade" },
  "consulta_modelo": "{texto_da_pergunta}",
  "top_k": 10,
  "estudos_holdout": ["estudo-07"],
  "calibracao": { "corte": 0.62, "consultas_placebo": 30, "percentil": 95, "feita_em": "2026-11-27" }
}
```

- **Segredo nunca entra no arquivo nem nos argumentos das ferramentas**, porque os argumentos passam pelo LLM. `autenticacao` aceita só `variavel` (nome da variável de ambiente) ou `cofre` (chave no keychain). O servidor recusa um arquivo com um campo `valor`, `token` ou `senha`.
- Os caminhos de `resposta` usam ponto (`metadata.study_id`), sem dependência nova.
- `score.tipo` é `similaridade` (maior é mais perto) ou `distancia` (menor é mais perto). O servidor converte tudo para "maior é mais perto".
- O hash do arquivo entra em toda saída do sinal, como no experimento às cegas: dá para saber com qual configuração o número saiu.

## Como o MCP pede a conexão ao usuário

Nova ferramenta `conectar_base(url: str | None, caminho_config: str | None)`. O fluxo:

1. **Credencial.** Se a variável de ambiente ou a chave do cofre não existir, o servidor usa **elicitation por URL** (`ctx.elicit_url`): abre uma página local em `127.0.0.1`, numa porta aleatória e com token de uso único, onde a pessoa cola a chave. A chave vai para o keychain (pacote `keyring`, como dependência opcional) e nunca passa pelo LLM. A especificação do MCP proíbe pedir segredo por formulário, então isso não usa `ctx.elicit`.
2. **Teste de conexão.** O servidor faz uma busca de teste e lista os **nomes** dos campos que vieram na resposta, sem o conteúdo.
3. **Mapeamento.** Por **elicitation de formulário** (`ctx.elicit`), pede o que não dá para adivinhar, com os campos detectados como opções: qual é a lista de resultados, qual é o texto, o score, o identificador do estudo e a data, se o score é similaridade ou distância, e quais estudos são holdout.
4. **Calibração** (abaixo) e gravação do `conexao.json` com hash.

**Plano B, obrigatório.** O suporte a elicitation varia por cliente, e um cliente agente pode responder o formulário sozinho. Se o cliente não aceitar elicitation, ou se a pessoa recusar, a ferramenta devolve `status: precisa_configuracao` com o que falta e o comando de exemplo (`claude mcp add ... -e SUC_RAG_TOKEN=...`). O agente pergunta no chat e chama `conectar_base(caminho_config=...)` com o arquivo preenchido. O fluxo tem que funcionar do começo ao fim só com arquivo e variável de ambiente.

## O sinal `suporte_na_base`

**Consulta.** Sai do `consulta_modelo`. O padrão é só o texto da pergunta; `{segmento}` é opcional. É fixa por configuração: a mesma pergunta sempre gera a mesma consulta. A consulta usada volta no JSON, para auditoria.

*Ajuste de 27/11/2026:* o padrão era `{texto_da_pergunta} Público: {segmento}`. No teste com 5 entrevistas de discovery de produto, palavras do segmento como "marketing" casam com quase todo trecho de uma base de pesquisa de produto e inflam o sinal; o segmento saiu do padrão.

**Corte de relevância, calibrado por base.** O RAG sempre devolve `top_k` trechos, mesmo sem nada relevante, então contar trechos sem corte não diz nada. E o score de uma ferramenta não se compara com o de outra, então um corte fixo também não serve. A proposta é calibrar o corte em cada base, com **consultas placebo**: uma lista fixa, versionada no repositório, de 30 consultas sobre temas que nenhuma pesquisa de produto trata (por exemplo, "receita de bolo de cenoura" ou "regras do críquete"). O corte é o percentil 95 do melhor score de cada consulta placebo. Por construção, uma consulta fora do tema passa do corte em cerca de 5% das vezes.

**Saída**

```json
"suporte_na_base": {
  "status": "ok",
  "estudos_distintos": 2,
  "estudos": ["estudo-03", "estudo-05"],
  "trechos_relevantes": 4,
  "score_maximo": 0.78,
  "corte": 0.62,
  "consulta": "How much do you trust the accuracy of the output from AI tools ...",
  "estudos_holdout_recuperados": [],
  "conexao": { "nome": "pesquisas-equipe", "hash": "a1b2c3" },
  "trechos": [{ "id": "t-91", "estudo": "estudo-03", "data": "2026-05", "score": 0.78 }],
  "limite": "mede se a base trata do tema, não se concorda com a resposta; score não comparável entre ferramentas; corte calibrado com consultas placebo nesta base"
}
```

- **Texto dos trechos fora da saída por padrão.** Só id, estudo, data e score. O texto vem com `incluir_texto=true`. Isso reduz o que vai para o contexto do LLM, que é o único terceiro que o PRD admite.
- **Sem conexão configurada:** `status: nao_configurado`, com o motivo "rode conectar_base". Se o RAG falhar (timeout, 401, 5xx): `status: erro_conexao`, com o código. Nunca zerado nem omitido.
- **Timeout** de 10 s, TLS verificado e nenhum cabeçalho de autenticação em log ou em mensagem de erro.

**Vazamento.** Os estudos de `estudos_holdout` não entram na contagem. Se algum aparecer entre os trechos relevantes, a saída avisa: "a base que o usuário sintético pode consultar contém estudos do holdout; a validação pode estar inflada". Com `estudos_holdout` vazio, o aviso é "não dá para checar vazamento: nenhum estudo marcado como holdout". O servidor não tem como saber se a ferramenta de usuário sintético usa esta mesma base, então o aviso diz isso.

## Como o sinal entra no nível de confiabilidade

Segue a regra já decidida: "Alta" exige os três sinais **calculados**.

- `status: ok` conta como calculado. `nao_configurado` e `erro_conexao` não contam, e o nível não passa de Média.
- **Proposta, em aberto:** com `estudos_distintos = 0`, o nível não passa de Média, com o insight "A base da equipe não trata deste tema." O número mínimo de estudos para chamar de "com suporte" (1? 2?) não é escolhido agora. Ele precisa de uma base real e é decidido antes da etapa 3, com pré-registro.

## Calibração e validação

**Calibração (etapa 1 do PRD, sem LLM e sem rede).** Um RAG falso em `tests/`, servido por `http.server` local, com uma base plantada:
- perguntas com estudos sobre o tema (suporte plantado), em mais de uma intensidade (1, 2 e 5 estudos);
- perguntas sem nenhum estudo sobre o tema;
- estudos de holdout misturados na base (vazamento plantado);
- scores nos dois sentidos (similaridade e distância).

Metas de aceite (a confirmar):
- perguntas sem suporte plantado com `estudos_distintos ≥ 1` em no máximo 10% dos casos. O corte por placebo mira 5% por consulta; a meta deixa folga para os `top_k` trechos;
- perguntas com 2 ou mais estudos plantados detectadas em pelo menos 80% dos casos;
- vazamento plantado avisado em 100% dos casos em que o estudo de holdout volta acima do corte.

**Validação (etapa 3 do PRD).** Só com a base real e anonimizada de uma equipe. Configuração pré-registrada com hash antes de olhar os resultados. Uma pessoa da equipe marca às cegas, para uma amostra de perguntas, se a base trata ou não do tema, e isso vira a referência para medir a detecção e o alarme falso do sinal. Os resultados são publicados, incluindo as falhas.

## Critérios de aceite da implementação

- `conectar_base` funciona de três jeitos: com elicitation (formulário e URL), só com arquivo e variável de ambiente, e com recusa da pessoa (devolve `precisa_configuracao`).
- Nenhum segredo aparece em argumento de ferramenta, no `conexao.json`, em log ou em mensagem de erro. Há um teste que procura o token nas saídas.
- `pontuar_resposta` e `validar_usuario` devolvem o `suporte_na_base` com os status `ok`, `nao_configurado` ou `erro_conexao`, cada um com motivo.
- Testes cobrem os dois sentidos do score, os caminhos aninhados da resposta, o timeout, o 401, o vazamento e a calibração por placebo, todos contra o RAG falso local.
- O README explica como conectar e o que o sinal não prova, e a frase "exige RAG, previsto para depois do MVP" some do código e da documentação.
- Testado em Claude Code, Cursor e VS Code, com uma tabela no README de quais clientes aceitam elicitation.

## Fora de escopo

- Indexar documentos, gerar embeddings ou construir RAG próprio (não-objetivo do PRD).
- Julgar se o trecho concorda ou discorda da resposta.
- Adaptadores dedicados por fornecedor e o adaptador `mcp`.
- Importação genérica do holdout tabular. Fica numa spec própria, que é a outra metade de "funcionar com qualquer base": as respostas humanas para comparar distribuições não vêm do RAG.

## Decisões tomadas

- [x] **O servidor chama o RAG da equipe (27/11/2026).** Opção B, com adaptador `http` genérico no MVP.

## Decisões em aberto

- [ ] **Mínimo de estudos** para chamar de "com suporte", e se `estudos_distintos = 0` limita o nível a Média.
- [ ] **Consultas placebo:** a lista e o percentil (proposta: 30 consultas, percentil 95).
- [ ] **`top_k`** padrão (proposta: 10).
- [ ] **Cofre de credenciais:** `keyring` como dependência opcional, ou só variável de ambiente no MVP.
- [ ] **Qual RAG a primeira equipe usa**, para testar o adaptador `http` num caso real antes do lançamento.
