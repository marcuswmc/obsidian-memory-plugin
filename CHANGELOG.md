# Changelog

## 1.1.0 — 23-09-2026
- Suporte a Windows (via Git Bash) e Linux: lançador `scripts/vault` que acha `python3`, `python` ou `py -3`; caminhos, processos e URIs do Obsidian por sistema; UTF-8 em todas as leituras e escritas.
- Detecção do Obsidian Desktop instalado; se não houver, abre a página de download.
- Novos comandos `doctor` (verifica python, git, identidade do git, Obsidian e Git Bash) e `install git|python|obsidian` (sempre com aprovação do usuário).
- `marketplace.json` para instalar direto do GitHub.
- `.obsidian/plugins/` fora do git (código de terceiros e possíveis tokens em `data.json`); o `.gitignore` de vaults antigos é atualizado no próximo commit.

## 1.0.0 — 23-09-2026
- Plugin com hooks SessionStart, PreCompact e SessionEnd; skill `vault` (init, save, status, open); templates; `.obsidian/` pré-configurado; commits só do vault com scan de segredos.
