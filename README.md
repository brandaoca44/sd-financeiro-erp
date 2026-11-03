# SD Financeiro ERP

ERP brasileiro voltado à gestão de empresas, com organização por empresa,
controle de acesso e acompanhamento financeiro em uma arquitetura modular.

O projeto tem caráter demonstrativo: apresenta habilidades em desenvolvimento
backend, modelagem de dados, segurança e testes, junto ao entendimento das regras
e dos processos de um sistema de gestão empresarial. Seu desenvolvimento parte
de fluxos de negócio concretos, com regras explícitas e integridade transacional.

## O que o sistema faz

- Organiza empresas identificadas por CNPJ dentro de organizações independentes.
- Gerencia usuários, vínculos e permissões específicas por empresa e operação.
- Permite lançar, consultar, editar e cancelar títulos de contas a pagar.
- Registra baixas manuais parciais ou totais e estornos com histórico preservado.
- Controla valores pagos e em aberto com cálculos decimais exatos.
- Resume contas a pagar por empresa e período, com vencidos, próximos vencimentos,
  baixas, estornos e série diária para indicadores.

A direção do produto é reunir gestão e inteligência empresarial: identificar
possíveis desperdícios, melhorias operacionais e oportunidades com base nos dados.
Contas a receber, comercial, compras, estoque, fiscal e painel executivo são
extensões planejadas; não são apresentados como módulos já concluídos.

## Como funciona

Cada organização define uma fronteira de dados e pode possuir diferentes empresas.
Os usuários representam pessoas autorizadas a operar essas empresas. O Master
administra os acessos; cargos não concedem permissões automaticamente.

As regras de autorização são verificadas no backend para cada empresa e operação.
Consultar títulos, gerenciá-los, registrar baixas e estornar são permissões
independentes. O isolamento também é reforçado por referências compostas no banco.

O fluxo financeiro parte de um título a pagar. Baixas e estornos geram movimentos
que determinam o saldo, mantendo o histórico. Transações, bloqueios e revisões
protegem alterações concorrentes. A idempotência evita duplicar movimentos quando
uma requisição é repetida após uma falha de comunicação.

Os relatórios distinguem saldo atual de atividade do período. Valores pagos são
registros informados pelo operador; o sistema não executa transferências bancárias.
O resumo de contas a pagar também não equivale a saldo de caixa ou lucro.

## Arquitetura e tecnologias

A aplicação utiliza um monólito modular com API HTTP. Contratos de entrada e saída,
regras de negócio, autorização e persistência possuem responsabilidades separadas.

| Tecnologia | Aplicação no projeto |
| --- | --- |
| Python e FastAPI | Backend assíncrono e contratos HTTP |
| Angular e TypeScript | Interface modular, formulários reativos e integração tipada com a API |
| Pydantic | Validação de dados e configuração tipada |
| SQLAlchemy e Psycopg | Modelagem relacional e acesso ao PostgreSQL |
| PostgreSQL | Persistência, transações, constraints e agregações financeiras |
| Alembic | Evolução versionada do schema |
| Redis | Rate limit por conta, origem e operação |
| Argon2id | Proteção das senhas de usuário |
| cryptography | Criptografia autenticada de backups |
| Docker Compose | Definição dos serviços de infraestrutura |
| uv | Gerenciamento de dependências e ambiente Python |
| unittest e HTTPX | Testes de regras, API, persistência e isolamento |

Segurança faz parte da implementação: sessões revogáveis por inatividade,
autorização por escopo, auditoria transacional, erros mínimos e logs sem conteúdo
financeiro ou credenciais. Testes de integração verificam também concorrência,
revogação de permissões, recuperação e tentativas de acesso entre empresas.

## Documentação

- [Backend, configuração e execução](backend/README.md)
- [Frontend e fluxos da interface](frontend/README.md)
- [Planejamento e evolução funcional](docs/planejamento.md)
- [Escopo do MVP](docs/prontidao-e-primeiro-mvp.md)
- [Catálogo e comparação de planos](docs/catalogo-assinaturas.md)
- [API de contas a pagar](docs/api-contas-a-pagar.md)
- [Baixas e estornos](docs/baixas-e-estornos.md)
- [Resumo financeiro por empresa e período](docs/resumo-contas-a-pagar.md)
- [Permissões financeiras](docs/permissoes-financeiras.md)
- [Segurança e autenticação](docs/autenticacao.md)

## Licenciamento

O repositório não inclui uma licença open source. Os termos de uso e distribuição
serão definidos pelo proprietário.
