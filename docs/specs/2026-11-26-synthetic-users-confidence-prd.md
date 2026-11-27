# PRD — synthetic-users-confidence (MCP open source)

Nov 26, 2026 · @Yas Avancini

## Problema e visão

O projeto é um servidor MCP open source que mede quão fiéis são os usuários sintéticos a pessoas de verdade e diz o quanto confiar em cada resposta, dentro das IDEs que as equipes já usam.

**Problema.** Ferramentas comerciais de "usuário sintético" prometem velocidade, mas raramente mostram evidência de validade. A literatura recente aponta falhas recorrentes: respostas excessivamente positivas e coerentes, achatamento de grupos demográficos e estimativas enviesadas quando o usuário sintético é só uma descrição demográfica. Quem faz pesquisa não tem um jeito aberto de testar se um usuário sintético se comporta como o público que ele representa.

**Visão.** Uma camada aberta de validação: a equipe usa a ferramenta de usuário sintético que preferir, e o MCP amostra várias respostas, compara com respostas humanas que ficaram de fora e devolve um relatório de fidelidade e um score de confiança por resposta. O projeto não vende produto: o valor é o método, o código e o harness de validação, que também servem de material prático para o curso da Aprender Design.

**Posicionamento.** Usuário sintético como ferramenta de hipótese e pré-teste, nunca como substituta de pesquisa com pessoas.

**Escopo do MVP.** Núcleo de validação e score de confiança, exposto como servidor MCP. No MVP a equipe traz os usuários e as respostas humanas; construtor de usuário sintético e RAG próprios ficam para depois. Base de conhecimento é o conjunto de pesquisas da própria equipe: transcrições, surveys e relatórios.

## Objetivos, métricas e não-objetivos

Como não há receita, o sucesso se mede por uso real, contribuição externa e rigor. As metas numéricas ficam em aberto até haver uma primeira linha de base.

**Objetivos**

1. Qualquer equipe valida, na própria IDE, os usuários sintéticos que já usa, com os próprios dados de holdout.
2. Toda resposta sintética sai com um score de confiança e com o relatório de fidelidade do usuário.
3. O projeto serve de material prático do curso da Aprender Design.
4. Forma-se uma comunidade que contribui com conectores, métricas e casos de validação.

| Métrica | O que mede | Meta |
| --- | --- | --- |
| Equipes que rodaram o harness com base de conhecimento própria | Adoção com uso real, além de estrelas no repositório | A definir |
| Contribuidores externos e PRs aceitos | Saúde da comunidade | A definir |
| Usuários com relatório de validação | Rigor no uso | A definir |
| Alunos que concluem o exercício de holdout | Uso educacional | A definir |
| Casos de validação publicados, incluindo falhas | Transparência da evidência | A definir |

**Não-objetivos**

- Vender ou hospedar um produto; não há SaaS nem serviço gerenciado.
- Substituir pesquisa com pessoas ou prever mercado.
- Fine-tuning, RAG e construtor de usuário sintético próprios no MVP; o projeto valida as ferramentas de usuário sintético, não compete com elas.
- Distribuir dados de respondentes de qualquer origem.

## Quem usa

O usuário principal é quem faz pesquisa ou decide com base nela e quer explorar hipóteses antes de recrutar pessoas.

| Perfil | Precisa de | Como o projeto atende |
| --- | --- | --- |
| Pesquisador, PM ou designer | Pré-testar mensagens, jornadas e hipóteses com rapidez e saber o quanto confiar | Score de confiança por resposta e relatório de fidelidade do usuário, dentro da IDE que já usam |
| Aluno do curso | Aprender o método e ver onde ele falha com dados próprios | Dataset de exemplo, notebook de ponta a ponta e exercício de holdout |
| Cientista de dados | Estender com modelos tabulares ou outros LLMs | Métricas e sinais de confiança extensíveis, cliente agnóstico de LLM e conector opcional |
| Contribuidor e mantenedor | Contribuir com métricas, conectores e casos de validação | Arquitetura modular, guia de contribuição e suíte de testes aberta |

