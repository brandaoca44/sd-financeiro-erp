# Prontidão operacional e primeiro fluxo do MVP

## Situação da base

A fundação permite continuar o desenvolvimento local com dados sintéticos. Não
está liberada para produção ou para receber dados reais de clientes. A última
validação de código teve 452 testes aprovados; este documento não acrescenta
implementações nem altera permissões, banco ou configuração.

| Área | Entregue | Necessário antes de produção |
| --- | --- | --- |
| Identidade | Login, sessões por inatividade, logout e rate limit | Recuperação de conta, troca de senha e revogação global de sessões |
| Onboarding | Convites e aceite auditados | Entrega direta e verificação de e-mail; revisão de senhas comprometidas |
| Autorização | Master, perfis, delegação limitada e leitura específica por empresa | Permissões de cada operação dos módulos e homologação de isolamento |
| Banco | Migrations e constraints de escopo | Separar credencial da aplicação da credencial de manutenção; revisar privilégios e defesa no banco |
| Backup | Arquivo cifrado e ensaio em contêiner descartável | Cópia externa, retenção, agendamento, alertas, RPO/RTO e procedimento completo de recuperação |
| Segredos e rede | Validação por ambiente e launcher local seguro | Gestor de segredos, rotação, TLS e configuração de banco/Redis e proxy da implantação |
| Observabilidade | Erros mínimos, correlação e logs por campos permitidos | Coleta restrita, retenção, monitoramento e resposta a incidentes |
| Produto | API de identidade e cadastros jurídicos | Fluxos de negócio e interface com estados de erro, acesso e validação homologados |

Essas pendências impedem a entrada em produção, mas podem ser trabalhadas em
paralelo ao módulo local. Não marcar um item como concluído apenas por existir
uma variável de configuração ou um teste unitário: registrar a validação no
ambiente de destino. Não copiar dados reais para desenvolvimento ou testes.

## Primeiro fluxo: contas a pagar

O primeiro recorte funcional será registrar e acompanhar obrigações de uma empresa,
efetuar uma baixa manual e corrigir essa baixa por estorno. Isso cria uma base
para posição de valores a pagar e, depois, análise de gastos. Uma baixa manual
registra um pagamento informado pelo operador; não movimenta dinheiro no banco.

O ERP continua destinado a empresas com CNPJ. Um usuário opera em nome da empresa;
o cargo não concede acesso automaticamente.

### Escopo e regras

- Cada título pertence a uma única Organization e Company. Todas as consultas,
  referências, históricos e escritas precisam conferir ambos os identificadores.
- Lançamento manual com descrição limitada, valor original em BRL, emissão e
  vencimento. Não exigir integração fiscal ou bancária para cadastrar o título.
  Descrição é dado potencialmente sensível: validar tamanho, restringir leitura e
  nunca registrar seu conteúdo em logs operacionais.
- Valores positivos em `Decimal`, sem float, com limite equivalente a 18 dígitos
  e duas casas. A persistência usa `NUMERIC` com CHECKs para recusar arredondamento
  silencioso, conforme [contrato entregue](persistencia-contas-a-pagar.md). O contrato HTTP deve
  aceitar representação decimal exata, rejeitando mais de duas casas, valores
  não finitos e valores acima da capacidade da coluna.
- Revisão otimista nas alterações. O valor original não poderá ficar abaixo do
  total líquido já baixado. Alterações de título e baixas entram no histórico.
- Baixa manual total ou parcial. Duas operações concorrentes não podem consumir
  o mesmo saldo nem produzir pagamento acima do valor da obrigação.
- Estorno vinculado à baixa original, sem apagar o registro. Nesta versão, cada
  baixa admite um estorno integral; para corrigir parte, estornar e registrar a
  baixa correta. Estorno repetido não pode devolver saldo duas vezes.
- Estados em aberto, parcialmente pago e pago decorrem dos movimentos válidos.
  Cancelamento só é permitido sem saldo líquido pago e preserva o histórico.
  Reabertura de título cancelado fica fora deste primeiro fluxo.
- Escritas de baixa e estorno devem prever idempotência: repetição da mesma chave
  e conteúdo devolve o mesmo resultado; chave reutilizada com conteúdo diferente
  gera conflito. A chave tem escopo da empresa, ator e operação. Persistir o
  resultado junto da alteração para evitar duplicidade após timeout.
