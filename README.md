# FarmaEstoque

Sistema de gestão para farmácias com ponto de venda (PDV), controle de estoque e validade, relatórios de vendas e recebimento por PIX. Funciona localmente, sem dependências externas: usa apenas a biblioteca padrão do Python e um banco SQLite em arquivo único.

## Sumário

1. [Visão geral](#visão-geral)
2. [Funcionalidades](#funcionalidades)
3. [Requisitos](#requisitos)
4. [Instalação e execução](#instalação-e-execução)
5. [Primeiro acesso](#primeiro-acesso)
6. [Guia de uso](#guia-de-uso)
7. [Configurações](#configurações)
8. [Recuperação de senha](#recuperação-de-senha)
9. [Perfis e permissões](#perfis-e-permissões)
10. [Arquitetura](#arquitetura)
11. [Banco de dados](#banco-de-dados)
12. [API HTTP](#api-http)
13. [Segurança](#segurança)
14. [Backup e restauração](#backup-e-restauração)
15. [Uso em rede local](#uso-em-rede-local)
16. [Limitações conhecidas](#limitações-conhecidas)
17. [Solução de problemas](#solução-de-problemas)

---

## Visão geral

O FarmaEstoque é composto por dois arquivos principais:

- `servidor.py`: servidor HTTP, regras de negócio e acesso ao banco de dados.
- `index.html`: interface completa (HTML, CSS e JavaScript em um único arquivo), servida pelo próprio servidor.

Não há instalação de pacotes, build ou serviços externos. Os dados ficam no arquivo `farmacia.db`, criado automaticamente na primeira execução.

## Funcionalidades

**Vendas e caixa**
- PDV em tela cheia, operado por teclado, com leitura de código de barras.
- Venda de múltiplas unidades pelo formato `quantidade*código`.
- Formas de pagamento: dinheiro (com cálculo de troco), PIX, cartão de débito e cartão de crédito.
- Cupom não fiscal para impressão.
- Carrinho preservado ao recarregar a página.

**PIX**
- Geração de QR Code e código "copia e cola" no padrão BR Code do Banco Central, já com o valor da venda.
- Confirmação manual do recebimento pelo atendente.

**Estoque e produtos**
- Cadastro com código de barras, categoria, laboratório, validade, preço de compra, preço de venda, estoque atual e estoque mínimo.
- Marcação de produtos que exigem receita.
- Bloqueio de venda de produtos vencidos ou sem estoque suficiente.
- Painel com alertas de estoque baixo e de produtos vencidos ou a vencer em até 90 dias.

**Relatórios**
- Faturamento, lucro bruto e quantidade de vendas por período.
- Totais por forma de pagamento.
- Consulta de detalhes de cada venda e exportação em CSV.

**Administração**
- Perfis de administrador e operador.
- Tela de login totalmente personalizável (fundo, cartão, cores e textos), com pré-visualização.
- Recuperação de senha por código enviado ao e-mail de um administrador.

## Requisitos

| Item | Requisito |
| --- | --- |
| Python | 3.8 ou superior |
| Sistema operacional | Windows, Linux ou macOS |
| Navegador | Versão atual do Chrome, Edge ou Firefox |
| Dependências | Nenhuma (somente biblioteca padrão) |

No Windows, ao instalar o Python, marque a opção **Add Python to PATH**.

## Instalação e execução

1. Baixe ou clone o repositório:

   ```bash
   git clone https://github.com/Vitorkrun/Sistema-Farm-cia.git
   cd Sistema-Farm-cia
   ```

2. Inicie o servidor:

   | Sistema | Comando |
   | --- | --- |
   | Windows | Duplo clique em `iniciar.bat` |
   | Linux e macOS | `chmod +x iniciar.sh` e depois `./iniciar.sh` |
   | Qualquer sistema | `python servidor.py` (ou `python3 servidor.py`) |

3. O navegador abre automaticamente em `http://127.0.0.1:8000`.

Para encerrar, feche a janela do terminal ou pressione `Ctrl+C`.

### Variáveis de ambiente

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `HOST` | `127.0.0.1` | Endereço de escuta. Use `0.0.0.0` para permitir acesso por outros aparelhos da rede. |
| `PORTA` | `8000` | Porta do servidor. |

Exemplos:

```powershell
# Windows (PowerShell)
$env:HOST="0.0.0.0"; $env:PORTA="8080"; python servidor.py
```

```bash
# Linux e macOS
HOST=0.0.0.0 PORTA=8080 python3 servidor.py
```

## Primeiro acesso

Na primeira execução, o banco está vazio e o sistema exibe a tela **Criar administrador**. Informe:

- usuário;
- e-mail (obrigatório; é usado na recuperação de senha);
- senha com no mínimo 4 caracteres.

Em seguida:

1. Abra **Configurações** e preencha a chave PIX, o nome do beneficiário e a cidade.
2. Se desejar, abra **Produtos** e use **Carregar exemplos** para testar com itens fictícios (disponível apenas enquanto não houver produtos cadastrados).

## Guia de uso

### Painel

Resumo do dia: total vendido, número de vendas, quantidade de produtos cadastrados e valor do estoque a preço de custo. Exibe também as listas de estoque baixo e de produtos vencidos ou a vencer em 90 dias.

### Produtos

Listagem com busca por nome ou código de barras. Cada produto possui os campos:

| Campo | Descrição |
| --- | --- |
| Nome | Obrigatório. |
| Código de barras | Opcional, único no sistema. |
| Categoria e laboratório | Opcionais. |
| Validade | Data opcional. Produtos vencidos não podem ser vendidos. |
| Preço de compra e de venda | Usados no cálculo de faturamento e lucro. |
| Estoque atual e mínimo | O alerta é exibido quando o estoque atual é menor ou igual ao mínimo. |
| Exige receita | Exige confirmação de conferência da receita no momento da venda. |

A exclusão é restrita a administradores e não é permitida para produtos que já constam em vendas.

### PDV (caixa)

Abra pelo botão **PDV / Caixa** no menu ou no Painel.

| Tecla | Ação |
| --- | --- |
| `Enter` | Adiciona o item digitado ao carrinho |
| `F2` | Busca de produto por nome |
| `F4` | Altera a quantidade |
| `Setas ↑ ↓` | Seleciona item do carrinho |
| `F5` | Remove o item selecionado |
| `F7` | Cancela a venda inteira (com confirmação) |
| `F10` | Recebe o pagamento |
| `Esc` | Sai do PDV |

Para vender várias unidades de uma só vez, digite `quantidade*código`. Exemplo: `3*7890000000011`.

Fluxo de uma venda:

1. Leia ou digite o código de barras de cada item.
2. Pressione `F10` e escolha a forma de pagamento.
3. Em dinheiro, informe o valor recebido para calcular o troco.
4. Em PIX, apresente o QR Code ou o código "copia e cola" ao cliente, confira o recebimento no aplicativo do banco e clique em **Pagamento recebido**.
5. Para itens com receita, confirme a conferência quando solicitado.
6. Imprima o cupom, se necessário.

O cupom emitido é **não fiscal** e não substitui nota fiscal.

### Vendas e relatórios

- **Vendas:** filtro por período, com faturamento, lucro bruto, número de vendas e total por forma de pagamento. Clique em uma venda para ver os itens e reimprimir o cupom.
- **Relatórios:** consolidado por período com exportação em CSV (separador ponto e vírgula, compatível com Excel).

### Usuários

Administradores podem adicionar usuários, editar o e-mail, definir uma nova senha e remover usuários. Um usuário com vendas registradas não pode ser removido, e ninguém remove a própria conta.

## Configurações

Disponível somente para administradores, organizada em abas.

### Loja

Nome e logo da farmácia, exibidos no menu, no PDV, nos cupons e na tela de login.

### PIX

| Campo | Observação |
| --- | --- |
| Chave PIX | Qualquer tipo de chave (CPF, CNPJ, e-mail, telefone ou aleatória). |
| Nome do beneficiário | Máximo de 25 caracteres. |
| Cidade | Máximo de 15 caracteres. |

### Tela de login

Possui pré-visualização em tempo real das telas de entrada, recuperação de senha e primeiro acesso. As opções são:

| Grupo | Opções |
| --- | --- |
| Fundo | Imagem, tipo de fundo (degradê padrão ou cor sólida), cor, escurecimento (0 a 90%) e desfoque (0 a 20 px) |
| Cartão | Logo próprio, tamanho do logo, largura (300 a 600 px), arredondamento, posição (centro, esquerda ou direita), cor do cartão, dos textos e do botão |
| Textos | Título, subtítulo, nome dos campos, texto do botão, exibição e texto do link de recuperação de senha, rodapé e cor do rodapé |

O botão **Restaurar visual padrão** retorna a tela de login às configurações originais, sem alterar nome e logo da loja.

### E-mail e recuperação de senha

Configuração do servidor SMTP usado no envio dos códigos de recuperação. Veja a seção seguinte.

## Recuperação de senha

O link **Esqueci minha senha** na tela de login inicia o processo:

1. O usuário informa o e-mail de um **administrador**.
2. O sistema gera um código numérico de 6 dígitos, válido por 15 minutos, e o envia por e-mail.
3. O usuário informa o código e a nova senha.
4. Após a redefinição, as sessões abertas dessa conta são encerradas.

Regras:

- Somente e-mails de administradores recebem código. Operadores que esquecerem a senha pedem a um administrador em **Usuários → Nova senha**.
- A resposta do sistema é a mesma para e-mails existentes e inexistentes.
- O código admite no máximo 5 tentativas e só pode ser solicitado novamente após 60 segundos.
- O código é armazenado apenas como hash e é descartado após o uso.

### Configuração do SMTP

Em **Configurações → E-mail e recuperação de senha**, informe servidor, porta, segurança, usuário, senha e e-mail remetente. Use o botão **Enviar teste** para validar.

Exemplo para Gmail:

| Campo | Valor |
| --- | --- |
| Servidor | `smtp.gmail.com` |
| Porta | `465` |
| Segurança | SSL |
| Usuário | endereço de e-mail completo |
| Senha | senha de aplicativo (não a senha da conta) |

Sem SMTP configurado, o código é exibido no terminal em que o servidor está rodando. Essa opção atende ao uso local, mas o código não chega por e-mail.

### Recuperação por linha de comando

Se nenhum administrador tiver e-mail cadastrado, execute na pasta do projeto:

```bash
python redefinir_senha.py
```

O script lista os usuários e redefine a senha do usuário escolhido diretamente no banco.

## Perfis e permissões

| Ação | Operador | Administrador |
| --- | :---: | :---: |
| Usar o PDV e registrar vendas | Sim | Sim |
| Consultar vendas e relatórios | Sim | Sim |
| Cadastrar e editar produtos | Sim | Sim |
| Excluir produtos | Não | Sim |
| Acessar Configurações | Não | Sim |
| Ver chave PIX e dados de e-mail | Não | Sim |
| Gerenciar usuários | Não | Sim |
| Ver lista de usuários (nomes e perfis) | Sim | Sim (com e-mails) |

As restrições são aplicadas no servidor, e não apenas na interface.

## Arquitetura

```
Navegador (index.html)  <--HTTP/JSON-->  servidor.py  <-->  farmacia.db (SQLite)
```

- **Servidor:** `ThreadingHTTPServer` da biblioteca padrão. Entrega o `index.html` e expõe a API em `/api/`.
- **Interface:** aplicação de página única em JavaScript sem frameworks.
- **Banco:** SQLite, com chaves estrangeiras habilitadas e transações por requisição.
- **Regras de negócio:** os preços usados na venda e no PIX são sempre lidos do banco, nunca do cliente. A baixa de estoque e o registro da venda ocorrem na mesma transação.
- **QR Code:** gerado no navegador por implementação própria, sem bibliotecas externas.

### Estrutura de arquivos

```
.
├── servidor.py          Servidor, API e regras de negócio
├── index.html           Interface completa
├── redefinir_senha.py   Utilitário de redefinição de senha
├── iniciar.bat          Inicialização no Windows
├── iniciar.sh           Inicialização no Linux e macOS
├── LEIAME.txt           Guia rápido de uso
├── README.md            Esta documentação
├── .gitignore           Exclui o banco de dados e arquivos temporários
└── farmacia.db          Banco de dados (gerado na execução, não versionado)
```

## Banco de dados

O arquivo `farmacia.db` é criado e atualizado automaticamente. Bancos de versões anteriores são migrados na inicialização, sem perda de dados.

| Tabela | Finalidade |
| --- | --- |
| `usuarios` | Contas de acesso: nome (único), hash da senha, perfil (`admin` ou `operador`) e e-mail |
| `produtos` | Cadastro de produtos e estoque. O estoque atual não pode ser negativo |
| `vendas` | Cabeçalho das vendas: data, operador, total, forma de pagamento, valor pago, troco e identificador do PIX |
| `venda_itens` | Itens de cada venda, com nome, quantidade, preço e custo no momento da venda |
| `config` | Configurações em pares chave e valor (loja, PIX, SMTP e aparência do login) |
| `recuperacao` | Códigos de recuperação de senha em andamento (hash, validade e tentativas) |

Os itens vendidos guardam uma cópia do nome, do preço e do custo, de modo que alterações posteriores no produto não modificam o histórico.

## API HTTP

Todas as rotas ficam sob `/api/` e trocam JSON. As rotas protegidas exigem o cabeçalho `Authorization: Bearer <token>`, obtido no login.

### Públicas

| Método | Rota | Descrição |
| --- | --- | --- |
| GET | `/status` | Informa se é o primeiro acesso |
| POST | `/primeiro-usuario` | Cria o primeiro administrador (somente com banco sem usuários) |
| POST | `/login` | Autentica por nome ou e-mail e devolve o token |
| POST | `/recuperar/solicitar` | Solicita o código de recuperação |
| POST | `/recuperar/confirmar` | Redefine a senha com o código |
| GET | `/config` | Sem login, retorna somente os campos públicos (loja, logo e aparência do login) |

### Autenticadas

| Método | Rota | Perfil | Descrição |
| --- | --- | --- | --- |
| GET | `/me` | Todos | Dados da sessão atual |
| GET | `/config` | Todos | Operador recebe apenas campos públicos; administrador recebe tudo (a senha SMTP nunca é devolvida) |
| POST | `/config` | Admin | Salva configurações (somente as chaves enviadas) |
| POST | `/config/testar-email` | Admin | Envia e-mail de teste |
| GET | `/produtos` | Todos | Lista de produtos |
| POST | `/produtos` | Todos | Cadastra produto |
| PUT | `/produtos/{id}` | Todos | Atualiza produto |
| DELETE | `/produtos/{id}` | Admin | Exclui produto sem vendas |
| POST | `/produtos/exemplo` | Admin | Carrega produtos de exemplo |
| POST | `/pix` | Todos | Gera o payload PIX para os itens informados |
| POST | `/venda` | Todos | Registra a venda e baixa o estoque |
| GET | `/venda/{id}` | Todos | Detalhes de uma venda |
| GET | `/vendas?ini=AAAA-MM-DD&fim=AAAA-MM-DD` | Todos | Vendas e totais do período (até 500 registros) |
| GET | `/resumo` | Todos | Dados do painel |
| GET | `/usuarios` | Todos | Lista de usuários (e-mails apenas para administrador) |
| POST | `/usuarios` | Admin | Cria usuário |
| PUT | `/usuarios/{id}` | Admin | Altera e-mail e/ou senha |
| DELETE | `/usuarios/{id}` | Admin | Remove usuário sem vendas |

### Exemplo: registrar uma venda

```http
POST /api/venda
Authorization: Bearer <token>
Content-Type: application/json

{
  "forma": "dinheiro",
  "pago": 50,
  "receita_ok": false,
  "itens": [
    { "produto_id": 1, "quantidade": 2 },
    { "produto_id": 4, "quantidade": 1 }
  ]
}
```

Resposta:

```json
{ "id": 12, "total": 53.7, "troco": 0 }
```

### Códigos de resposta

| Código | Significado |
| --- | --- |
| 200 | Sucesso |
| 400 | Dados inválidos ou regra de negócio violada (produto vencido, estoque insuficiente, receita não confirmada) |
| 401 | Credenciais incorretas ou sessão expirada |
| 403 | Ação restrita a administradores |
| 404 | Recurso ou rota não encontrada |
| 409 | Conflito (código de barras ou e-mail já cadastrado, exclusão de item com histórico) |
| 500 | Erro interno |

## Segurança

Medidas implementadas:

- Senhas armazenadas com PBKDF2-HMAC-SHA256 (120.000 iterações) e sal aleatório por usuário.
- Atraso de 0,6 segundo após tentativa de login inválida.
- Sessões com token aleatório e validade de 12 horas.
- Validação no servidor de permissões, preços, estoque, validade, cores, imagens e formatos de e-mail.
- Consultas ao banco parametrizadas.
- Chave PIX, dados de SMTP e demais configurações restritas ao administrador.
- Código de recuperação armazenado com hash, expiração e limite de tentativas.

Recomendações de uso:

- Mantenha o servidor em rede local confiável. Não exponha a porta diretamente à internet.
- A comunicação é HTTP, sem criptografia. Para acesso fora da rede local, utilize um proxy reverso com HTTPS ou uma VPN.
- Não versione nem compartilhe o arquivo `farmacia.db`. Ele contém hashes de senhas, chave PIX e credenciais de e-mail.
- Em Gmail, use senha de aplicativo e revogue-a se o banco for exposto.

## Backup e restauração

Todos os dados estão em um único arquivo.

**Backup:** com o servidor fechado, copie `farmacia.db` para um local seguro (pen drive, nuvem ou outro computador). Faça isso com frequência regular.

**Restauração:** feche o servidor, substitua o `farmacia.db` pela cópia e inicie novamente.

**Atualização do sistema:** substitua apenas `servidor.py` e `index.html` e mantenha o `farmacia.db`. As alterações de estrutura do banco são aplicadas automaticamente.

## Uso em rede local

Para usar o sistema em outros computadores ou celulares da mesma rede:

1. Inicie o servidor com `HOST=0.0.0.0`.
2. Descubra o IP do computador servidor (`ipconfig` no Windows, `ip a` no Linux).
3. Nos demais aparelhos, acesse `http://IP-DO-COMPUTADOR:8000`.
4. Se necessário, libere a porta no firewall do sistema operacional.

O computador servidor deve permanecer ligado com o programa em execução.

## Limitações conhecidas

- As sessões ficam na memória do servidor. Ao reiniciá-lo, todos precisam entrar novamente.
- A confirmação do pagamento PIX é manual; o sistema não consulta o banco.
- O cupom é não fiscal. O sistema não emite NF-e, NFC-e nem integra com SEFAZ.
- Não há controle de lotes, nem integração com o SNGPC.
- Não há registro de auditoria de alterações.
- O acesso é por HTTP simples, sem TLS.
- Projeto pensado para uma loja por instalação.

## Solução de problemas

| Sintoma | Causa provável e solução |
| --- | --- |
| "Python não encontrado" ao abrir `iniciar.bat` | Instale o Python e marque **Add Python to PATH** |
| Página não abre | Confirme que o servidor está em execução e acesse `http://127.0.0.1:8000` |
| Porta em uso | Inicie com outra porta: `PORTA=8080` |
| "Sessão expirada" | A sessão venceu ou o servidor foi reiniciado. Entre novamente |
| Esqueci a senha e não há e-mail de administrador | Execute `python redefinir_senha.py` |
| Código de recuperação não chega por e-mail | Verifique o SMTP e use **Enviar teste**; confira a caixa de spam. Sem SMTP, o código aparece no terminal do servidor |
| Gmail recusa o login | Utilize senha de aplicativo, com verificação em duas etapas ativa na conta |
| Outro aparelho não acessa o sistema | Inicie com `HOST=0.0.0.0` e libere a porta no firewall |
| Interface desatualizada após trocar arquivos | Atualize a página com `Ctrl+F5` |
| Venda bloqueada por produto vencido | Atualize a validade no cadastro caso tenha havido reposição |

## Autor

Vitor Figueiredo ([@Vitorkrun](https://github.com/Vitorkrun))
