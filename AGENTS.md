# AGENTS.md

## Cursor Cloud specific instructions

### Project Overview
AIFutureTrade is a microservices-based AI-powered cryptocurrency futures trading system with Java (Spring Boot 3.2) + Python (Flask) + Vue 3 (Vite) stack.

### Services

| Service | Directory | Port | Tech | Dev Start Command |
|---------|-----------|------|------|-------------------|
| MySQL | docker-compose-mysql.yml | 32123→3306 | MySQL 8.0 (Docker) | `docker compose -f docker-compose-mysql.yml up -d` |
| Backend | `backend/` | 5002 | Java 21 + Spring Boot | `java --add-opens java.base/java.lang.invoke=ALL-UNNAMED -jar backend/target/java-backend-1.0.0.jar` |
| Binance Service | `binance-service/` | 5004 | Java 21 + Spring Boot | `java --add-opens java.base/java.lang.invoke=ALL-UNNAMED -jar binance-service/target/binance-service-1.0.0.jar` |
| Trade Service | `trade/` | 5000 | Python 3 + Flask | `MYSQL_HOST=localhost MYSQL_PORT=32123 MYSQL_USER=aifuturetrade MYSQL_PASSWORD=your_password_here MYSQL_DATABASE=aifuturetrade USE_GUNICORN=false python3 -m trade.app` |
| Frontend | `frontend/` | 3000 | Vue 3 + Vite | `cd frontend && npm run dev` |

### Key Development Gotchas

1. **MySQL port**: Docker maps MySQL container port 3306 to host port **32123**. Backend services must use `SPRING_DATASOURCE_URL=jdbc:mysql://localhost:32123/aifuturetrade?useSSL=false&serverTimezone=UTC&characterEncoding=utf8` when running locally.

2. **Database schema**: The Python trade service auto-creates all database tables on startup via `trade/common/database/database_init.py`. You MUST start the trade service at least once before other services can function properly.

3. **MySQL credentials**: The Docker init script (`mysql/init-database.sh`) attempts to change passwords but may not run correctly with default `.env.example` values. Default working credentials are:
   - root: `your_root_password_here` / user `aifuturetrade`: `your_password_here` (from Docker ENV)

4. **Java version**: Java 21 works fine even though `pom.xml` targets Java 17. The `--add-opens java.base/java.lang.invoke=ALL-UNNAMED` JVM flag is required for MyBatis-Plus reflection.

5. **TA-Lib**: The Python `TA-Lib` package requires the C library to be installed first (`/usr/lib/libta_lib.so`). If missing, `pip install TA-Lib` will fail.

6. **Frontend proxy**: Vite dev server proxies `/api` and `/socket.io` to `http://localhost:5002` (backend). No manual proxy config needed for development.

7. **Build commands**: See README.md for standard commands. Java services: `mvn clean package -DskipTests` in each service dir. Frontend: `npm install && npm run dev` in `frontend/`.

8. **Docker daemon**: Must be started before MySQL. In nested container environments, use `fuse-overlayfs` storage driver and `iptables-legacy`.

### Lint / Test / Build

- **Backend tests**: `cd backend && mvn test`
- **Frontend build**: `cd frontend && npm run build`
- **Backend build**: `cd backend && mvn clean package -DskipTests`
- **Binance service build**: `cd binance-service && mvn clean package -DskipTests`
- No dedicated linter configured for Java (uses IDE inspections). No ESLint configured for frontend.