- As datas serão campos de calendário, com regras de emissão, vencimento e baixa
  explícitas nos contratos antes da publicação das rotas. Não inferir períodos
  contábeis nem calcular juros ou tributos automaticamente.

### Autorizações

As chaves abaixo já estão no catálogo e na política de autorização; as operações
de negócio ainda serão publicadas nos próximos incrementos:

| Permissão proposta | Operação |
| --- | --- |
| `payables.read` | Consultar títulos e movimentos autorizados da empresa |
| `payables.manage` | Criar, editar e cancelar títulos |
| `payables.settle` | Registrar baixa manual |
| `payables.reverse` | Estornar baixa |

A concessão precisa conter o escopo da empresa. Nenhuma chave é implícita em
`companies.read`, em cargo ou em outra permissão financeira. O Master administra
as concessões; colaboradores não podem redelegá-las. A política do proprietário
deve ser explícita e testada, sem tornar o operador da plataforma um administrador
financeiro dos clientes.

A infraestrutura de concessões foi ampliada por migration sem criar ou ativar
direitos existentes. Inatividade e reativação continuam sem restaurar permissões
revogadas. Contrato em [permissões financeiras](permissoes-financeiras.md).

## Ordem de implementação

1. **Domínio e persistência:** contratos monetários e de datas, título, movimentos,
   revisões e histórico; constraints e migration sem dados de demonstração no banco
   real. Começar sem novas rotas públicas.
2. **Autorização financeira:** ampliar o catálogo e as concessões por empresa de
   forma explícita; validar leitura, escrita e ciclo de revogação independentemente.
3. **Lançamento e consulta:** serviços e rotas de criação, edição, cancelamento e
   listagem com filtros autorizados antes da paginação; respostas com campos mínimos.
4. **Baixa e estorno:** transações, concorrência, idempotência e histórico atômico.
   Não usar o Redis como fonte da integridade dos movimentos financeiros.
5. **Posição a pagar:** valores em aberto, pagos e vencidos por empresa e período,
   derivados de registros válidos; testar totais sem dupla contagem.
6. **Interface e homologação:** páginas consumindo a API protegida, sem carregar
   dados não autorizados para depois escondê-los no frontend.

Cada incremento deve documentar o contrato efetivamente entregue e passar pelos
testes pertinentes. O item 1 tem contratos e persistência implementados, incluindo
estrutura de movimentos; suas operações transacionais ainda não estão disponíveis.
Os itens 2 e 3 também estão implementados; o próximo incremento é o item 4,
baixa e estorno. Contrato atual: [API de títulos](api-contas-a-pagar.md). Não alterar as rotas
de autenticação ou a política de expiração por inatividade para entregar o módulo.

## Critérios de aceite do fluxo

- Testes negativos entre tenants, empresas e permissões, inclusive referência
  forjada, acesso por UUID, listagem e empresa/vínculo inativo.
- Casos de centavos, limites, casas decimais indevidas e totais exatos; nenhuma
  soma financeira baseada em float.
- Pagamento parcial/total, estorno e cancelamento coerentes, com concorrência e
  tentativas repetidas sem duplicar efeitos.
- Falha de auditoria ou de persistência desfaz toda a operação. Não apagar histórico
  nem expor dados financeiros em logs, erros ou rotas sem autorização.
- Migrations e restauração testadas em infraestrutura isolada. Downgrade não pode
  descartar títulos, movimentos ou histórico silenciosamente.
- Homologação do fluxo completo antes de incluir dados reais ou chamar o MVP de
  concluído; a liberação depende também das pendências operacionais acima.

## Evolução posterior

Contas a receber, conciliação bancária, cobrança, integrações de pagamentos,
recorrências, parcelamentos automáticos, anexos, aprovações por alçada e cálculos
tributários não entram automaticamente neste recorte. Organograma e acesso por
setor/página acompanham os módulos e a interface, com autorização no backend.

O painel de oportunidades permanece na direção do produto. Detecção de desperdícios
dependerá de dados suficientes e regras rastreáveis; títulos a pagar, isoladamente,
não demonstram pagamento duplicado, economia possível ou benefício tributário.

Documentos de apoio: [planejamento](planejamento.md),
[backup e recuperação](backup-e-recuperacao.md),
[erros, logs e segredos](erros-logs-e-segredos.md) e
[concessões por empresa](acesso-por-empresa.md).
