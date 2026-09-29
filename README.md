# bot-watchdog

Внешний сторож личного бота. GitHub Actions раз в ~10 минут проверяет сервер
(`/api/health/watch`) и, если он молчит или сообщает о проблеме, пишет владельцу
в Telegram и VK напрямую через их API — тревога дойдёт, даже если сервер мёртв.

Все адреса и токены — только в Settings → Secrets and variables → Actions:
`WATCH_URL`, `TG_TOKEN`, `TG_CHAT`, `VK_TOKEN`, `VK_PEER`.

Ручной запуск: Actions → watch → Run workflow (галочка «test_alert» — тестовое сообщение).
