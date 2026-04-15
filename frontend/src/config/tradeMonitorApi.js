/**
 * 浏览器访问 trade-monitor（微信通知群等）的基地址。
 *
 * 与 docker-compose 的关系：
 * - compose 里 `trade-monitor` 服务映射：`${TRADE_MONITOR_PORT:-5005}:5005`，并参与网络名 `trade-monitor:5005`
 * - 其它**容器**访问监控服务：环境变量 `TRADE_MONITOR_URL`（默认 `http://trade-monitor:5005`），见 docker-compose 中 async-service 等
 * - **浏览器**不在 Docker 网络里，不能使用主机名 `trade-monitor`，应使用「宿主机 + 映射端口」，即与 `TRADE_MONITOR_PORT` 一致（默认 5005）
 *
 * 前端构建时可与 compose 对齐端口/完整地址（Vite 仅暴露以 VITE_ 开头的变量）：
 * - `VITE_TRADE_MONITOR_PORT` — 与 `.env` / compose 中的 `TRADE_MONITOR_PORT` 保持一致（默认 5005）
 * - `VITE_TRADE_MONITOR_URL` — 若用 Nginx 反代或自定义完整地址，可设完整 URL（无尾部斜杠），优先于 PORT
 *
 * 本地开发：`npm run dev` 下使用相对路径 `/api/...`，由 vite.config.js 将 `/api/wechat-groups` 代理到本机 trade-monitor（与 compose 映射端口一致即可）
 */

export const getTradeMonitorBaseUrl = () => {
  const full = import.meta.env.VITE_TRADE_MONITOR_URL
  if (full) {
    return String(full).replace(/\/$/, '')
  }
  if (import.meta.env.DEV) {
    return ''
  }
  const protocol = window.location.protocol
  const hostname = window.location.hostname
  const port = import.meta.env.VITE_TRADE_MONITOR_PORT || '5005'
  return `${protocol}//${hostname}:${port}`
}

/**
 * @param {string} path 以 / 开头的路径，如 /api/wechat-groups
 */
export function tradeMonitorUrl(path) {
  const p = path.startsWith('/') ? path : `/${path}`
  const base = getTradeMonitorBaseUrl()
  return base ? `${base}${p}` : p
}
