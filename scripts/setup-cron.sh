#!/bin/bash
# ==============================================================================
# Cron 任务设置脚本
# ==============================================================================
# 用途：设置每天凌晨2点自动重启服务的cron任务
# 使用方法：sudo bash scripts/setup-cron.sh
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="/root/AIFutureTrade"
RESTART_SCRIPT="${PROJECT_DIR}/scripts/restart-services.sh"

# 检查脚本文件是否存在
if [ ! -f "$RESTART_SCRIPT" ]; then
    echo "错误: 重启脚本不存在: $RESTART_SCRIPT"
    exit 1
fi

# 确保脚本有执行权限
chmod +x "$RESTART_SCRIPT"

# Cron 任务配置（每天凌晨2点执行）
# 格式：分钟 小时 日 月 星期 命令
CRON_JOB="0 2 * * * $RESTART_SCRIPT"

# 检查是否已存在相同的cron任务
if crontab -l 2>/dev/null | grep -q "$RESTART_SCRIPT"; then
    echo "警告: Cron任务已存在，将更新现有任务"
    # 删除旧的cron任务
    crontab -l 2>/dev/null | grep -v "$RESTART_SCRIPT" | crontab -
fi

# 添加新的cron任务
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -

echo "✓ Cron任务已设置"
echo ""
echo "任务详情:"
echo "  时间: 每天凌晨2:00"
echo "  命令: $RESTART_SCRIPT"
echo ""
echo "查看当前cron任务:"
echo "  crontab -l"
echo ""
echo "删除cron任务:"
echo "  crontab -e  # 然后删除相关行"
echo "  或: crontab -l | grep -v '$RESTART_SCRIPT' | crontab -"
echo ""