## Diferenciais frente ao NotebookLM

O NotebookLM já resolve RAG com citação ([ajuda do Google](https://support.google.com/notebooklm/answer/16179559?hl=en)); o projeto não compete nisso e não constrói RAG no MVP. O diferencial está em amostrar, validar, pontuar a confiança e rodar na IDE que a equipe já usa.

| Aspecto | NotebookLM | Este projeto |
| --- | --- | --- |
| Resposta com citação das fontes | Sim, com trechos diretos das fontes | Rótulo "sintético" em toda saída; fonte quando o usuário a traz |
| Usuário | Estilo ou papel definido por instrução customizada no chat | Não constrói o usuário: valida o que a equipe já usa |
| Distribuição de respostas | Chat com uma resposta por pergunta; não encontrei amostragem múltipla | Amostragem múltipla por usuário como padrão |
| Validação de fidelidade | Não encontrei recurso equivalente | Harness com holdout, baseline humano, distribuições e placebo, e score de confiança por resposta |
| Modelo | Gemini | Agnóstico |
| Dados | Nuvem do Google; a versão Enterprise mantém os dados no projeto GCP do cliente ([Google Cloud](https://cloud.google.com/agentspace/notebooklm-enterprise/docs/overview)) | Auto-hospedado, local |
| Limites | Gratuito: 100 notebooks e 50 fontes cada ([FAQ](https://support.google.com/notebooklm/answer/16269187)); Enterprise: 300 fontes | Apenas os da infraestrutura |
| Facilidade de uso | Pronto ao entrar | Instala como MCP na IDE, mas exige configuração |

Se o projeto oferecesse só chat com citação, o NotebookLM venceria em acabamento. Por isso o MVP é apenas o harness de validação e o score de confiança, que nenhuma ferramenta verificada entrega.

## Panorama competitivo e matriz de valor

Nenhuma ferramenta que verifiquei reúne, no mesmo fluxo, ancoragem na base de conhecimento, amostragem múltipla e validação com holdout, e nenhuma validação comercial que encontrei é independente. Verificado em 26/11/2026 nas páginas oficiais, em papers e em repositórios; "não encontrei" significa que a página consultada não diz, não que o recurso não exista.

### Curva de valor

&#91;embedded content: notas qualitativas estimadas a partir das fontes verificadas · 26/11/2026\]

Só o projeto chega a nível alto em validação embutida e, com os frameworks abertos, em controle dos dados. Como o MVP não constrói usuários, a ancoragem fica em nível médio, abaixo do NotebookLM; a facilidade de uso é o ponto fraco: não há interface, só ferramentas dentro da IDE, e a instalação exige configuração.

| Fator | Nota 1 (Baixa) | Nota 5 (Alta) |
| --- | --- | --- |
| Ancoragem na base de conhecimento | Usuários por prompt ou com dados do fornecedor | Responde só a partir das pesquisas do próprio usuário |
| Amostragem múltipla | Uma resposta por pergunta | Distribuição de muitas respostas por usuário |
| Validação embutida | Sem comparação com humanos na ferramenta | Holdout, baseline humano e placebo no fluxo |
| Controle dos dados | Nuvem do fornecedor | Auto-hospedado, local |
| Facilidade de uso | Exige configuração e código | Pronto ao entrar |
| Baixo custo para o usuário | Contrato ou preço por entrevista | Gratuito, só custo de API |

As notas de Synthetic Users e Qualtrics em preço e amostragem são estimativas: as páginas consultadas não trazem o preço completo nem detalham a amostragem. As notas do projeto são a meta do MVP: ancoragem em 3 porque ele só mede o suporte na base de conhecimento, sem construir o usuário. A nota de custo considera só o preço da ferramenta; a amostragem múltipla multiplica as chamadas de API, e esse gasto fica por conta de quem usa.

### O que a validação das ferramentas mostrou

- **A validação comercial é autodeclarada.** A Qualtrics reporta desvio de 0,07 desvio-padrão contra 0,87 e 0,88 de GPT e Gemini, em uma única replicação com 584 respostas sintéticas; o texto é conteúdo de parceiro e a própria autora ressalva que uma replicação não valida todos os usos. O caso Aaru e EY foi conduzido pela EY, que é parceira. O Synthetic Users cita estudos independentes sem listá-los.
- **A evidência independente aponta no sentido contrário.** Em setembro de 2026, o [Pew Research Center](https://www.pewresearch.org/data-labs/2026/09/30/how-well-synthetic-samples-replicate-public-opinion/) fez twins de membros reais do seu painel com o melhor modelo que testou e errou em média 12,4 pontos. As respostas sintéticas exageraram diferenças entre subgrupos e perderam diversidade, e o Pew disse que não pretende usar IA para gerar os próprios resultados.
- **Alguns fornecedores reconhecem limites.** A Ipsos publicou que seus twins perderam nuances; a Qualtrics lista como pontos fracos o comportamento passado, os temas emergentes e os nichos.
- **No código aberto, as peças existem, mas estão dispersas:** o validador do TinyTroupe, as métricas do RADIUS, o SynthBench e os estudos do Anamnesis. Nenhum liga um usuário sintético ancorado em base de conhecimento própria, validação com holdout e contexto brasileiro.
- **No Brasil,** Galaxies (com a NTT Data), [Toluna](https://tolunacorporate.com/pt-br) e QuestionPro oferecem usuários ou consumidores sintéticos; não encontrei metodologia de validação publicada por nenhum deles.

### Implicações para o projeto

1. O harness não precisa reinventar métricas: deve integrar as do RADIUS (distância entre distribuições, correlação de ranking, significância) e a ideia do validador do TinyTroupe. O que é novo é o fluxo completo: holdout por estudo, baseline humano e placebo, ligado aos dados de quem usa.
2. O espaço que as fontes verificadas não cobrem é validação com holdout e score de confiança no mesmo fluxo, em português do Brasil, sobre usuários que a equipe já tem.
3. O relatório de fidelidade deve mostrar falhas por subgrupo e a variância, como o Pew fez, porque é aí que as ferramentas falham.
4. Decisão pendente: lançar um projeto novo ou contribuir com um módulo de validação para TinyTroupe ou EDSL. A segunda via ganha comunidade pronta; a primeira ganha foco e identidade. Como o MVP é um servidor de validação que serve a qualquer ferramenta de usuário sintético, ele cabe bem como módulo.

## Requisitos do MVP

O MVP é o núcleo de validação e o score de confiança, expostos como servidor MCP. A equipe traz os usuários e as respostas humanas; construtor de usuário sintético e RAG próprios ficam para depois.

| Requisito | Prioridade | Critério de aceite |
| --- | --- | --- |
| Importação de usuários, respostas sintéticas e respostas humanas (CSV ou JSON) com metadados de estudo, data, segmento e pergunta | P0 — MVP | Importa os arquivos e preserva os metadados em cada resposta |
| Checagem de dados pessoais na importação | P0 — MVP | Gera relatório do que foi detectado e removido antes de qualquer análise |
| Servidor MCP com ferramentas de amostragem, validação e score, instalável em Claude Code, Cursor e VS Code | P0 — MVP | Instala com um comando e as ferramentas aparecem na IDE |
| Amostragem múltipla: dispara N rodadas por usuário ou recebe as N respostas já coletadas, com modo crítico contra sicofancia ativo por padrão | P0 — MVP | Devolve a distribuição e a variância das respostas, não só uma resposta |
| Rótulo "sintético" e referência à fonte, quando o usuário traz uma, em toda saída e exportação | P0 — MVP | Nenhuma saída sai sem rótulo; a fonte aparece sempre que o usuário a traz |
| Score de confiança por resposta, com três sinais: dispersão entre amostras, suporte na base de conhecimento e acerto histórico em perguntas parecidas do holdout | P0 — MVP | Os três sinais aparecem separados, sem número único; o terceiro só é calculado quando há holdout |
| Harness de validação: holdout, baseline humano, distribuições, sensibilidade a prompt e placebo | P0 — MVP | Gera um relatório de fidelidade por usuário, com falhas por subgrupo |
| Dataset de exemplo e notebook de ponta a ponta | P0 — MVP | Roda do zero ao relatório sem dados reais |
| Cliente de amostragem agnóstico de LLM | P1 | Troca de modelo por configuração, sem mudar código |
| Mapeamento semântico de resposta em texto para escala Likert | P1 | Compara com resposta numérica direta no harness |
| Construtor de usuário sintético ancorado em RAG e conector opcional para modelo tabular externo | P2 | Documentado com exemplo; fora do núcleo |

## Arquitetura

&#91;embedded content: arquitetura · o MCP valida, a equipe traz usuário e respostas humanas\]

A equipe gera as respostas sintéticas com a ferramenta de usuário sintético que já usa; o servidor MCP amostra várias rodadas, compara com respostas humanas que ficaram de fora e devolve o relatório de fidelidade e o score de confiança. O LLM é configurável.

## Saídas do MCP

Cada ferramenta devolve um JSON estruturado, lido pelo agente da IDE, e um resumo em markdown, lido pela pessoa. Toda saída leva o rótulo "sintético". Os nomes das ferramentas e dos campos são proposta, ainda não decisão.

| Ferramenta | O que devolve |
| --- | --- |
| `importar_dados` | Contagem de registros, metadados reconhecidos e relatório de dados pessoais detectados e removidos |
| `amostrar` | As N respostas e a distribuição (contagens, média, variância) |
| `pontuar_resposta` | Os três sinais de confiança, separados, mais avisos |
| `validar_usuario` | Relatório de fidelidade do usuário contra o holdout |
| `exportar_relatorio` | O mesmo relatório em JSON, markdown ou CSV |

**Regras de formato.**

- Campo que não pôde ser calculado vem com `status` e motivo, nunca omitido nem zerado, para que a ausência de um sinal não seja lida como sinal bom.
- Cada número vem com o seu limite ao lado, como o campo `limite` na dispersão.
- Os campos `avisos` e `limite` são obrigatórios no JSON, e o resumo em markdown começa pelo rótulo, pelo nível de confiança e pelo que não foi calculado.
- O nível de confiança (baixa, média, alta) é uma regra simples sobre os três sinais, a definir e calibrar na etapa 2 da validação. Ele não substitui os sinais.

### Exemplo de `pontuar_resposta` (valores ilustrativos)

```json
{
  "rotulo": "sintético",
  "usuario_id": "p-014",
  "pergunta": "Você usaria a função X toda semana?",
  "amostras": 20,
  "distribuicao": { "escala": "likert5", "contagens": [1, 3, 6, 7, 3], "media": 3.4, "variancia": 1.1 },
  "confianca": {
    "dispersao": { "valor": 0.18, "leitura": "consistente", "limite": "mede consistência do modelo, não verdade" },
    "suporte_na_base": { "estudos": 2, "similaridade": 0.71, "fontes": ["estudo-03", "estudo-07"] },
    "acerto_historico": { "taxa": null, "n": 0, "status": "sem_holdout_suficiente" }
  },
  "avisos": ["terceiro sinal indisponível: faltam perguntas parecidas no holdout"],
  "resumo": "Confiança média: respostas consistentes e com 2 estudos de apoio, sem histórico de acerto."
}
```

### Exemplo do resumo em markdown

```markdown
> **SINTÉTICO.** Resposta simulada por usuário. Não substitui pesquisa com pessoas.

## Confiança: MÉDIA
Respostas consistentes e com 2 estudos de apoio, **sem histórico de acerto** para este tipo de pergunta.

**Usuário:** p-014 · **Pergunta:** "Você usaria a função X toda semana?" · **Amostras:** 20

### Distribuição (escala 1 a 5)
| 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|
| 1 | 3 | 6 | 7 | 3 |

Média 3,4 · variância 1,1. O usuário se divide: 10 de 20 ficaram em 4 ou 5.

### Os três sinais
| Sinal | Resultado | O que significa |
|---|---|---|
| Dispersão entre amostras | 0,18 (consistente) | Resposta estável. Mede consistência do modelo, não verdade. |
| Suporte na base de conhecimento | 2 estudos (estudo-03, estudo-07), similaridade 0,71 | Há base nas pesquisas da equipe, mas a pergunta não é idêntica a nenhuma. |
| Acerto histórico | **não calculado** | Faltam perguntas parecidas no holdout. |

### Avisos
- O terceiro sinal está indisponível. Não leia a ausência como sinal bom.
- O usuário não tem estudo de apoio para o subgrupo "menos de 25 anos".
```

## Validação

O harness responde a uma pergunta: este usuário se comporta como as pessoas que ele representa? Cada rodada gera um relatório por usuário.

| Teste | Como funciona | O que revela |
| --- | --- | --- |
| Holdout | Respostas reais são separadas antes da análise; o usuário responde às mesmas perguntas | Acurácia fora da amostra |
| Baseline humano | Compara com o test-retest das próprias pessoas, quando existir | O teto realista de fidelidade |
| Distribuição, não só média | Compara variância, extremos e subgrupos | Achatamento e excesso de coerência |
| Sensibilidade a prompt | Reformula a pergunta sem mudar a informação | Instabilidade da resposta |
| Placebo | Procura relações que não existem nos dados humanos | Efeitos fabricados pelo modelo |
| Numérico vs. semântico | Compara Likert direto com o mapeamento por similaridade | Qual elicitação é mais fiel |

Regra contra vazamento: o holdout se separa por estudo ou por período, nunca por linha, para o teste não repetir o que o usuário já viu.

### Score de confiança por resposta

Cada resposta sai com três sinais, separados porque misturá-los em um número só esconderia o que cada um mede.

| Sinal | O que mede | Limite |
| --- | --- | --- |
| Dispersão entre amostras | Consistência do usuário em N rodadas | Mede consistência do modelo, não verdade |
| Suporte na base de conhecimento | Quantos estudos sustentam a resposta e quão próximos da pergunta | Proxy: depende de o usuário trazer fontes |
| Acerto histórico | Taxa de acerto em perguntas parecidas e do mesmo segmento no holdout | Único calibrado; exige holdout suficiente |

O score não usa a confiança declarada pelo próprio LLM, que não é confiável.

## Validação do projeto: como saber que o MCP funciona

O harness e o score também precisam de prova. A validação tem três etapas, em ordem, porque cada uma responde a uma pergunta diferente. Os critérios de aprovação são fixados antes de rodar cada etapa; as metas numéricas ficam em aberto até haver uma linha de base.

| Etapa | Pergunta | Dados | Critério de aprovação |
| --- | --- | --- | --- |
| 1. Seed paramétrico | O harness detecta defeitos conhecidos? | Dados sintéticos gerados por um processo estatístico definido pela equipe, não por LLM, com defeitos plantados: achatamento de subgrupos, sicofancia, vazamento de holdout, efeito inexistente (placebo) e instabilidade a reformulação | Taxa de detecção de cada defeito e de alarmes falsos: meta a definir |
| 2. Pesquisa pública com humanos reais | O score é calibrado e os três sinais triangulam? | Microdados públicos por respondente, de preferência com mais de uma onda | Calibração (confiança alta com acerto alto), ablação de cada sinal contra os três juntos e redundância entre sinais: metas a definir |
| 3. Piloto com base de conhecimento real | Funciona em pesquisa real de produto? | Base de conhecimento anonimizada de uma equipe, nunca publicado, com holdout próprio | Uma equipe externa reproduz o relatório e reporta as falhas; os resultados são publicados, incluindo as falhas |

**Regra do seed.** Ele não pode ser gerado por LLM: usuário e "humanos" compartilhariam vieses e a fidelidade apareceria inflada por circularidade. O seed prova que o harness funciona onde a relação foi plantada, não que ela existe no mundo; por isso a etapa 2 não pode ser pulada.

### Critérios para escolher a pesquisa pública

- Microdado por respondente, não relatório agregado, com segmento e a pergunta literal.
- Mais de uma onda, para separar o holdout por período.
- Publicada depois do corte de conhecimento do modelo testado, ou disponível só em arquivo de dados e raramente reproduzida em texto, para reduzir a contaminação do treino.
- Licença que permita reusar e redistribuir o recorte usado no dataset de exemplo, conferida caso a caso.
- O mais próxima possível de comportamento e uso de produto, em português do Brasil quando houver.

**Limite.** Surveys de opinião e comportamento testam distribuições, subgrupos e calibração, mas não testam o usuário respondendo a uma pergunta qualitativa de produto; isso fica para a etapa 3. Os candidatos levantados estão abaixo e só entram no dataset de exemplo depois de conferidas licença e data.

### Candidatos levantados

Verificado em 26/11/2026 nas páginas dos próprios produtores. A avaliação de aderência e de contaminação é minha, não dos produtores.

| Pesquisa | Cobertura | Licença e uso | Observação |
| --- | --- | --- | --- |
| [TIC Domicílios (Cetic.br)](https://cetic.br/media/microdados/1027/tic_domicilios_2025_relatorio_metodologico_v1.0.pdf) | Brasil: uso de internet, aplicativos e comércio eletrônico por indivíduos; microdados baixáveis, com edição de 2025 | A publicação da pesquisa é [CC BY-NC 4.0](https://cetic.br/media/docs/publicacoes/2/pt-br/20260511173200/tic_domicilios_2025_livro%20pt.pdf); a licença dos microdados ainda precisa ser confirmada | Mais próxima de uso de produto, em português e recente, o que reduz a contaminação |
| [AmericasBarometer (LAPOP)](https://www.vanderbilt.edu/cgd/americasbarometer/) | Opinião pública nas Américas, com o Brasil em várias ondas até 2023 e uma rodada de 2026 anunciada | Acesso gratuito e sem restrições, com compromisso de citar e proteger a privacidade; módulos experimentais só saem após dois anos | Ótimo para holdout por onda; o tema é governança e democracia, distante de produto |
| [European Social Survey](https://europeansocialsurvey.org/node/58) | Atitudes e valores em países europeus, em rodadas até a 11 (2023) | CC BY-NC-SA 4.0, sem restrição para fins sem lucro | Sem Brasil; redistribuição possível só para uso não comercial e com a mesma licença |
| [General Social Survey (NORC)](https://gss.norc.org/terms-and-conditions.html) | Atitudes sociais nos EUA, de 1972 a 2024 | Download gratuito; os termos pedem citação e uso responsável | Em inglês e muito conhecida, então o risco de contaminação é alto |
| [World Values Survey](https://www.worldvaluessurvey.org/AJDownloadLicense.jsp) | Valores em dezenas de países, ondas 1 a 7 e a 8 em coleta | Uso sem fins lucrativos, com citação e sem redistribuir os arquivos | Não pode entrar no repositório; só por script de download |
| [Stack Overflow Developer Survey 2025](https://survey.stackoverflow.co/) | Uso de ferramentas de desenvolvimento e IA por pessoas desenvolvedoras: 49.191 respondentes, 172 colunas, microdado por respondente, edições anuais | Dados [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) (atribuição e mesma licença em derivados), conteúdo DbCL 1.0; CSV de 141 MB no Git LFS do [repositório oficial](https://github.com/StackExchange/Survey/tree/main/packages/archive/2025) | Escolhida para a etapa 2. Perguntas ordinais e com boa dispersão: `AIAcc` (confiança na precisão da IA), `AISent` (sentimento), `AISelect` (frequência de uso), `AIComplex` (IA em tarefas complexas); cerca de 33 mil respostas cada. Risco de contaminação alto, porque os resultados são muito reproduzidos em texto |

**Decisão (26/11/2026).** A primeira pesquisa de validação é a Stack Overflow Developer Survey 2025, pelo volume (poder estatístico para subgrupos e holdout), pelo microdado aberto e pela proximidade com uso de ferramentas digitais. O holdout é sorteado por respondente e estratificado por `Age`, `DevType` e `Employment`; a contaminação é tratada comparando com a baseline de um modelo sem acesso aos dados. Pesquisa de produto em português fica como segunda validação.

**Sugestão para a segunda validação.** Começar pelo TIC Domicílios e pelo AmericasBarometer: o primeiro é o mais próximo de uso de produto e do contexto brasileiro, o segundo traz o Brasil em várias ondas para o holdout por período. Como as licenças variam e algumas proíbem redistribuir, o repositório traz um script que baixa os dados da fonte, e não os próprios dados.

## Governança, privacidade e riscos

**Licença.** Uma licença permissiva (Apache 2.0 ou MIT) favorece a adoção; uma com proteção contra empacotamento fechado (AGPL) protege a comunidade. A escolha está em aberto.

**Privacidade.** O repositório não contém dados de respondentes. Quem usa o projeto é o controlador dos dados que importa e responde pela base legal; o projeto oferece checagem de dados pessoais na importação e um guia de LGPD. O servidor roda local e não envia dados a terceiros além do LLM que a equipe configurar.

| Risco | Mitigação |
| --- | --- |
| Saída sintética lida como pesquisa real | Rótulo obrigatório e relatório de fidelidade junto de cada saída |
| Vazamento de dados pessoais | Checagem na importação, execução local, nenhum dado real no repositório e guia de LGPD |
| Usuário herda o viés da base de conhecimento | Relatório por subgrupo e aviso sobre a cobertura da base de conhecimento |
| Sicofancia e excesso de coerência | Modo crítico por padrão e teste de distribuição |
| Falsa segurança por vazamento no holdout | Separação por estudo ou período |
| Falta de contribuidores | Arquitetura modular, casos de validação como porta de entrada e guia de contribuição |
| Score de confiança lido como probabilidade de acerto | Três sinais separados, sem número único, e aviso do que cada um mede |
| Alcance limitado a quem usa clientes MCP e pouco controle da geração | Biblioteca e CLI como núcleo, MCP como uma das interfaces, e ferramenta que dispara as N rodadas |

## Roadmap

Cada fase só termina quando seu critério de passagem é cumprido.

1. **Núcleo.** Servidor MCP, importação de dados e amostragem múltipla. *Passagem:* a ferramenta aparece e roda na IDE com o dataset de exemplo.
2. **Validação.** Harness com holdout, distribuição, sensibilidade a prompt e score de confiança, validado no seed paramétrico e em pesquisa pública com humanos. *Passagem:* o relatório de fidelidade do dataset de exemplo é reproduzido por uma pessoa de fora.
3. **Abertura.** README, licença, guia de LGPD e de contribuição; uso no curso com a primeira turma. *Passagem:* ao menos uma equipe externa valida os próprios usuários e reporta o resultado.
4. **Extensões.** Mapeamento semântico para Likert, construtor de usuário sintético ancorado em RAG, conectores para modelos tabulares e interface web.

## Questões em aberto

- [x] Nome do projeto: `synthetic-users-confidence`
- [x] Licença: MIT
- [x] Pesquisa pública de validação: Stack Overflow Developer Survey 2025 (perguntas `AIAcc`, `AISent`, `AISelect`)
- [ ] Dataset de exemplo: recorte pequeno e redistribuível, e conferir se a ODbL permite versioná-lo no repositório
- [ ] LLMs suportados na primeira versão e clientes MCP testados (Claude Code, Cursor, VS Code)
- [ ] Idioma principal da documentação (pt-BR, inglês ou ambos)
- [ ] Quem mantém o projeto e qual a governança (Aprender Design, comunidade)
- [ ] Pesquisa pública em aberto do mercado para o primeiro teste de validação (humanos de referência)
- [ ] Como o MCP obtém as N respostas: dispara as rodadas por um LLM configurado ou recebe respostas já coletadas pelo cliente
- [ ] Formato aberto de entrada de usuários, respostas sintéticas e holdout
