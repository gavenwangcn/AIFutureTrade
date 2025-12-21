# 安全建议和防护措施

## 当前问题分析

### 错误信息
```
Invalid character found in method name [SSH-2.0-Go0x0d0x0a...]. HTTP method names must be tokens
```

### 问题说明
- **攻击类型**：协议混淆攻击 / 端口扫描
- **攻击方式**：攻击者尝试在HTTP端口（5002）上发送SSH协议数据
- **目的**：探测服务、寻找漏洞、尝试未授权访问
- **影响**：目前仅产生日志噪音，Tomcat已自动拒绝无效请求

## 立即防护措施

### 1. 配置防火墙规则（推荐）

#### 如果使用云服务器（如阿里云、腾讯云）：
- 在安全组中只开放必要的端口（5002, 5000, 5003）
- 限制来源IP（如果可能，只允许特定IP访问）
- 启用DDoS防护

#### 如果使用iptables（Linux）：
```bash
# 只允许特定IP访问（根据实际情况修改）
iptables -A INPUT -p tcp --dport 5002 -s 允许的IP地址 -j ACCEPT
iptables -A INPUT -p tcp --dport 5002 -j DROP

# 或者限制连接速率（每分钟最多10个新连接）
iptables -A INPUT -p tcp --dport 5002 -m state --state NEW -m limit --limit 10/minute -j ACCEPT
iptables -A INPUT -p tcp --dport 5002 -m state --state NEW -j DROP
```

### 2. 使用反向代理（Nginx/Apache）

在应用前放置Nginx反向代理，可以：
- 过滤无效请求
- 限制请求速率
- 隐藏真实服务端口

#### Nginx配置示例：
```nginx
# 限制请求速率
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;

server {
    listen 80;
    server_name your-domain.com;
    
    # 限制请求速率
    location / {
        limit_req zone=api_limit burst=20 nodelay;
        proxy_pass http://localhost:5002;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 3. 降低日志噪音

当前Tomcat已配置为DEBUG级别记录后续错误，这是合理的。如果需要进一步降低日志：

#### 修改 `application.yml`：
```yaml
logging:
  level:
    org.apache.coyote.http11: WARN  # 将HTTP解析错误降级为WARN
    org.apache.tomcat: WARN
```

### 4. 监控和告警

建议添加：
- **日志监控**：监控异常请求模式
- **IP黑名单**：自动封禁频繁攻击的IP
- **告警机制**：当检测到大量攻击时发送告警

## 长期安全加固

### 1. 添加Spring Security（可选）

如果需要更强的安全控制，可以添加Spring Security：

```xml
<!-- pom.xml -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
```

### 2. 实现IP白名单/黑名单

可以创建一个Filter来过滤恶意IP：

```java
@Component
public class SecurityFilter implements Filter {
    private static final Set<String> BLACKLIST_IPS = new HashSet<>();
    
    @Override
    public void doFilter(ServletRequest request, ServletResponse response, 
                         FilterChain chain) throws IOException, ServletException {
        String clientIp = getClientIp(request);
        
        if (BLACKLIST_IPS.contains(clientIp)) {
            ((HttpServletResponse) response).setStatus(HttpStatus.FORBIDDEN.value());
            return;
        }
        
        chain.doFilter(request, response);
    }
}
```

### 3. 使用Fail2Ban（Linux服务器）

Fail2Ban可以自动检测并封禁攻击IP：

```bash
# 安装fail2ban
sudo apt-get install fail2ban

# 配置规则（检测HTTP解析错误）
# /etc/fail2ban/filter.d/tomcat-http.conf
[Definition]
failregex = Invalid character found in method name.*<HOST>

# /etc/fail2ban/jail.local
[tomcat-http]
enabled = true
port = 5002
filter = tomcat-http
logpath = /path/to/logs/backend.log
maxretry = 5
bantime = 3600
```

### 4. 启用HTTPS（生产环境必须）

生产环境必须使用HTTPS：

```yaml
server:
  ssl:
    enabled: true
    key-store: classpath:keystore.p12
    key-store-password: your-password
    key-store-type: PKCS12
```

## 当前状态评估

✅ **好消息**：
- Tomcat已自动拒绝无效请求
- 错误不会影响应用正常运行
- 后续错误已降级为DEBUG级别，不会产生大量日志

⚠️ **需要注意**：
- 这是常见的网络扫描行为
- 如果攻击频率很高，建议实施上述防护措施
- 定期检查日志，关注是否有成功的攻击

## 建议的优先级

1. **立即执行**：配置防火墙规则（如果可能）
2. **短期**：添加Nginx反向代理 + 速率限制
3. **中期**：实现IP黑名单机制
4. **长期**：完善监控和告警系统

## 监控命令

```bash
# 查看最近的攻击IP
grep "Invalid character found in method name" logs/backend.log | \
  grep -oP '\d+\.\d+\.\d+\.\d+' | sort | uniq -c | sort -rn

# 统计攻击频率
grep "Invalid character found in method name" logs/backend.log | wc -l
```

