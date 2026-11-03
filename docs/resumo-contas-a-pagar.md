# Resumo de contas a pagar por empresa e período

## Objetivo e acesso

`GET /api/v1/organizations/{org}/companies/{company}/payables/summary`

Fornece indicadores e uma série diária para a futura interface financeira.
Exige sessão válida e `payables.read` na empresa exata, com usuário, vínculo,
empresa e tenant ativos. Gestão, baixa, estorno ou provisionamento da plataforma
não implicam leitura do resumo. O Master também passa pelos controles de escopo.

Não informa saldo bancário, disponibilidade de caixa, faturamento ou lucro. Não
há conta a receber ou conciliação implícita nesses números. Esta entrega é a API
do resumo; não cria uma página de frontend ou gráficos renderizados.

## Parâmetros

| Parâmetro | Regra |
| --- | --- |
| `period_start` | Data inicial obrigatória, AAAA-MM-DD |
| `period_end` | Data final obrigatória, inclusiva |
| `upcoming_days` | Janela futura de 1 a 90 dias; padrão 7 |

Período máximo de 366 dias inclusivos. Intervalo invertido, datas inválidas,
parâmetros desconhecidos ou repetidos retornam 422. Não há parâmetro para escolher
um fechamento histórico. O dia operacional usa America/Sao_Paulo e aparece em
`as_of`; a resposta declara `balance_basis: CURRENT`.

## Duas bases distintas

### Posição atual (`current`)

Considera todos os títulos cadastrados da empresa, independentemente do período
selecionado. Cancelados não compõem valores atuais. Por título não cancelado:

`saldo aberto = valor original - baixas + estornos`

| Campo | Significado |
| --- | --- |
| `original_amount` | Total original dos títulos não cancelados |
| `paid_amount` | Baixas menos estornos desses títulos |
| `outstanding_amount` | Total ainda em aberto |
| `overdue_amount` | Saldo com vencimento anterior ao dia operacional |
| `due_today_amount` | Saldo que vence no dia operacional |
| `upcoming_amount` | Saldo de amanhã até hoje + upcoming_days, inclusive |
| `later_amount` | Saldo com vencimento depois dessa janela |

As quatro faixas de vencimento não se sobrepõem e somam o aberto total. Títulos
pagos não geram saldo vencido. Contagens distinguem não cancelados, cancelados,
sem baixa, parcialmente pagos e pagos. `active_title_count` significa não cancelado,
incluindo títulos pagos; é a soma das três últimas contagens.

Títulos com emissão futura que já foram cadastrados são obrigações registradas
nesta posição; o resumo não transforma esse cadastro em comprovação fiscal.

### Atividade do período (`period`)

`original_due_amount`, `outstanding_due_amount` e `overdue_due_amount` agrupam
títulos não cancelados pelo vencimento dentro do intervalo. Os saldos continuam
sendo atuais: não reconstroem quanto estava aberto no último dia daquele mês.

`payments_amount` agrupa baixas por sua data informada no período, mesmo que o
vencimento do título seja de outro mês. `reversals_amount` agrupa estornos por sua
própria data. `net_paid_amount = payments_amount - reversals_amount`.

O líquido do período pode ser negativo quando houver estorno de baixa anterior.
Não remover retroativamente uma baixa do período antigo porque ela foi estornada
depois. Cancelamento posterior não apaga os movimentos ocorridos: os valores
brutos de baixa/estorno permanecem na atividade, enquanto o cancelado deixa de
compor o saldo atual.

Exemplo: baixa de 100 em outubro e estorno em novembro produzem líquido de 100
em outubro e -100 em novembro. O saldo atual considera o estorno nos dois relatórios.
Isso é atividade registrada no ERP, não movimentação bancária comprovada.

## Série diária (`days`)

Retorna todos os dias do período, ordenados e com zeros nos dias sem registros.
Cada ponto traz valores originais/ainda abertos com vencimento naquele dia e
baixas/estornos/líquido com ocorrência naquele dia. As somas da série correspondem
aos totais de período equivalentes. As bases de vencimento e ocorrência permanecem
separadas; não somá-las como se fossem despesas adicionais.

Moeda é BRL e valores são strings decimais com duas casas. Agregados podem exceder
o limite de um título individual e continuam exatos, sem conversão por float.
A resposta não contém descrições, motivos, usuários, títulos individuais ou tokens.

## Consistência e segurança

Autorização, títulos, movimentos, totais e série diária são lidos numa única
instrução SQL, com o mesmo snapshot do PostgreSQL. Movimentos são agrupados por
título antes de somar valores originais, evitando multiplicar o valor de uma
obrigação que tenha várias baixas ou estornos.

Não há cache de permissão, atualização de títulos, geração de movimentos ou
gravação de saldos consolidados. Somente a atividade da sessão é renovada após
uma consulta autorizada, mantendo a política de inatividade existente.

Saldo negativo ou acima do título, cancelado com líquido pago, movimento futuro
ou anterior à emissão e estorno com tipo/valor/data de origem incompatíveis
resultam em 409 mínimo. Não corrigir nem esconder dados inconsistentes no cálculo.
Uma inconsistência em outra empresa não interfere no escopo autorizado.

A consulta tem timeout SQL de cinco segundos. Infraestrutura indisponível ou
timeout retorna 503 mínimo; sem sessão, 401; sem escopo/permissão, 404 genérico.
Permanecem HTTPS em staging/produção, `no-store`, `X-Request-ID` e logs que não
registram parâmetros nem valores financeiros. Sem migration nova nesta etapa.

## Validação e próximo passo

Testes de integração cobrem zeros, precisão, limites de datas, vencimentos,
cancelamento, estornos em outro período, totais da série, isolamento, revogação,
snapshot único, dados inconsistentes e ausência de escritas financeiras.

Suíte completa aprovada: **495 testes**, incluindo 18 novos do resumo. API local
com health 200, contrato no OpenAPI e recusa 401 sem sessão com `no-store`.
Nenhum título, movimento ou resultado idempotente real foi criado e nenhum banco
temporário restou. Não houve migration ou alteração de permissões nesta entrega.

Próximo passo do fluxo: interface e homologação dos títulos, movimentos e resumo,
sem disponibilizar dados reais antes de resolver as pendências operacionais
registradas em [prontidão e MVP](prontidao-e-primeiro-mvp.md).
