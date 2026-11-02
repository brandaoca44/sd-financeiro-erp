# Fundação de contas a pagar

## Escopo entregue

Incremento interno em `finance/`, sem rotas HTTP, interface ou permissões novas.
Inclui `PayableCreate`, models de título/movimentos/histórico e repository de
criação e leitura. `companies.read` não concede acesso a títulos financeiros.

O contrato recebe descrição, valor, emissão e vencimento. Tenant, empresa e ator
são argumentos internos separados; campos adicionais, incluindo moeda, estado e
revisão, são recusados. O chamador precisa autorizar o ator: repository não é um
serviço de autorização.

## Valores e datas

- Valor positivo em BRL, como string decimal canônica ou `Decimal`, até
  `9999999999999999.99`, com no máximo duas casas. Float, booleano, inteiro,
  notação científica textual, vírgula e não finitos são recusados.
- Banco usa `NUMERIC` sem typmod, com CHECK de escala e limite. Essa escolha
  substitui o `Numeric(18,2)` proposto: mantém o limite de negócio e rejeita
  precisão excedente antes de arredondar. Inclusive `1.000` é recusado.
  Nunca preparar parâmetros monetários usando float.
- Datas são `date` ou texto `AAAA-MM-DD`, sem hora. Vencimento não pode anteceder
  emissão; datas infinitas também são recusadas no banco. Títulos já vencidos
  podem ser cadastrados. Regras de data das baixas virão com seu serviço.
- Descrição é limitada a 300 caracteres, não vazia e normalizada nas bordas.
  É conteúdo potencialmente sensível; não registrar em logs operacionais.

## Persistência e isolamento

| Tabela | Proteção principal |
| --- | --- |
| `payables` | FK composta para tenant/empresa, criador vinculado ao tenant, revisão positiva |
| `payable_movements` | Referência ao título por escopo completo e estorno com origem no mesmo título |
| `payable_changes` | Histórico por título/empresa e ator vinculado ao tenant |

Get e list exigem tenant e empresa, filtrados antes da paginação. Get fora do
escopo retorna ausência. List tem limite de 100 itens e cursor por UUID.

Criar título inclui histórico `CREATED`, com revisão, valor, moeda, datas e estado,
sem duplicar descrição. O repository faz `flush`, sem `commit`; o serviço futuro
deve delimitar a transação e desfazê-la integralmente em falha. Histórico contém
dados financeiros sensíveis e também exigirá autorização para leitura.

As FKs são RESTRICT; histórico existente impede remover o título referenciado.
Isso não torna os registros imutáveis contra SQL privilegiado. A existência de
vínculo do ator não substitui validar atividade e permissão no serviço.

Estado cadastral é `OPEN` ou `CANCELLED`. Pago e parcialmente pago serão posições
derivadas dos movimentos, sem adicionar um saldo mutável agora. Ainda não há
comandos de edição/cancelamento nem comparação de revisão em escrita.

## Movimentos ainda não operacionais

A estrutura admite `PAYMENT` e `REVERSAL`, recusa valor inválido, origem de outro
título/empresa e segundo estorno da mesma origem. Ela não é um serviço de baixa.
Ainda faltam bloqueio transacional do título, limite de saldo, validação do tipo
e valor da origem, datas, idempotência e histórico dessas operações. CHECKs por
linha não validam a soma dos movimentos. Não inserir movimentos manualmente no
banco real nem disponibilizar essas tabelas diretamente ao frontend.

## Migration e validação

`f07c4219be86` sucede `e96b2130ad74`, criando apenas três tabelas e índices,
sem registros iniciais. Downgrade bloqueia se existir qualquer dado financeiro,
inclusive título cancelado ou histórico. Não apagar registros para forçá-lo.

O verificador de recuperação agora inclui as colunas financeiras. Backups antigos
continuam exigindo o código correspondente à sua migration, conforme
[backup e recuperação](backup-e-recuperacao.md).

Foram acrescentados 14 testes de contratos, constraints, escopo, atomicidade e
migration, incluindo roundtrip vazio e conferência de metadata/schema, em bancos
temporários na porta 5433.

Suíte completa: **413 testes aprovados**, incluindo PostgreSQL, Redis e recuperação
em contêiner descartável. Migration aplicada ao banco local na porta 5433, com
contagens anteriores preservadas, schema alinhado e as três tabelas financeiras
vazias. Nenhum banco temporário restou; não foram criados títulos reais.

As [permissões financeiras por empresa](permissoes-financeiras.md) já foram
implementadas. Os [serviços de títulos](api-contas-a-pagar.md) também estão disponíveis.
Próximo incremento: baixa/estorno com
concorrência e idempotência. O fluxo está em
[prontidão e MVP](prontidao-e-primeiro-mvp.md).
