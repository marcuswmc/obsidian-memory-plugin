# Obsidian Memory — plugin para Claude Code

Dá a cada projeto uma memória persistente num vault Obsidian: `<projeto>/.obsidian-vault/`. Nele ficam o CLAUDE.md de contexto, o histórico de sessões, specs, planos, processos, decisões (ADRs), bugs e retrospectivas. O vault é versionado no git do próprio projeto.

- **Menos tokens:** para retomar, carrega só o `CLAUDE.md` e o resumo da última sessão (alguns KB), em vez de reconstruir o contexto.
- **Memória fora da janela:** o vault cresce no disco, e o Claude lê o que precisa quando precisa.
- **Automático:** hooks arquivam cada sessão e comitam o vault (só o vault, sem push, com verificação de segredos).

## Requisitos

| | macOS | Linux | Windows |
|---|---|---|---|
| Claude Code | ✔ | ✔ | ✔ |
| Python 3.8+ | `python3` | `python3` | `python` ou `py -3` |
| git | ✔ | ✔ | **Git for Windows** (traz o Git Bash, usado pelos hooks) |
| Obsidian Desktop | opcional | opcional | opcional |

Rode `/obsidian-memory:vault doctor` para conferir. O que faltar pode ser instalado pelo próprio plugin (`winget`, `brew` ou `flatpak`), **sempre com a sua aprovação**. Se o Obsidian não for encontrado, a página de download (https://obsidian.md/download) é aberta.

## Instalação

**Pelo GitHub (recomendado):** dentro do Claude Code, rode:
```
/plugin marketplace add marcuswmc/obsidian-memory-plugin
/plugin install obsidian-memory@obsidian-memory
```

**Manual:** clone ou copie este repositório para `~/.claude/skills/obsidian-memory/` (no Windows, `%USERPROFILE%\.claude\skills\obsidian-memory\`). Como a pasta tem `.claude-plugin/plugin.json`, o Claude Code a carrega como plugin (`obsidian-memory@skills-dir`) na próxima sessão.

Use **só um** dos dois métodos, porque com os dois instalados os hooks rodam em dobro. Depois, reinicie o Claude Code (ou rode `/reload-plugins`) e confira com `/obsidian-memory:vault doctor`.

Os hooks vêm no próprio plugin (`hooks/hooks.json`), então não é preciso editar o `settings.json`.

### Windows
- Instale o [Git for Windows](https://git-scm.com/downloads/win). Os hooks rodam `bash scripts/vault …`, e o Git Bash é o que fornece o `bash`. Se o Claude Code não achar o Git Bash, defina `CLAUDE_CODE_GIT_BASH_PATH` (por exemplo `C:\Program Files\Git\bin\bash.exe`) no `env` do `settings.json`.
- O lançador `scripts/vault` usa `python3`, `python` ou `py -3`, nessa ordem, e ignora o atalho da Microsoft Store que não é um Python de verdade.
- Tudo é lido e gravado em UTF-8.
- O Obsidian é procurado em `%LOCALAPPDATA%\Programs\Obsidian` e a configuração dele em `%APPDATA%\obsidian\obsidian.json`.

## Uso

| Comando | O que faz |
|---|---|
| `/obsidian-memory:vault init` | Cria o vault, faz `git init` se necessário, comita e abre no Obsidian |
| `/obsidian-memory:vault save` | Escreve o resumo da sessão, atualiza o Current State e comita o vault |
| `/obsidian-memory:vault status` | Mostra o estado do vault, do git, do Obsidian e os alertas |
| `/obsidian-memory:vault open` | Registra e abre o vault no Obsidian (pergunta antes de reiniciar o app) |
| `/obsidian-memory:vault doctor` | Verifica os requisitos e oferece instalar o que faltar |

Também funciona pedindo em linguagem natural: "salva a sessão", "registra essa decisão", "onde paramos?".

## Hooks

| Evento | Ação |
|---|---|
| SessionStart | Injeta a última sessão e os alertas; depois de uma compactação, reinjeta também o CLAUDE.md |
| PreCompact | Arquiva o transcript e comita o vault antes da compactação |
| SessionEnd | Arquiva o transcript e a memória e comita o vault |

## Garantias

- Os commits incluem **somente** `.obsidian-vault/`. O que você deixou em stage não é tocado, e nunca há push.
- Transcripts e cópias da memória ficam fora do git (`.obsidian-vault/.gitignore`).
- Antes de cada commit, o script procura segredos. Se achar algo, não comita e mostra um alerta no próximo início de sessão.
- Nenhum vault é criado automaticamente em home, Downloads, Desktop, Documents, pastas temporárias ou na raiz de um disco.
- Nada é instalado e o Obsidian nunca é reiniciado sem a sua aprovação.

## Configuração (`scripts/vault.py`)

| Constante | Padrão |
|---|---|
| `VAULT_DIR` | `.obsidian-vault` |
| `CONTEXT_LIMIT` | 12000 caracteres injetados |
| `SECRET_PATTERNS` | padrões de segredos verificados antes do commit |
| `OBSIDIAN_CONFIG` | configuração inicial do `.obsidian/` (Daily Notes, Templates) |
| `excluded()` | pastas onde o vault nunca é criado |

## Licença

MIT
