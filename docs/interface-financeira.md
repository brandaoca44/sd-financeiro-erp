# Interface financeira em Angular

## Estrutura

`frontend/src/app/core` concentra sessão, contextos, formatação e cliente financeiro.
`features/auth` contém login. `features/finance` contém shell, resumo e títulos.
Angular Router protege o acesso à aplicação e carrega as funcionalidades sob
demanda. Componentes não contêm regras de autorização ou cálculo do domínio.

A primeira interface integra os contratos já existentes, sem migração de banco,
mudança de expiração ou concessão automática. Contas existentes são usadas no
login; criação de conta depende dos convites e bootstrap já implementados.

## Contextos autorizados

`GET /api/v1/auth/workspaces`, autenticado, retorna página com limite de 1 a 100
e cursor UUID. Cada item tem somente `organization_id`, `company_id`, nome
cadastral opcional e as quatro capacidades financeiras efetivas daquele escopo.

São listadas apenas empresas ativas nas quais o usuário ativo possui vínculo
ativo e alguma permissão financeira, por propriedade ou concessão direta.
Leitura de organização, provisionamento ou cargo não abre diretório de empresas.
O filtro SQL precede o limite; não há catálogo global enviado ao cliente.

Nome cadastral só é retornado se a leitura de Company já for permitida. Para
financeiro sem essa leitura, a interface usa rótulo com referência curta da
empresa, sem obter razão social, CNPJ ou dados da organização indevidamente.
Nomes duplicados são diferenciados por referência da empresa.

A lista não substitui verificação na operação. Revogação ou inatividade é aplicada
na próxima requisição protegida. Atualizar contextos limpa a seleção e os dados
anteriores; nenhuma capacidade é incorporada ao token.

## Comportamento

O painel distingue posição atual de atividade por período. Gráfico tem consulta
tabular dos valores exatos. Títulos não confundem estado cadastral ativo com saldo
em aberto: pago e parcialmente pago aparecem na posição individual.

Escritas têm confirmações e respostas mínimas. O usuário com gestão sem leitura
pode cadastrar, mas não recebe lista ou detalhes automaticamente. Operações que
dependem de selecionar títulos/movimentos na tela requerem sua leitura; fluxos
específicos de tarefas por referência para operadores sem leitura ficam pendentes.

Sem acesso, sem registros, carregamento, falha de rede, conflito e sessão encerrada
têm estados separados. Erros exibidos são mensagens locais fixas, não cópias de
exceções. O cliente não imprime senha, token, payload ou resposta privada no console.

## Segurança e entrega

Sessão é mantida apenas em memória e reaplicada somente à API relativa própria.
Uma resposta 401 antiga não encerra uma sessão nova. Troca de contexto descarta
respostas atrasadas antes de renderizá-las. Não há leitura em background para
renovar inatividade, cache persistente ou mudança das regras do backend.

Na publicação, servir arquivos e API por origem controlada com HTTPS, headers
de segurança e política CSP compatível com Angular. Não publicar o Angular CLI
ou o servidor sintético de QA como infraestrutura de produção. A homologação
com usuários e as pendências de [prontidão](prontidao-e-primeiro-mvp.md) continuam
necessárias; build e teste automatizado não substituem essa aprovação.

Angular 21 foi selecionado dentro das faixas suportadas da
[matriz oficial](https://angular.dev/reference/versions). Pacotes e lockfile
registram versões; os overrides transitivos tratam os avisos
[glob](https://github.com/advisories/GHSA-3g3m-2fjr-6pw4) e
[minimatch](https://github.com/advisories/GHSA-g3hv-75wg-m249), sem downgrade do framework.

## Identidade e linguagem

A interface utiliza o monograma SDF e linguagem institucional, objetiva e discreta. Textos devem orientar a operação e identificar funcionalidades, sem slogans ou mensagens motivacionais. A apresentação prioriza hierarquia visual, consistência e leitura dos dados.

Validação atual: build de produção e 15 testes do frontend aprovados; 515 testes do backend aprovados com infraestrutura isolada e restauração de backup. Auditoria npm sem vulnerabilidades reportadas.


As telas de identidade compartilham uma composição responsiva com a imagem fornecida pelo responsável pelo projeto, transição curva e elementos vetoriais locais. A foto é ilustrativa; seus gráficos não representam dados operacionais. Consulte [Ciclo de conta](ciclo-de-conta.md) para cadastro, CPF, confirmação, recuperação e MFA.
