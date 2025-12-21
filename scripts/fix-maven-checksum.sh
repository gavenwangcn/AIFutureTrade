#!/bin/bash

# ============================================
# Maven 校验和策略修复脚本
# ============================================
# 功能：修复 Maven 校验和验证警告问题
# 将校验和策略设置为 warn，允许缺少校验和时继续构建
# ============================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 查找 Maven 安装路径
find_maven_home() {
    # 方法1: 从环境变量获取
    if [ -n "$MAVEN_HOME" ] && [ -d "$MAVEN_HOME" ]; then
        echo "$MAVEN_HOME"
        return 0
    fi
    
    # 方法2: 从 PATH 中查找 mvn 命令
    MVN_CMD=$(command -v mvn 2>/dev/null || echo "")
    if [ -n "$MVN_CMD" ]; then
        # mvn 通常在 $MAVEN_HOME/bin/mvn
        MVN_DIR=$(dirname "$MVN_CMD")
        MAVEN_HOME_CANDIDATE=$(dirname "$MVN_DIR")
        if [ -d "$MAVEN_HOME_CANDIDATE/conf" ]; then
            echo "$MAVEN_HOME_CANDIDATE"
            return 0
        fi
    fi
    
    # 方法3: 检查常见安装路径
    for path in "/opt/maven/apache-maven-3.8.8" "/opt/maven/apache-maven-3.8" "/usr/local/maven" "/opt/maven"; do
        if [ -d "$path/conf" ]; then
            echo "$path"
            return 0
        fi
    done
    
    return 1
}

# 修复 Maven 配置
fix_maven_config() {
    MAVEN_HOME=$(find_maven_home)
    
    if [ -z "$MAVEN_HOME" ]; then
        log_error "无法找到 Maven 安装路径"
        log_error "请确保 Maven 已安装并且 MAVEN_HOME 环境变量已设置"
        exit 1
    fi
    
    MAVEN_SETTINGS_FILE="${MAVEN_HOME}/conf/settings.xml"
    
    log_info "找到 Maven 安装路径: $MAVEN_HOME"
    log_info "配置文件: $MAVEN_SETTINGS_FILE"
    
    # 备份现有配置
    if [ -f "$MAVEN_SETTINGS_FILE" ]; then
        BACKUP_FILE="${MAVEN_SETTINGS_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
        cp "$MAVEN_SETTINGS_FILE" "$BACKUP_FILE"
        log_info "已备份现有配置到: $BACKUP_FILE"
    fi
    
    # 创建新的配置
    log_info "更新 Maven 配置..."
    cat > "$MAVEN_SETTINGS_FILE" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.0.0
          http://maven.apache.org/xsd/settings-1.0.0.xsd">
  <mirrors>
    <mirror>
      <id>aliyunmaven</id>
      <mirrorOf>central</mirrorOf>
      <name>阿里云公共仓库</name>
      <url>https://maven.aliyun.com/repository/public</url>
    </mirror>
  </mirrors>
  <profiles>
    <profile>
      <id>aliyun-repo</id>
      <repositories>
        <repository>
          <id>aliyunmaven</id>
          <name>阿里云公共仓库</name>
          <url>https://maven.aliyun.com/repository/public</url>
          <releases>
            <enabled>true</enabled>
            <checksumPolicy>warn</checksumPolicy>
          </releases>
          <snapshots>
            <enabled>false</enabled>
          </snapshots>
        </repository>
      </repositories>
      <pluginRepositories>
        <pluginRepository>
          <id>aliyunmaven</id>
          <name>阿里云公共仓库</name>
          <url>https://maven.aliyun.com/repository/public</url>
          <releases>
            <enabled>true</enabled>
            <checksumPolicy>warn</checksumPolicy>
          </releases>
          <snapshots>
            <enabled>false</enabled>
          </snapshots>
        </pluginRepository>
      </pluginRepositories>
    </profile>
  </profiles>
  <activeProfiles>
    <activeProfile>aliyun-repo</activeProfile>
  </activeProfiles>
</settings>
EOF
    
    log_info "✓ Maven 配置已更新"
    log_info ""
    log_info "配置说明："
    log_info "- 校验和策略已设置为 'warn'，缺少校验和时只会显示警告而不会失败"
    log_info "- 已配置阿里云镜像加速依赖下载"
    log_info ""
    log_info "现在可以重新运行 Maven 命令，校验和警告应该不会再影响构建了"
}

# 主函数
main() {
    log_info "============================================"
    log_info "Maven 校验和策略修复脚本"
    log_info "============================================"
    
    fix_maven_config
    
    log_info "============================================"
    log_info "修复完成！"
    log_info "============================================"
}

# 执行主函数
main "$@"





