# Issue #197: ночной пул агентов

Сначала закоммить bootstrap-изменения типизации и убедись, что рабочая копия чистая. Launcher не делает commit за основную рабочую ветку и никогда не делает push.

```bash
python3 scripts/issue197_agents.py dry-run
python3 scripts/issue197_agents.py prepare
python3 scripts/issue197_agents.py run --hours 10 --concurrency 8
python3 scripts/issue197_agents.py status
python3 scripts/issue197_agents.py integrate
python3 scripts/issue197_agents.py resume --hours 10 --concurrency 8
python3 scripts/issue197_agents.py integrate
```

Первая команда `run` выполняет только foundation wave. После её интеграции второй запуск выполняет остальные 18 jobs. Логи и состояние лежат в `.issue197/`, а worktrees — в `.worktrees/issue197/`; оба пути игнорируются Git и не удаляются launcher-ом.

Каждый job начинает с GLM 5.2. Если агент завершается без чистого commit, молчит 15 минут или не делает commit за час, launcher создаёт новую worktree и сразу пробует MiniMax, затем GLM latest, после чего повторяет цикл до deadline. Предыдущие логи и diff сохраняются.

После интеграции обязательно прогоните:

```bash
make fmt-check lint typecheck analyze test build coverage
```

Не запускайте launcher из dirty worktree: `prepare` остановится, чтобы jobs не получили незафиксированные изменения.
